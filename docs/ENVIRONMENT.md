# Environment Variables

> **Last updated:** 2026-04-29 (added `MASKING_RESULTS_FEATURE` / `MASKING_RESULTS_DC` for masking-model dataset mirror)
>
> Truth source: `app/core/config.py` and `env.example`. Where the README's table disagrees with code, the code wins.

`.env` is loaded automatically at app start (`python-dotenv`). The repo's `env.example` is the template — copy to `.env` for local dev. `.env` is gitignored; **never** commit secrets.

## 1. API access

| Variable | Default (code) | Notes |
|---|---|---|
| `API_KEY` / `API_KEYS` | (none) | Comma-separated list. `services/utils.py::_expected_api_keys()` reads `API_KEYS` first, then `API_KEY`. Validated with `hmac.compare_digest`. |
| `FLASK_ENV` | (unset) | `production` or `development`. |
| `FLASK_DEBUG` | `1` if unset (in `app.py` startup) | `0` / `1`. |
| `PORT` | `5000` (Flask), `2302` (compose convention) | Set in `wsgi.py` / `app.py`. |
| `HOST` | `0.0.0.0` | Set in `app.py` startup. |

## 2. Versioning

| Variable | Default (code) | Notes |
|---|---|---|
| `API_PREFIX` | `""` | Empty → URL prefix becomes `/{API_VERSION}`. |
| `API_VERSION` | `v1` | Mount point for all blueprints. |
| `APP_VERSION` | `0.1.0` | Surfaced in `X-App-Version` response header. |
| `BUILD` | `""` | CI-injected. |
| `GIT_SHA` | `""` | CI-injected; surfaced in `X-Git-SHA`. |
| `BUILD_AT` | `""` | CI-injected. |

## 3. Anthropic Claude (LLM)

| Variable | Default (code) | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | Pattern `^sk-ant-[A-Za-z0-9_-]{20,}$` (per `.env.example`). |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model used by `services/llm.py`. Use the alias exactly — never append a date suffix (the alias is the complete ID). |
| `ANTHROPIC_MAX_TOKENS` | (env-driven; no code default visible in `Config`) | Max output tokens per Anthropic call. |
| `MAX_INPUT_TOKEN` | `0` (= unlimited) | Read by `Config.MAX_INPUT_TOKEN`. Over-limit input → 400 `input_too_large`. |
| `LLM_TEMPERATURE` | (env-driven) | Float 0..1. |
| `LLM_LANG_VALIDATION` | `1` (per README) | Toggles Claude-fallback in language guard (`app/core/lang_detect.py`). |

## 4. Auto-chain switches

| Variable | `Config` default | Effect |
|---|---|---|
| `AUTO_CHAIN_LLM` | `1` | Enable LLM stage in pipelines that consult this. |
| `AUTO_CHAIN_UNMASK` | `1` | Enable unmask stage. |
| `AUTO_CHAIN_REFORMAT` | `1` | Enable reformat stage. |

Truthy values: `1`, `true`, `yes`. Anything else → off.

## 5. MongoDB

| Variable | Default (code) | Notes |
|---|---|---|
| `MONGO_URI` | (none) | Full URI incl. credentials and `authSource=admin`. |
| `MONGO_DB` | `proofread` | Database name. |
| `MASKING_RESULTS_DC` | `masking_results` | Destination collection for the 9-field whitelist mirror (see §13a). |

Initialised by `services/db.py::init_db()` at app startup.

## 6. Rate limit

| Variable | `Config` default | Notes |
|---|---|---|
| `RATE_LIMIT_RPS` | `20` | Max requests per window. |
| `RATE_LIMIT_WINDOW_SEC` | `60` | Window length in seconds. `Config.RATE_LIMIT_WINDOW` reads this. |

## 7. NER and prompts

| Variable | Default (code) | Notes |
|---|---|---|
| `NER_MODEL_DIR` | (env-driven; container path) | `/app/ner_model` in Docker. |
| `LLM_PROMPT_DIR` | (env-driven) | HTML/markdown prompts. |
| `LLM_PROMPT_DIR_PLAIN` | (env-driven) | Plain-text prompts. |
| `HOST_NER_MODEL_DIR` | (env-driven) | Host path used by docker-compose volume mount. |
| `HOST_LLM_PROMPT_DIR` | (env-driven) | Host path. |
| `HOST_LLM_PROMPT_DIR_PLAIN` | (env-driven) | Host path. |

`Config.NER_BASE_DIR = <repo>/ner_model` is the package-relative fallback when env is unset (computed in `app/core/config.py`).

`Config.TENANT2MODEL` (hard-coded mapping):

| Tenant | NER subdir |
|---|---|
| `indonesia` | `indonlu_ner_grit` |
| `malaysia`  | `malay_ner` |
| `thailand`  | `thai_nner` |

## 8. GPU

| Variable | Default | Notes |
|---|---|---|
| `USE_GPU` | `1` | `0` forces CPU. Auto-detection in `services/ner.py`. |

## 9. Result analysis (Google Sheets QA)

| Variable | Default | Notes |
|---|---|---|
| `RESULT_ANALYZE` | `INACTIVE` (per `.env.example`) | `ACTIVATE` enables the after-final hook in `ProofreadRepo`; `INACTIVE` disables. |
| `GOOGLE_SHEET_ID` | (none) | Target sheet, ~44-char base62. |
| `RESULT_ANALYZE_SHEET_TAB` | (none) | Tab name within the sheet. |
| `GOOGLE_SA_JSON_PATH` | (none) | Path inside container to the service account JSON. |
| `HOST_SECRETS_DIR` | (none) | Host-side secrets dir for compose volume. |

## 10. Language guard

| Variable | `Config` default | Notes |
|---|---|---|
| `LANGUAGE_MIN_CHARS` | `80` (see `.env.example`) | Below this → unreliable detection. |
| `LANGUAGE_CONFIDENCE_MIN` | `0.85` (see `.env.example`) | Auto-accept threshold. |
| `LLM_LANG_VALIDATION` | `1` | Toggles Claude fallback on low confidence. |

## 11. Semantic-text guard (not in README)

| Variable | `Config` default | Notes |
|---|---|---|
| `TEXT_SEMANTIC_MIN_CHARS` | `40` | Below → 422 `TEXT_TOO_SHORT`. |
| `TEXT_SEMANTIC_MIN_WORDS` | `10` | Below → 422 `TEXT_TOO_FEW_WORDS`. |
| `LLM_SEMANTIC_VALIDATION` | `1` | Toggles the semantic check. |

Wired in `app/core/text_semantic.py::validate_semantic_text` and called from `proofread/routes.py`.

## 12. Security toggles (off by default — not in README)

| Variable | `Config` field | Default | Effect |
|---|---|---|---|
| `SQL_INJECTION` | `DETECT_SQLI` | off | Rejects payloads with SQLi-shaped patterns. |
| `HTML_FORMAT` | `DETECT_HTML` | off | Rejects raw HTML in `data` unless `format` is `html` or `markdown`. |
| `REJECT_SYMBOL_ONLY` | `REJECT_SYMBOL_ONLY` | off | Rejects symbol-/digit-only payloads. |

Truthy → on. Falsy values: `0`, `false`, `off`, `no`, `""`.

## 13. Misc

| Variable | Default | Notes |
|---|---|---|
| `DEFAULT_EN_REGION` | `US` | Used by `services/utils.py::LOCALE_TO_REGION` for the `en` locale. |

## 13a. Data Masking Model Improvement

Optional dataset mirror for future masking-model training. When enabled, the `/v1/proofread` flow writes a 9-field subset of each `masking_output` document to a separate collection.

| Variable | `Config` field | Default | Effect |
|---|---|---|---|
| `MASKING_RESULTS_FEATURE` | `MASKING_RESULTS_FEATURE` | OFF | **Strict** parse — only literal `ON` (case-insensitive) enables. Any other value, typo, empty, or unset → OFF. |
| `MASKING_RESULTS_DC` | (read in `services/db.py`) | `masking_results` | Mongo collection name for the mirror. |

Whitelist (hardcoded in `app/modules/proofread/repositories.py::_MASKING_RESULTS_FIELDS`):

```
_id, report_id, toc_type, tenant, locale, message_01, layers, created_at, created_at2
```

Behaviour notes:
- **Scope:** only the `/v1/proofread` flow (jalur B). Endpoint `/v1/masking/mask` standalone (jalur A) is not mirrored.
- **`_id`:** reused from source (pre-generated `ObjectId()` in `ProofreadRepo.save_masking`) — gives a 1:1 trace between `masking_output` and the mirror.
- **Timestamps:** `created_at` and `created_at2` are copied from the source document (snapshot consistency).
- **Failure isolation:** mirror insert goes through `safe_insert`, so any Mongo error (or `col_masking_results = None`) is silently logged and never propagates to the response.
- **Indexes (auto-created in `init_db`):** `(report_id, created_at DESC)` and `(tenant, created_at DESC)`. Non-unique.

## 14. Files and where they live

- **Template:** `.env.example` (committed). Not auto-loaded.
- **Active values:** `.env` (gitignored). Auto-loaded at `app.py` import via `load_dotenv()`.
- **Secrets dir:** `secrets/` (gitignored). Holds Google service-account JSON when QA-push to Sheets is enabled.
