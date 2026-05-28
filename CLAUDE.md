# CLAUDE.md

> Auto-loaded context for Claude Code in the **AItegrity Core — AI Proofread** repository.
> Keep this file concise. Detailed docs live in [`docs/`](./docs/). Update both whenever the project changes.

---

## What this project is

A production Flask service that runs LLM proofreading on customer payloads (HTML or plain text) safely:

```
HTML Freeze → PII Mask (3 layers) → Claude (LLM) → Unmask → Reformat → Reverse HTML → persist (Mongo) → respond
```

PII is replaced with `[CATEGORY_n]` tokens **before** the prompt reaches Claude; non-`TEXT_*` tokens are unmasked after; locale-aware reformatting (mostly Indonesian phones / dates) follows. A consolidated record per run is stored in MongoDB; QA can be pushed to Google Sheets.

## Where to look first

| You want… | File |
|---|---|
| Repo layout, tech stack, branches, recent work | [`docs/PROJECT_OVERVIEW.md`](./docs/PROJECT_OVERVIEW.md) |
| Pipeline stage detail (mask layers, LLM, unmask, reformat) | [`docs/PIPELINE.md`](./docs/PIPELINE.md) |
| HTTP endpoints, request/response shapes, headers | [`docs/ENDPOINTS.md`](./docs/ENDPOINTS.md) |
| Hard invariants and gotchas (token preservation, regex traps) | [`docs/CONVENTIONS.md`](./docs/CONVENTIONS.md) |
| Environment variables (grounded in `app/core/config.py`) | [`docs/ENVIRONMENT.md`](./docs/ENVIRONMENT.md) |
| Original product README (note: partly stale — see below) | [`README.md`](./README.md) |

## Hard invariants (read before changing masking / LLM / regex code)

1. **Token preservation is sacred.** `[TEXT_*]`, `[ORG_*]`, `[DATE_*]`, `[URL_*]`, `[KEYWORD_*]`, etc. must come back from Claude **exactly and in original order**. `[TEXT_*]` tokens must NOT appear inside JSON string values; non-TEXT tokens may.
2. **Shared `counters` dict** across all three masking layers in `services/masking.py` — token IDs must be unique across layers. Don't introduce a per-layer counter that could collide.
3. **`_find_token_spans` + `_overlaps`** prevent re-masking inside an already-replaced token. Any new pattern in `mask_with_patterns` must respect this.
4. **`+`-freeze trick** in `services/phonefmt.py` (`_freeze_plus`/`_unfreeze_plus`, `​`) stops `libphonenumber` from re-matching already-handled international tokens.
5. **Indonesian mobile regex** `_RE_ID_MOBILE = r'(?<!\d)0(?:[ .()-]?\d){9,11}(?!\d)'` — match must end on a digit so trailing `.`/`,` are not swallowed. `mobile_sub` then asserts `digits.startswith("08")` and `10 ≤ len(digits) ≤ 12`. Don't loosen these without considering the trailing-punctuation regression.
6. **Strict DTO validation.** `app/modules/proofread/dto.py` (Pydantic, `extra = "forbid"`). Adding a request field requires updating the DTO.
7. **WIB timestamps** (`now_wib()` in `services/db.py`) must be invoked inside a request handler, not at import time.
8. **Masking-results mirror is non-load-bearing.** `Config.MASKING_RESULTS_FEATURE` (default OFF) toggles a 9-field whitelist side-write to `MASKING_RESULTS_DC` from `ProofreadRepo.save_masking` only (jalur B). A failure in the mirror **must never** fail the main response — it's routed through `safe_insert`. Don't change this contract. See `docs/PIPELINE.md` §10.

## Tenants and locales (active code, not the README)

- **Tenants:** `indonesia`, `malaysia`, `thailand` (ProofreadRequest DTO).
- **Locales:** `en`, `id`, `ms` — **`th` and `my` are NOT in the active DTO** (`app/modules/proofread/dto.py`). Lingua returns ISO `ms` for Malay; the DTO matches.
- **Tenant → NER model** mapping (`app/core/config.py::TENANT2MODEL`):
  - `indonesia` → `indonlu_ner_grit`
  - `malaysia` → `malay_ner_finetuned_300725_10h50_set01`
  - `thailand` → `thai_nner`

## URL prefix (active code)

`app/app.py` builds the prefix as `f"/{API_VERSION}"` if `API_PREFIX` is empty (default), so endpoints live under `/v1/...`. The README's `BASE_PREFIX=/aitegrity-core/aiproofread` is **not** applied by the Flask app itself — it's likely a reverse-proxy convention.

## Branch strategy

- `Staging` is the integration branch.
- Feature branches: `task/<slug>` (e.g. `task/regex-reformatting-improvement03`).
- Frequent merges from `Staging` into feature branches are normal.
- Versioning surfaces in response headers: `X-App-Version`, `X-API-Version`, `X-Git-SHA`.

## When working in this repo

- Code comments are predominantly in **Indonesian/Bahasa**. Match local style if you add comments — but the system default is "no comment unless WHY is non-obvious."
- The `README.md` is **partly out of sync with the code** (DTO locales, endpoint paths, rate-limit defaults, security toggles). When in doubt, **trust the code and `docs/`** over the README. If you change behavior that the README documents, fix the README in the same change.
- Update `docs/` and (when relevant) the memory dir whenever you change pipeline, endpoints, env vars, integrations, tenants/locales, or invariants. See `docs/CONVENTIONS.md` §"Doc maintenance".
