# Project Overview

> **Last updated:** 2026-04-28 (branch `task/regex-reformatting-improvement03`, commit `a1cd78c6`; Claude model bumped to `claude-sonnet-4-6`)

## 1. Identity

| Field | Value |
|---|---|
| Project | AItegrity Core — AI Proofread (PII Masking + LLM + Reverse HTML) |
| Purpose | Safety-wrapped LLM proofreading on HTML / plain-text payloads |
| Repository | `git@gitlab.integrity-asia.com:ai-projects/ai_proofread.git` |
| Default integration branch | `Staging` |
| Local path | `C:\Users\zaki\Jack Works\aitegrity-core\git_clone\ai_proofread_v0102\AIProofread_mod_01_221025` |
| Git user (owner of current branches) | zaky (`putra.zakyindras@gmail.com`) |
| Deployment | Dockerized; Gunicorn for prod. CI: `.gitlab-ci.yml`. SonarQube via `sonar-project.properties`. |

## 2. Tech stack

- **Web:** Flask app factory in `app/app.py`. Blueprints per module under `app/modules/`. Gunicorn entrypoint via `wsgi.py`.
- **Validation:** Pydantic DTOs (`extra = "forbid"`). Strict, reject-unknown-field semantics.
- **PII detection / masking:** `piiregex` (email + credit card), `libphonenumber` (`PhoneNumberMatcher`), custom regex patterns, multilingual NER (HuggingFace `transformers` weights on disk).
- **LLM:** Anthropic Claude SDK; default model `claude-sonnet-4-6` (`ANTHROPIC_MODEL`).
- **Language detection:** Lingua first; Claude as fallback for low-confidence cases.
- **Persistence:** MongoDB (`pymongo`) — see [PIPELINE.md §6](./PIPELINE.md#6-persistence).
- **QA push:** Google Sheets API via service account.
- **Container:** `Dockerfile` + `docker-compose.yml`.

## 3. Repo layout

```
AIProofread/
├─ app/
│   ├─ app.py                    # Flask app factory: create_app()
│   ├─ core/
│   │   ├─ config.py             # Config class — single source of truth for env-driven settings
│   │   ├─ ratelimit.py          # enforce_rps sliding-window limiter (used in every blueprint)
│   │   ├─ validation.py         # validate_and_scan, is_symbol_only_text, validate_locale_tenant, error helpers
│   │   ├─ lang_detect.py        # validate_language_locale (Lingua + Claude fallback)
│   │   ├─ text_semantic.py      # validate_semantic_text (min chars/words / "meaningful" check)
│   │   ├─ swagger.py            # OpenAPI / Swagger init
│   │   ├─ token_utils.py        # auth & token helpers
│   │   └─ version.py            # version_info() for /meta/version
│   └─ modules/                  # feature modules; each has dto/repositories/routes/services
│       ├─ htmlmask/             # POST /htmlmask/freeze, POST /htmlmask/reverse
│       ├─ masking/              # POST /masking/mask, POST /masking/unmask
│       ├─ ner/                  # POST /ner/mask
│       ├─ proofread/            # POST /proofread (one-hit with full pipeline)
│       ├─ reformat/             # POST /reformat
│       ├─ result_analyse/       # GET/POST /v1/result-analyse/* (Google Sheets QA)
│       └─ meta/                 # GET /meta/version, GET /meta/healthz
│   └─ repositories/
│       └─ base.py               # common base repository class
├─ services/                     # cross-module shared services
│   ├─ masking.py                # 3-layer PII masking: piiregex / libphonenumber / patterns
│   ├─ phonefmt.py               # phone reformatting (Indonesia + intl via WORLD_CC)
│   ├─ phone_world_cc.py         # country-code → region map for intl detection
│   ├─ llm.py                    # Claude client + prompt orchestration
│   ├─ ner.py                    # NER model load + inference per tenant
│   ├─ subjectfmt.py             # subject/text formatting helpers
│   ├─ htmltags.py               # HTML freeze/reverse helpers
│   ├─ db.py                     # Mongo client + summary upserts + WIB timestamps
│   ├─ gsheets_client.py         # Google Sheets push for QA
│   └─ utils.py                  # require_headers, locale_to_region, etc.
├─ llm_prompt/                   # HTML/markdown prompts
│   └─ plain/                    # plain-text variants (selected when format=plain)
├─ ner_model/                    # local NER weights
│   ├─ bert_large_cased/
│   ├─ indonlu_ner_grit/
│   ├─ malay_ner_finetuned_300725_10h50_set01/
│   └─ thai_nner/
├─ secrets/                      # service account JSON (gitignored)
├─ tests/                        # pytest suite (conftest, unit tests across core + modules)
├─ Dockerfile, docker-compose.yml, wsgi.py
├─ requirement_aiproofread.txt, requirements_base.txt, requirements_ml.txt, requirements_test.txt
├─ .gitlab-ci.yml, sonar-project.properties
├─ pytest.ini, .coveragerc, coverage.xml
├─ env.example, .env (gitignored)
├─ CLAUDE.md                     # auto-loaded Claude context (this folder's parent)
└─ README.md                     # original product README (partly stale; see CLAUDE.md note)
```

## 4. Tenants and locales (truth: code, not README)

| | Active in code | README claims |
|---|---|---|
| Tenants | `indonesia`, `malaysia`, `thailand` | same |
| Locales (DTO) | `en`, `id`, `ms` | `en`, `id`, `th`, `my` (stale) |
| Tenant → NER model | see `Config.TENANT2MODEL` | implied only |

`Config.TENANT2MODEL`:
- `indonesia` → `indonlu_ner_grit`
- `malaysia`  → `malay_ner_finetuned_300725_10h50_set01`
- `thailand`  → `thai_nner`

## 5. Branch strategy and release

- **Trunk:** `Staging`. Feature work merged in via merge requests on GitLab.
- **Feature branches:** `task/<slug>` (e.g. `task/regex-reformatting-improvement03`, `task/keyword-data-masking`, `task/phoneDate_reforma_american`).
- **Sync pattern:** merge `Staging` into feature branches frequently before MR.
- **CI:** runs on default-branch pushes (see `.gitlab-ci.yml`); Sonar gate via `sonar-project.properties`.
- **Versioning:** every response carries `X-App-Version`, `X-API-Version`, `X-Git-SHA` headers, populated from `Config`.

## 6. Recent / in-flight work

> Use `git log --oneline -20` for the authoritative list. Snapshot:

| Branch / commit | What it changes |
|---|---|
| `task/regex-reformatting-improvement03` (HEAD `a1cd78c6`) | `mask_with_patterns`: adds `KEYWORD` regex for double-quoted text. `_RE_ID_MOBILE` tightened so trailing `.` / `,` aren't swallowed; `mobile_sub` asserts `08` prefix + 10–12 total digits. |
| `task/regex-reformatting-improvement01..02` | Precursor regex iterations. |
| `task/keyword-double-apostrophe`, `task/keyword-data-masking` | Hashtag / keyword masking groundwork. |
| `task/phoneDate_reforma_american`, `task/phonenumberdateformatpart2`, `task/phonereformatting_upgrade` | Prior phone + date reformatting iterations and country-code algorithm upgrades. |

## 7. Local run (Docker)

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps -a
```

Without Docker (dev only):

```bash
python -m venv ai_proofread_221025   # already present in repo for some setups
source ai_proofread_221025/Scripts/activate   # Windows bash
pip install -r requirements_base.txt -r requirements_ml.txt -r requirement_aiproofread.txt
python wsgi.py        # or: flask --app app.app run
```

Defaults: host `0.0.0.0`, port `5000` (overridden via `.env` `PORT=2302` for the Docker setup).

## 8. Tests

- Suite under `tests/`, run via `pytest` (config in `pytest.ini`, coverage in `.coveragerc`).
- See `tests/conftest.py` for fixtures. Coverage XML is committed at repo root for Sonar ingestion.

## 9. Doc maintenance contract

This `docs/` set must be kept in sync with reality. After any change to:

- module structure, service files, or new/removed modules → update [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)
- pipeline stages, masking layers, LLM call shape, unmask / reformat logic → update [PIPELINE.md](./PIPELINE.md)
- HTTP routes, headers, request/response shapes → update [ENDPOINTS.md](./ENDPOINTS.md)
- env variables, defaults, security toggles → update [ENVIRONMENT.md](./ENVIRONMENT.md)
- invariants, regex constraints, conventions → update [CONVENTIONS.md](./CONVENTIONS.md)

…and bump the `Last updated` date at the top of each touched file.

When `README.md` and the active code disagree, **prefer the code**. Reconcile in the same change.
