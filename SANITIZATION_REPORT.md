# Sanitization Report — AI Proofread

> Pre-publication audit of this repo for portfolio release. All real secret
> values are **redacted** in this file. Generated 2026-05-28.

This report is the Phase-1 deliverable. **No edits have been made to the repo
yet.** Phase 2 (sanitization) starts only after you approve the plan at the end
of this file.

---

## 1. Executive summary

| # | Severity | Class | Count | Action |
|---|---|---|---|---|
| 1 | **CRITICAL** | Active live secrets in working tree | 5 | **Rotate** *and* remove from repo |
| 2 | **CRITICAL** | Service-account JSON (private key) | 1 file | Delete + rotate |
| 3 | **HIGH** | Company / parent-org identity | 14 files | Replace with `the Company` / `Acme Screening` |
| 4 | **HIGH** | Internal network: IPs, hostnames, domains | 7 distinct values × many sites | Replace with placeholders |
| 5 | **HIGH** | Real person + email + Windows username | 3 sites | Replace with `<author>` / strip |
| 6 | **HIGH** | Checked-in Python virtualenv (~hundreds MB) | 1 dir | Gitignore + delete from publish |
| 7 | **HIGH** | Proprietary fine-tuned NER weights (~2.5 GB) | 3 dirs | Decision needed — recommend exclude |
| 8 | MEDIUM | Mongo db / collection names with product brand | 6 sites | Generalize |
| 9 | MEDIUM | Auto-generated artifact with absolute paths | 1 file (`coverage.xml`) | Delete + gitignore |
| 10 | MEDIUM | Internal SonarQube project key (UUID) | 1 file | Replace or delete file |
| 11 | LOW | Internal-design doc in Indonesian | 1 file | Decision needed — recommend sanitize+keep |
| 12 | LOW | `.claude/settings.local.json` has venv-path allows | 1 file | Replace or remove |

**PII in test fixtures: clean.** No 16-digit NIK, no real names, no realistic
phones (only repeating `0812345678`). No real emails. Tests use only placeholder
identifiers (`Rizal`, `Nina`, `Acme`).

---

## 2. CRITICAL — secrets to rotate (priority 1)

These are **active, real** credentials sitting in the working tree. Sanitizing
the working tree is not enough — **you must rotate them at the source** because
they were viewable in this repo on your machine and may already exist in remote
git history.

> **In this report I name *what* is leaked and *where*, but I never print the
> actual value.** A length + first-3 / last-2-chars fingerprint is given so you
> can confirm rotation later.

| # | Secret | File | Line | Fingerprint | Action |
|---|---|---|---|---|---|
| 1 | Anthropic API key (live) | `.env` | 13 | `sk-…AA` len 108 | **Revoke** in Anthropic console, regenerate, store in env only |
| 2 | Anthropic API key (duplicate, live) | `secrets/.env` | (env block) | same as #1 | Revoke covers both |
| 3 | MongoDB URI w/ creds + internal IP | `.env` | 20 | `mon…se` len 130 | Rotate Mongo password; if IP exposed externally, audit DB access logs |
| 4 | MongoDB URI duplicate | `secrets/.env` | (env block) | same as #3 | — |
| 5 | API_KEY UUID (auth header) | `.env` + `secrets/.env` | 5 / — | UUID v4 (36 chars) | Rotate (regen UUID + redeploy) |
| 6 | Inline `GOOGLE_SERVICE_ACCOUNT` JSON with **private key** | `.env` | 70 (multi-line) | `{"t…}` len ~1400 | **Critical** — revoke SA key in GCP IAM |
| 7 | Service-account JSON file | `secrets/aiproofreadv01-sa.json` | whole file | Project `protean-mind-466905-i3`, SA `calendar-sync-service@…iam.gserviceaccount.com` | **Revoke SA key**; delete file |
| 8 | Google Sheet ID | `.env` line 65, `secrets/.env`, `README.md` line 174 | — | 44-char Sheet ID | If sheet contains data, audit share settings; rotate Sheet ID is not possible — review what the sheet contains |

> **The Anthropic key, the MongoDB password, and the GCP SA private key must be
> assumed compromised** even if the repo was never pushed publicly. Rotate all
> three before continuing.

---

## 3. Files to remove from the publishable tree

These should never appear in the public repo. The `.gitignore` will be extended
in Phase 5 to cover them.

| Path | Reason | Phase-2 disposition |
|---|---|---|
| `.env` | Live secrets | **delete** from working tree (move to `.env.local` if you want a local copy) |
| `secrets/` (entire directory) | Holds live SA JSON + duplicate .env | **delete** |
| `ai_proofread_221025/` | Checked-in Python venv (~100s MB, leaks lib metadata) | **gitignore + delete** before publish |
| `ner_model/` | ~8.9 GB; mix of public BERT-large + **proprietary fine-tunes** | **decision needed — see §8** |
| `coverage.xml` | Auto-generated artifact, leaks `C:\Users\zaki\…\aitegrity-core\…` paths | **delete + gitignore** |
| `.pytest_cache/` | Local cache | gitignore (already, verify) |
| `__pycache__/` (any) | Local cache | gitignore (already, verify) |
| `.claude/settings.local.json` | Per-machine permission allowlist with hard-coded venv path; not portfolio value | **delete** (or replace with sanitized version) |

---

## 4. Company / brand identity — replacement map

Per your decision (hybrid: prose uses `the Company`, slugs/brands use
`Acme Screening`):

| Found | Replace with | Where |
|---|---|---|
| `AItegrity Core — AI Proofread` (title casing) | `AI Proofread` | README title, CLAUDE.md, docs/PROJECT_OVERVIEW.md, docs/README.md |
| `AItegrity Core` (standalone) | `the Company's proofreading service` (prose) | CLAUDE.md L3, README L1, docs |
| `AItegrity` (slug / inline) | drop or `Acme Screening` | wherever it appears |
| `aitegrity-core` (URL/slug) | `api` (URL prefix) — see below | env.example, README, docs |
| `/aitegrity-core/aiproofread` (BASE_PREFIX) | `/proofread` (or simply leave the API on `/v1/...` which is what the code actually uses) | env.example L43, README L15/L325/L330/L165/L182, all docs |
| `integrity-asia.com` (parent-org domain) | `the-company.example.com` | `.gitlab-ci.yml`, `docs/PROJECT_OVERVIEW.md` |
| `registry.gitlab.integrity-asia.com` | `registry.internal.example.com` | `.gitlab-ci.yml` |
| `ai-services.integrity-asia.com` | `ai-services.example.com` | `.gitlab-ci.yml` |
| `ai-projects/ai_proofread` (GitLab path) | `acme-screening/ai-proofread` | `docs/PROJECT_OVERVIEW.md` L11, `sonar-project.properties` |
| `AI_Proofread` (Mongo DB name) | `proofread` | `services/db.py` L9, env.example, README, docs |
| `AIProofread_Masking_Results` (collection) | `masking_results` | `services/db.py` L14, env.example L87, docs/PIPELINE.md, docs/ENVIRONMENT.md |
| `protean-mind-466905-i3` (GCP project ID) | not in published repo (file deleted) | `secrets/aiproofreadv01-sa.json` — file removed |
| `calendar-sync-service@…iam.gserviceaccount.com` | not in published repo | same |

---

## 5. Internal infrastructure — IP / domain / host replacement

| Found | Replace with | Sites |
|---|---|---|
| `10.30.40.147` (internal Docker registry) | `<internal-registry-ip>` or remove the line | `.gitlab-ci.yml` L42 |
| `10.30.40.155` (CI runner) | `<ci-runner>` or remove tag entirely | `.gitlab-ci.yml` L53 +3 more |
| `10.30.40.162` (MongoDB host) | `<db-host>` | README L152, `.gitlab-ci.yml` (if present) |
| `10.30.112.70:2302` (API service) | `localhost:5000` (curl examples) | README L325, L330 |

---

## 6. Person identity — strip

| File | Line | Found | Replace with |
|---|---|---|---|
| `docs/PROJECT_OVERVIEW.md` | 13 | `C:\Users\zaki\Jack Works\aitegrity-core\git_clone\ai_proofread_v0102\AIProofread_mod_01_221025\` | `<repo-root>` (or remove the row) |
| `docs/PROJECT_OVERVIEW.md` | 14 | `zaky (putra.zakyindras@gmail.com)` | remove the row entirely (it's metadata, not portfolio-useful) |
| `coverage.xml` | 6–7 | `C:\Users\zaki\Jack Works\aitegrity-core\AI Proofread Final\…` | file deleted |

---

## 7. Source files that reference brand / collection names (need edits, no PII)

These are code/config sites that bake brand names into defaults or strings.
Phase-2 edits will be small and mechanical.

| File | What's there | Phase-2 plan |
|---|---|---|
| `services/db.py` L9, L14 | `os.getenv("MONGO_DB", "AI_Proofread")`, `os.getenv("MASKING_RESULTS_DC", "AIProofread_Masking_Results")` | Rename defaults to `proofread` and `masking_results` |
| `services/db.py` L9 | `mongodb://127.0.0.1:27017/AI_Proofread` default URI | Update DB segment to `proofread` |
| `env.example` L43 | `BASE_PREFIX=/aitegrity-core/aiproofread` | Set to empty (the code already routes under `/v1/...`) |
| `env.example` L87 | `MASKING_RESULTS_DC=AIProofread_Masking_Results` | `masking_results` |
| `app/core/config.py` | `TENANT2MODEL` references model dir names like `malay_ner_finetuned_300725_10h50_set01` | Rename to generic e.g. `malay_ner` (model dir naming → §8) |
| `CLAUDE.md` | Entire file references "AItegrity Core" 3× and internal API prefix | Sanitize (it's a useful context-for-Claude file) or remove |
| `README.md` (25 KB) | Many leaks (per §4–6) | **Replaced entirely** in Phase 4 |
| `docs/README.md`, `docs/PROJECT_OVERVIEW.md`, `docs/PIPELINE.md`, `docs/ENVIRONMENT.md`, `docs/ENDPOINTS.md`, `docs/CONVENTIONS.md` | Brand references, internal paths | Mechanical replace per §4; PROJECT_OVERVIEW also needs §6 fixes |
| `docs/superpowers/specs/2026-04-29-masking-results-feature-design.md` | Internal design doc (Indonesian) referencing brand collection | **decision needed — see §8** |
| `.gitlab-ci.yml` | Internal registry IPs/domains, SonarQube creds (env-driven OK), deployment URLs | **decision needed — see §8** |
| `sonar-project.properties` | `sonar.projectKey=ai-projects_ai_proofread_<uuid>` | Replace key with neutral `acme-screening_ai-proofread` or **delete the file** |
| `docker-compose.yml` | References to `AI_Proofread` via env var defaults | Verify after env.example update |
| `tests/test_repositories.py` | Strings `AIProofread_Masking_Results` in tests | Update with collection-name change |

---

## 8. Decisions needed from you before Phase 2

I'll **not edit any of the following** until you choose. These are policy
calls, not technical ones.

### D1. `ner_model/` directory (~8.9 GB)
- **Contents:** `bert_large_cased` (public, 6.4 GB), `indonlu_ner_grit` (~840 MB,
  proprietary fine-tune), `malay_ner_finetuned_300725_10h50_set01` (~1.3 GB,
  proprietary fine-tune), `thai_nner` (~411 MB, unclear license).
- **Recommendation:** **Exclude entire `ner_model/`** from the public repo
  (gitignore + don't ship). The README will document where each model is
  expected at runtime, and link to public base models on HuggingFace. Don't
  publish your fine-tuned weights — that's company IP.
- **Pick one:** (a) exclude entire dir (recommended), (b) ship only public
  `bert_large_cased`, (c) ship everything as-is.

### D2. `docs/superpowers/specs/2026-04-29-masking-results-feature-design.md`
- Internal design doc (Indonesian) showing how the masking-results mirror
  feature was designed. **Portfolio-positive** (shows design thinking) but
  contains brand names + module-level architectural detail.
- **Recommendation:** **Sanitize and keep.** Strip brand + slug references per
  §4–§5; translate the Indonesian sections to English (or leave bilingual with
  a note). Good portfolio artifact.
- **Pick one:** (a) sanitize + keep + translate, (b) sanitize + keep
  Indonesian, (c) remove file.

### D3. `.gitlab-ci.yml`
- 10 KB GitLab CI pipeline targeting internal Docker registry + deployment.
  Recruiters using GitHub won't run it; sanitizing every internal reference is
  work; leaving an untested file is misleading.
- **Recommendation:** **Replace with a minimal CI example** — either a stub
  `.github/workflows/ci.yml` running tests + lint (most portfolio-friendly), or
  a sanitized `.gitlab-ci.yml` that builds + tests but doesn't deploy.
- **Pick one:** (a) GitHub Actions stub (recommended), (b) sanitize the
  existing GitLab CI, (c) remove the CI file entirely.

### D4. `CLAUDE.md`
- It's a Claude Code context file. **Useful** to keep (shows you work
  effectively with AI tools) but currently lists "AItegrity Core" 3× and
  internal API conventions.
- **Recommendation:** **Sanitize and keep.** Replace brand references; trim
  invariants list to ones that make sense without internal context.
- **Pick one:** (a) sanitize + keep (recommended), (b) remove.

### D5. `sonar-project.properties`
- Reveals you use SonarQube and a specific internal project key.
- **Recommendation:** **Delete** (zero portfolio value, and the UUID leaks
  internal tooling state).
- **Pick one:** (a) delete (recommended), (b) keep with neutral project key.

### D6. `.claude/settings.local.json`
- Per-machine permission allowlist that hard-codes `ai_proofread_221025/Scripts/python.exe`.
- **Recommendation:** **Delete** (it's local-only by convention; the path
  pattern can be re-derived per-machine).

### D7. Ambiguous strings I won't touch silently
- `indonlu_ner_grit`, `thai_nner` — model dir names. Are these public model
  names (acceptable) or internal codenames (rename)? Need confirmation.
- `malay_ner_finetuned_300725_10h50_set01` — date-stamped internal training
  artifact name. **Recommend rename** to `malay_ner` (less timeline leakage).
- `protean-mind-466905-i3` (GCP project ID, only in the SA JSON which is being
  deleted) — confirm the SA itself will be revoked, not just the file removed.

---

## 9. Git history — read this carefully

The repo *has* a `.git/` directory (so commits exist). **Sanitizing the working
tree does not remove anything from history.** Any of the live secrets above —
the Anthropic key, the Mongo password, the GCP SA private key — likely sit in
one or more older commits.

> **Two options, ranked safest first:**
>
> 1. **(Recommended) Fresh history.** Create a brand-new repo, copy the
>    sanitized working tree in, and commit once. Old commits never leave your
>    machine. Concrete steps will be in the final deliverables (Phase 6).
> 2. **History rewrite (`git filter-repo` / BFG).** Preserves authorship
>    timeline but is fragile — one missed pattern stays public *forever* in old
>    commits. Not recommended for portfolio publication.
>
> Push only after rotating secrets (§2) regardless of which option you pick.

---

## 10. Phase-2 execution plan (what I'll do once you approve)

In order:

1. **Delete** `.env`, `secrets/`, `coverage.xml`, `.claude/settings.local.json`
   from the working tree.
2. **Update `.gitignore`** to cover `.env*`, `secrets/`, `ai_proofread_221025/`,
   `coverage.xml`, `.pytest_cache/`, `__pycache__/`, `ner_model/` (per D1),
   `.claude/settings.local.json`.
3. **Rewrite `env.example`** as a single sanitized file (sync keys present in
   `.env` but missing from example: `MASKING_RESULTS_FEATURE`,
   `MASKING_RESULTS_DC`, `TEXT_SEMANTIC_*`, `LLM_SEMANTIC_VALIDATION`; remove
   keys present in example but not used: e.g. unify with `GOOGLE_SA_JSON_PATH`
   path-based pattern; set `BASE_PREFIX=` empty).
4. **Sanitize source files** per §4–§7 mapping. Surgical edits, brand-name only.
5. **Sanitize / replace** the policy files per D1–D6 decisions.
6. **Replace `README.md`** entirely with the 12-section portfolio version
   (Phase 4).
7. **Add `LICENSE`** (MIT).
8. **Final security sweep** — regex pass for secret-shaped strings and any
   missed `aitegrity` / `integrity-asia` / `10.30.` / `Users\zaki` patterns.
9. **Hand you** the final-deliverables packet (Phase 6).

---

## 11. Approval checklist

Please confirm or override the recommendations in §8 (D1–D7) and confirm:

- [ ] You will rotate the Anthropic API key, MongoDB password, GCP SA key, and
      `API_KEY` UUID **before** publishing.
- [ ] You'll go with **fresh-history publication** (single squashed initial
      commit in a new repo).
- [ ] You're OK with my proposed naming map in §4 (`the Company` / `Acme
      Screening` / `proofread` / `masking_results`).
- [ ] D1 (ner_model/): **exclude entire dir** (default) or other.
- [ ] D2 (design spec): **sanitize + keep + translate** (default) or other.
- [ ] D3 (CI file): **GitHub Actions stub** (default) or other.
- [ ] D4 (CLAUDE.md): **sanitize + keep** (default) or other.
- [ ] D5 (sonar properties): **delete** (default) or other.
- [ ] D6 (`.claude/settings.local.json`): **delete** (default) or other.
- [ ] D7 (model dir names): rename `malay_ner_finetuned_300725_10h50_set01` →
      `malay_ner`? confirm `indonlu_ner_grit` / `thai_nner` are public-safe or
      flag to rename.

Reply with confirmations / overrides and I'll proceed with Phase 2.
