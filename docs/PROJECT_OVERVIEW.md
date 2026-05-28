# Project Overview

> **Last updated:** 2026-05-28 (portfolio sanitization pass)

## 1. Identity

| Field | Value |
|---|---|
| Project | AI Proofread — safety-wrapped LLM proofreading for HTML / plain-text payloads |
| Purpose | Run LLM proofreading on customer text without ever sending PII to the LLM |
| Deployment | Dockerized; Gunicorn for prod. See `Dockerfile`, `docker-compose.yml`, and `.github/workflows/ci.yml`. |

> This is a sanitized portfolio version of an internal service. Company-specific
> branding, identifiers, and client data have been removed; technical content is
> preserved.

## 2. Tech stack

- **Web:** Flask app factory in `app/app.py`. Blueprints per module under `app/modules/`. Gunicorn entrypoint via `wsgi.py`.
- **Validation:** Pydantic DTOs (`extra = "forbid"`). Strict, reject-unknown-field semantics.
- **PII detection / masking:** `piiregex` (email + credit card), `libphonenumber` (`PhoneNumberMatcher`), custom regex patterns, multilingual NER (HuggingFace `transformers` weights on disk).
- **LLM:** Anthropic Claude SDK; default model `claude-sonnet-4-6` (`ANTHROPIC_MODEL`).
- **Language detection:** Lingua first; Claude as fallback for low-confidence cases.
- **Persistence:** MongoDB (`pymongo`) — see [PIPELINE.md §6](./PIPELINE.md#6-persistence).
- **Optional QA push:** Google Sheets API via service account.
- **Container:** `Dockerfile` + `docker-compose.yml`.

## 3. Repo layout

```
ai-proofread/
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
├─ ner_model/                    # local NER weights (NOT shipped — download separately, see README)
│   ├─ bert_large_cased/
│   ├─ indonlu_ner_grit/
│   ├─ malay_ner/
│   └─ thai_nner/
├─ tests/                        # pytest suite (conftest, unit tests across core + modules)
├─ Dockerfile, docker-compose.yml, wsgi.py
├─ requirement_aiproofread.txt, requirements_base.txt, requirements_ml.txt, requirements_test.txt
├─ pytest.ini, .coveragerc
├─ .env.example, .env (gitignored)
├─ CLAUDE.md                     # auto-loaded Claude Code context
└─ README.md
```

## 4. Tenants and locales (truth: code)

| | Active in code |
|---|---|
| Tenants | `indonesia`, `malaysia`, `thailand` |
| Locales (DTO) | `en`, `id`, `ms` |
| Tenant → NER model | see `Config.TENANT2MODEL` |

`Config.TENANT2MODEL`:
- `indonesia` → `indonlu_ner_grit`
- `malaysia`  → `malay_ner`
- `thailand`  → `thai_nner`

## 5. Local run (Docker)

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps -a
```

Without Docker (dev only):

```bash
python -m venv .venv
source .venv/bin/activate            # Linux/macOS
.venv\Scripts\activate               # Windows PowerShell
pip install -r requirements_base.txt -r requirements_ml.txt -r requirement_aiproofread.txt
python wsgi.py                       # or: flask --app app.app run
```

Defaults: host `0.0.0.0`, port `5000` (overridden via `.env` `PORT=2302` for the
Docker setup).

## 6. Tests

- Suite under `tests/`, run via `pytest` (config in `pytest.ini`, coverage in
  `.coveragerc`).
- See `tests/conftest.py` for fixtures.

## 7. Doc maintenance contract

This `docs/` set must be kept in sync with the code. After any change to:

- module structure, service files, or new/removed modules → update this file
- pipeline stages, masking layers, LLM call shape, unmask / reformat logic → update [PIPELINE.md](./PIPELINE.md)
- HTTP routes, headers, request/response shapes → update [ENDPOINTS.md](./ENDPOINTS.md)
- env variables, defaults, security toggles → update [ENVIRONMENT.md](./ENVIRONMENT.md)
- invariants, regex constraints, conventions → update [CONVENTIONS.md](./CONVENTIONS.md)

…and bump the `Last updated` date at the top of each touched file.
