# Masking-Results Feature — Design Spec

**Date:** 2026-04-29
**Status:** Design approved, implemented

---

## 1. Goal

Persist a 9-field whitelist subset of each masking result into a separate
MongoDB collection (default: `masking_results`) so it can later be used as a
curated dataset for masking-model improvement. The feature must be toggleable
via `.env` so it doesn't add I/O when not needed.

## 2. Scope

- **In scope:** Mirror documents produced by the `POST /v1/proofread` flow
  (path B) into a new collection, restricted to a 9-field whitelist.
- **Out of scope:**
  - Standalone endpoint `POST /v1/masking/mask` (path A) — its payload lacks
    `report_id` / `toc_type` / `tenant`, so it doesn't fit the training-data
    schema.
  - Backfill tooling for source/mirror mismatches.
  - Migrating `print` calls to a logging library.
  - New threading / async / queue infrastructure.
  - Mongo-native change-stream or replica-set approaches.

## 3. Whitelist fields (9)

```
_id, report_id, toc_type, tenant, locale, message_01, layers, created_at, created_at2
```

Non-whitelisted source fields (`body`, `order`, etc.) are **not** copied to
the mirror.

## 4. Design decisions

| Aspect | Decision | Rationale |
|---|---|---|
| Architecture | Inline sync via `_ins` / `safe_insert` | Consistent with the 7 other collections; failure isolation is free; YAGNI on threading |
| Toggle parsing | Strict `"ON"` case-insensitive, default OFF | Fail-safe for a persistence-side feature; consistent with `RESULT_ANALYZE` |
| Toggle lifecycle | Parsed once at startup (attribute on `Config`) | Hot-path; consistent with `AUTO_CHAIN_*`, `DETECT_*` |
| Collection name | `MASKING_RESULTS_DC` env var, default `masking_results` | Per-env flexibility without redeploy |
| Whitelist | Hardcoded constant of 9 fields in the repo module | Schema-sensitive; ENV CSV would be too prone to silent typo breakage |
| `_id` strategy | Reuse source `_id` (pre-generate `ObjectId()` in repo) | 1:1 source↔mirror traceability; natural idempotency |
| `created_at` / `created_at2` | Copied from source (snapshot-consistent) | Identical timestamps across source and mirror |
| Missing fields | Save as-is (don't skip), log a warning | Defensive logging; don't lose entries |
| Failure isolation | `safe_insert` (already exists) — returns bool, never raises | Guarantees the mirror can't disrupt the main response |
| Logging | `print` + emoji prefix, matching the repo style | Consistency over generic best-practice |
| Mirror indexes | 2 compound: `(report_id, created_at DESC)`, `(tenant, created_at DESC)` | Source access pattern + training-pipeline tenant filter |
| Unique on `report_id`? | **No** (non-unique) | Better to over-keep than to drop; dedupe is a downstream preprocessing concern |
| Bind & index | Always, regardless of toggle | Idempotent, low cost; toggle-ON without restart still works |
| `MASKING_RESULTS_DC` read location | `services/db.py` via `os.getenv` | Consistent with neighboring `MONGO_URI`, `DB_NAME` style |
| `Config` import in repo | Direct import in `proofread/repositories.py` | Reads class attribute (resolved once at startup) |

## 5. Hard rule

**A failed write to `col_masking_results` MUST NOT fail the main response.**

This is satisfied automatically because:
1. The insert goes through `_ins` → `safe_insert` (try/except, returns bool,
   never raises).
2. `safe_insert` guards `col is None` and `DB_DISABLED`.
3. There is no exception path that can propagate to the handler.

## 6. Files touched

| File | Change |
|---|---|
| `.env.example` | Add `MASKING_RESULTS_FEATURE` and `MASKING_RESULTS_DC` |
| `app/core/config.py` | Add `Config.MASKING_RESULTS_FEATURE` (strict ON parse) |
| `services/db.py` | Add `MASKING_RESULTS_DC` env, global `col_masking_results`, binding, 2 indexes |
| `app/modules/proofread/repositories.py` | Modify `save_masking()`: pre-generate `_id`, conditional mirror write |
| `tests/test_repositories.py` | Add 3 unit tests (happy path, OFF, mirror down) |
| `docs/PIPELINE.md` | Note about mirror collection and toggle |
| `docs/ENVIRONMENT.md` | Document the 2 new env vars |
| `CLAUDE.md` (root) | 1–2 lines pointing to the feature (discoverability) |

**Not touched:** `app/modules/masking/repositories.py`,
`app/modules/masking/routes.py`, `app/app.py`.

## 7. Step-by-step implementation order

1. **Env scaffolding** — `.env.example`
2. **Config toggle** — `app/core/config.py`
3. **DB binding & indexes** — `services/db.py`
4. **Repo modification** — `app/modules/proofread/repositories.py`
5. **Unit tests** — `tests/test_repositories.py`
6. **Documentation** — `docs/PIPELINE.md`, `docs/ENVIRONMENT.md`,
   optionally `CLAUDE.md`
7. **Self-verify** — pytest passes; manual end-to-end run

## 8. Manual verification (4 scenarios)

**Scenario A — Toggle ON, full proofread.**
Hit `POST /v1/proofread` with a normal payload → both collections should contain
a document with the same `_id`; the mirror should only have the 9 whitelisted
fields.

**Scenario B — Toggle OFF.**
Set `MASKING_RESULTS_FEATURE=OFF`, restart → mirror should not receive writes.

**Scenario C — Standalone endpoint unaffected.**
Toggle ON, hit `POST /v1/masking/mask` → mirror should not receive writes
(out of scope).

**Scenario D — Mirror down (optional).**
Drop the collection or set it read-only → response succeeds, source is written,
mirror fails silently.

**Index check:** `db.masking_results.getIndexes()` should report 3 entries
(`_id_`, `report_id_1_created_at_-1`, `tenant_1_created_at_-1`).

## 9. Env format

```env
# Masking-model dataset mirror
MASKING_RESULTS_FEATURE=ON         # ON | OFF (default OFF, strict)
MASKING_RESULTS_DC=masking_results
```

## 10. Assumptions

1. Mongo is single-node (not a replica set) — inferred from
   `directConnection=true` in the example `MONGO_URI`.
2. Normal user flow produces exactly one masking document per `report_id` per
   request.
3. `bson.ObjectId` is available (transitive via `pymongo`).
4. Existing tests at `tests/test_repositories.py:29-37` (path A,
   `MaskingRepository`) are not affected by changes in path B (`ProofreadRepo`).

## 11. Open questions (resolved during brainstorming)

- Q: Scope — path A, path B, or both? → **Path B only.**
- Q: Approach? → **Inline sync.**
- Q: Toggle pattern? → **Strict `"ON"`, parsed once.**
- Q: Whitelist & `_id`? → **Hardcoded, reuse `_id`, copy timestamps.**
- Q: Failure handling? → **`safe_insert` is enough; no retry / circuit-breaker / DLQ.**
- Q: Indexing? → **Two compound indexes, non-unique.**
- Q: Testing? → **3 unit tests + 4 manual scenarios.**
