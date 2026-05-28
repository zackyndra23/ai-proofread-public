# 🧠 AItegrity Core — AI Proofread (PII Masking + LLM + Reverse HTML)

Production-ready, dockerized service for safely running **LLM proofreading** on HTML/text with **multi-layer PII masking**, unmasking, reformatting, and QA result analysis.  
Supports an **HTML Tag Freeze system** + **one-hit endpoint** that returns final **HTML** while persisting a full JSON summary to MongoDB and optionally pushing QA results to Google Sheets.

---

## ✨ Highlights
- 🔒 **Multi-layer PII masking** (regex, libphonenumber, patterns, multilingual NER).  
- 🌍 **Tenant / locale aware** (EN/ID/MY/TH models; per-tenant overrides).  
- 🤖 **Claude LLM** with strict **token-preservation** (no token loss / reordering).
- 🧱 **Input Token Limiter** → configurable `MAX_INPUT_TOKEN` to prevent large payloads.  
- 🔁 **Unmasking** & 📱 **Reformatting** (e.g., Indonesian phone numbers).  
- 🧩 **HTML Tag Freeze** → `[TEXT_xx]`, `[TABLE_xx]` placeholders + skeleton kept intact.  
- 🧷 **One-hit endpoint** (`POST /aitegrity-core/aiproofread`) returns **HTML**; `?format=json` returns JSON.  
- 🗃️ **MongoDB summaries** with **WIB** timestamps (`created_at_wib`, `created_at2`) in addition to UTC.  
- 🛡️ **Rate limiting** with proper `429` + `Retry-After`.  
- 🈲 **Language–Locale Guard** — automatic language detection (Lingua) that **blocks** requests when the `data` language doesn’t match the requested `locale`; **Claude** is used only as a fallback for low-confidence cases.
- ⚡ **CUDA acceleration** (GPU autodetect; override via `.env`).  
- 📊 **QA Automation**: optional `result_analyse` module pushes results into Google Sheets for QA review.  
- 🐳 **Docker + Gunicorn** for production.

---

## 📦 Project Structure
```
AIProofread/
│
├─ app/
│   ├─ __init__.py                # App package initializer
│   ├─ app.py                     # Flask app entry point
│   └─ core/                      # Core utilities and configuration
│        ├─ __init__.py
│        ├─ config.py             # Load env, configs
│        ├─ ratelimit.py          # Rate limiting logic
│        ├─ validation.py         # payload validation & lightweight security scanning
│        ├─ lang_detect.py        # Language–Locale Guard (Lingua + Claude fallback)
│        ├─ swagger.py            # API documentation / OpenAPI
│        ├─ token_utils.py        # Token & auth helpers
│        └─ version.py            # App version info
│
│   └─ modules/                   # Feature-based modules
│        ├─ htmlmask/             # Handles HTML freeze/reverse process
│        │    ├─ __init__.py
│        │    ├─ dto.py           # Request/response DTOs
│        │    ├─ repositories.py  # Persistence for HTML freeze/reverse
│        │    ├─ routes.py        # Routes for HTML freeze/reverse
│        │    └─ services.py      # Core services for HTML masking
│        ├─ masking/              # PII masking/unmasking stage
│        │    ├─ __init__.py
│        │    ├─ dto.py
│        │    ├─ repositories.py
│        │    ├─ routes.py
│        │    └─ services.py
│        ├─ meta/                 # Meta endpoints (e.g., health/version)
│        │    ├─ __init__.py
│        │    └─ routes.py
│        ├─ ner/                  # NER model usage
│        │    ├─ __init__.py
│        │    ├─ dto.py
│        │    ├─ repositories.py
│        │    ├─ routes.py
│        │    └─ services.py
│        ├─ proofread/            # LLM proofreading stage
│        │    ├─ __init__.py
│        │    ├─ dto.py
│        │    ├─ repositories.py
│        │    ├─ routes.py
│        │    └─ services.py
│        ├─ reformat/             # Phone formatting and cleanup stage
│        │    ├─ __init__.py
│        │    ├─ dto.py
│        │    ├─ repositories.py
│        │    ├─ routes.py
│        │    └─ services.py
│        ├─ result_analyse/       # QA automation (Google Sheets integration)
│        │    ├─ __init__.py
│        │    ├─ dto.py
│        │    ├─ repositories.py
│        │    ├─ routes.py
│        │    └─ services.py
│        └─ __init__.py
│
│   └─ repositories/
│        └─ base.py               # Base repository class
│
├─ llm_prompt/                    # Prompt templates for LLM
│   ├─ address_check_prompt.txt
│   ├─ employment_check_prompt.txt
│   ├─ general_prompt.txt
│   ├─ reference_check_prompt.txt
│   └─ plain/                     # Plain text format prompts
│        ├─ address_check_prompt.txt
│        ├─ employment_check_prompt.txt
│        ├─ general_prompt.txt
│        ├─ reference_check_prompt.txt
│        └─ language_guard_prompt.txt
│
├─ ner_model/                     # Local NER models
│   ├─ bert_large_cased/
│   ├─ indonlu_ner_grit/
│   ├─ malay_ner_finetuned_300725_10h50_set01/
│   └─ thai_nner/
│
├─ services/                      # Shared services across modules
│   ├─ __init__.py
│   ├─ masking.py                 
│   ├─ ner.py
│   ├─ llm.py
│   ├─ utils.py
│   ├─ phonefmt.py
│   ├─ db.py                       # MongoDB client, summary storage
│   ├─ gsheets_client.py           # Google Sheets integration for QA
│   └─ htmltags.py
│
├─ secrets/                        # Sensitive credentials (ignored in git)
│   └─ aiproofreadv01-sa.json
│
├─ .dockerignore
├─ .env                            # Environment variables (see below)
├─ .gitignore
├─ .gitlab-ci.yml
├─ docker-compose.yml
├─ Dockerfile
├─ README.md
├─ requirement_aiproofread.txt
├─ requirements_base.txt
├─ requirements_ml.txt
├─ sonar-project.properties
└─ wsgi.py
```

---

## ⚙️ Environment (.env)
Set these before running:

```
Below is the complete list of supported environment variables for **AIProofread_mod_01**, including their description, purpose, and example values.

| Variable | Description | Example |
|-----------------------------|-----------------------------------------------------------------------|---------------------------------------------------------------------------|
| `API_KEY`                   | Unique API access key (UUID v4)                                       | `cdcd0b30-334a-45e6-a340-488b91b96e1d`                                    |
| `FLASK_ENV`                 | Flask environment                                                     | `production` / `development`                                              |
| `FLASK_DEBUG`               | Enable Flask debug mode                                               | `0` / `1`                                                                 |
| `PORT`                      | Server port                                                           | `2302`                                                                    |
| `ANTHROPIC_API_KEY`         | API key for Anthropic Claude                                          | *(secret)*                                                                |
| `ANTHROPIC_MODEL`           | Model name used by Anthropic API                                      | `claude-sonnet-4-6`                                                       |
| `ANTHROPIC_MAX_TOKENS`      | Maximum token limit per request                                       | `2048`                                                                    |
| **`MAX_INPUT_TOKEN`**       | **Maximum allowed tokens for input payload** (`0` = unlimited)        | `500`                                                                     |
| `LLM_TEMPERATURE`           | Sampling temperature (0–1)                                            | `0`                                                                       |
| `MONGO_URI`                 | MongoDB connection URI                                                | `mongodb://integrity:1nt2024UM0ng60@10.30.40.162:27017/?authSource=admin` |
| `MONGO_DB`                  | Database name                                                         | `AI_Proofread`                                                            |
| `AUTO_CHAIN_LLM`            | Enable LLM auto-chain execution                                       | `1`                                                                       |
| `AUTO_CHAIN_UNMASK`         | Enable unmasking auto-chain                                           | `1`                                                                       |
| `AUTO_CHAIN_REFORMAT`       | Enable reformatting auto-chain                                        | `1`                                                                       |
| `NER_MODEL_DIR`             | Directory for NER models inside container                             | `/app/ner_model`                                                          |
| `LLM_PROMPT_DIR`            | Directory for LLM prompts                                             | `/llm_prompt`                                                             |
| `LLM_PROMPT_DIR_PLAIN`      | Directory for plain-format prompts                                    | `/llm_prompt/plain`                                                       |
| `HOST_NER_MODEL_DIR`        | (Optional) Host path override for NER models                          | `./ner_model`                                                             |
| `HOST_LLM_PROMPT_DIR`       | (Optional) Host path override for LLM prompts                         | `./llm_prompt`                                                            |
| `HOST_LLM_PROMPT_DIR_PLAIN` | (Optional) Host path override for plain prompts                       | `./llm_prompt/plain`                                                      |
| `RATE_LIMIT_RPS`            | Max requests per second per user                                      | `20`                                                                      |
| `RATE_LIMIT_WINDOW_SEC`     | Rate limit window duration (seconds)                                  | `1`                                                                       |
| `BASE_PREFIX`               | Base API path prefix                                                  | `/aitegrity-core/aiproofread`                                             |
| `API_VERSION`               | API version                                                           | `v1`                                                                      |
| `API_PREFIX`                | API URL prefix (if any)                                               | *(empty or `/`)*                                                          |
| `APP_VERSION`               | Application version                                                   | `0.1.0`                                                                   |
| `BUILD`                     | Build identifier (injected by CI)                                     | *(auto)*                                                                  |
| `GIT_SHA`                   | Git commit hash (injected by CI)                                      | *(auto)*                                                                  |
| `BUILD_AT`                  | Build timestamp                                                       | *(auto)*                                                                  |
| `USE_GPU`                   | GPU usage flag (1 = enable, 0 = force CPU)                            | `1`                                                                       |
| `RESULT_ANALYZE`            | Enable result analysis pipeline                                       | `ACTIVATE` / `INACTIVE`                                                   |
| `GOOGLE_SHEET_ID`           | Target Google Sheet ID for analysis                                   | `1e1dIqVVVm0LqVvhYby2dDxQh3tQ4arJ3keTEip_jJNw`                            |
| `RESULT_ANALYZE_SHEET_TAB`  | Sheet tab name for analysis output                                    | `V01_Plain_Analysis_Part02`                                               |
| `GOOGLE_SA_JSON_PATH`       | Path to Google Service Account JSON                                   | `./secrets/aiproofreadv01-sa.json`                                        |
| `LANGUAGE_MIN_CHARS`        | Minimum text length for reliable detection                            | `80`                                                                      |
| `LANGUAGE_CONFIDENCE_MIN`   | Acceptance threshold (0..1) for auto-accept language detection        | `0.85`                                                                    |
| `LLM_LANG_VALIDATION`       | Enable Claude fallback on low-confidence detection (`1` on, `0` off)  | `1`                                                                       |
```

> `BASE_PREFIX` controls the prefix of all endpoints (default examples below use `/aitegrity-core/aiproofread`).
> With `RESULT_ANALYZE=ACTIVATE`, the `result_analyse` module will automatically push proofread results into Google Sheets for QA review. Set to `INACTIVE` to disable.
> `MAX_INPUT_TOKEN` prevents requests that exceed a given token count for fields like `"data"`.  
> If input text exceeds this value, the API returns an HTTP **400 Bad Request** with error code `input_too_large`.

---


## 🧱 Input Token Limiter

### Purpose
To safeguard system performance and avoid costly or runaway LLM calls by rejecting overly long inputs.

---

## ✅ Payload & Validation (Strict Schema)

The `/v1/proofread` endpoint uses **strict validation** through a Pydantic DTO (`ProofreadRequest`). Only defined fields are allowed; unexpected fields trigger an HTTP 400 error.

### Request Body Example
```json
{
  "type_of_check": "general",
  "tenant": "indonesia",
  "locale": "id",
  "format": "plain",
  "data": "Halo Rizal, no saya 09281819.",
  "report_id": "94d579ec-11b6-48fb-a999-f0859bf7c09c"
}
```

### Allowed Fields and Rules
| Field | Type | Required | Allowed Values |
|--------|------|-----------|----------------|
| `type_of_check` | string | optional (default `general`) | any non‑empty string |
| `tenant` | string | ✅ | `indonesia`, `thailand`, `malaysia` |
| `locale` | string | ✅ | `en`, `id`, `th`, `my` |
| `format` | string | ✅ | `plain`, `html`, `markdown` |
| `data` | string | ✅ | non‑empty string |
| `report_id` | string | optional | any |

> Fields other than these will be rejected (`HTTP 400`), and invalid `tenant` or `locale` values will return a validation error.

### Example Error Responses
**Invalid Locale**
```json
{"error":"validation_error","detail":[{"loc":["locale"],"msg":"unexpected value; permitted: 'en', 'id', 'th', 'my'","type":"value_error.const"}]}
```

**Unknown Field**
```json
{"error":"validation_error","detail":[{"loc":[],"msg":"extra fields not permitted","type":"value_error.extra"}]}
```

### Example Request (Windows PowerShell)
```powershell
$body = @{
  type_of_check = 'general'
  tenant        = 'indonesia'
  locale        = 'id'
  format        = 'plain'
  data          = 'hi'
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri 'http://<HOST>:2305/v1/proofread' `
  -Method POST -ContentType 'application/json' -Body $body
```

### Example Request (curl)
```bash
curl -X POST "http://<HOST>:2305/v1/proofread" \
  -H "Content-Type: application/json" \
  -d '{"type_of_check":"general","tenant":"indonesia","locale":"id","format":"plain","data":"hi"}'
```

---

## 🛡️ Rate Limiting

Each user (based on `X-APIKey` header or IP address) is limited to **20 requests per second**. Requests beyond that threshold return **HTTP 429 Too Many Requests** with a `Retry-After` header.

### Environment Configuration
```ini
RATE_LIMIT_RPS=20
RATE_LIMIT_WINDOW_SEC=1
```

### Behavior
| Condition | Response |
|------------|-----------|
| ≤ 20 requests/second | ✅ 200 OK |
| > 20 requests/second | 🚫 429 Too Many Requests + `Retry-After` header |

### Example 429 Response
```json
{
  "error": "rate_limited",
  "message": "Exceeded 20 req/s"
}
```

---

## 🐳 Run (Docker)
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps -a
```

---

## 🔌 Endpoints Overview

### A) One-Hit (recommended for HTML)
**POST `{BASE_PREFIX}/`**  
- **Input**: raw **HTML** (Body = HTML).  
- **Output (default)**: **HTML** (`text/html`) — final proofread HTML.  
- **Output (JSON)**: add `?format=json` or header `Accept: application/json` to get full JSON summary.

**Headers (typical)**
```
X-APIKey : <your key>
X-TocType: reference_check     # or general/employment_check/address_check
X-Tenant : indonesia           # or malaysia/thailand/...
X-Locale : id                  # or en/th/my
```

**What happens internally**
1) **HTML Freeze** → returns:
   - `html_format` (HTML skeleton with `[TEXT_xx]` / `[TABLE_xx]`),
   - `text_format` (JSON mapping `{ "[TEXT_01]": "…", ... }`),
   - `table_format` (if any), `table_map` (HTML tables by token),
   - `raw_format` (the untouched HTML you sent).
2) **PII→LLM→Unmask→Reformat** on `text_format`, with **token guard**.
3) **Reverse HTML**: fill the skeleton placeholders with the final text/table map → `final_html_format`.
4) **Persist** all fields to `summary_output` (Mongo) + return **HTML** (or JSON if requested).

**Examples**

- 🔁 **HTML out (default)**  
  ```bash
  curl -sS -X POST "http://10.30.112.70:2302/aitegrity-core/aiproofread"     -H "X-APIKey: <KEY>"     -H "X-TocType: reference_check"     -H "X-Tenant: indonesia"     -H "X-Locale: id"     --data-binary @input.html > final.html
  ```

- 🧾 **JSON out**  
  ```bash
  curl -sS -X POST "http://10.30.112.70:2302/aitegrity-core/aiproofread?format=json"     -H "X-APIKey: <KEY>"     -H "X-TocType: reference_check"     -H "X-Tenant: indonesia"     -H "X-Locale: id"     --data-binary @input.html | jq .
  ```

**JSON fields (one-hit)** — saved to `summary_output` and returned when `?format=json`:
```json
{
  "report_id": "uuid-...",
  "html_tag": true,
  "raw_format": "<p>...</p>",
  "html_format": "<p>[TEXT_01]</p>... [TABLE_01] ...",      // skeleton
  "text_format": {"[TEXT_01]": "...", "...": "..."},        // all [TEXT_*]
  "table_format": ["[TABLE_01]", "..."],                    // token list (if any)
  "table_map": {"[TABLE_01]": "<table>...</table>"},        // full HTML per table token
  "message_01": "masked text ...",
  "message_02": "{... json from LLM, values edited but tokens preserved ...}",
  "message_03": "unmasked text ...",
  "final_message": {"[TEXT_01]": "...", "...": "..."},      // post-LLM [TEXT_*] map
  "final_html_format": "<p>... final html ...</p>",
  "final_html_format_sha1": "ab12...",
  "final_html_format_b64":  "PGgxPj...==",
  "created_at": "2025-09-02T07:30:45.123456+00:00",         // UTC
  "created_at_wib": "2025-09-02T14:30:45+07:00",            // WIB ISO
  "created_at2": "02 September 2025 14:30:45 WIB",          // WIB human
  "updated_at": "...",
  "updated_at_wib": "...",
  "updated_at2": "..."
}
```

> **Default return = HTML.** Add `?format=json` or header `Accept: application/json` for JSON.

---

### B) HTML Utilities
All paths below are relative to `{BASE_PREFIX}`.

1) **Freeze** — `POST /html_tag_freeze`  
   Body: raw HTML.  
   Returns `report_id`, `html_format`, `text_format`, `table_format`, `table_map`, `raw_format`.

2) **Reverse** — `POST /reverse_html_tag`  
   Body: JSON `{ "html_format": "...", "final_message": {...}, "table_map": {...} }`  
   Returns `final_html_format`.

3) **Preview** — `GET /html_preview?report_id=<RID>` (or POST with JSON body)  
   Returns **raw HTML** (`text/html`) of `final_html_format` from DB (easy browser preview).

---

### C) Classic PII/LLM Stages (Text mode)
These accept **plain text** input or use `X-ReportID` of a previous step.

- `POST /pii_datamasking` – Mask → (optional) LLM → (optional) Unmask → (optional) Reformat.  
- `POST /llm-claude`      – Run LLM for a masking result (`message_01`).  
- `POST /unmask`          – Unmask a given `message_02`.  
- `POST /reformating`     – Normalize numbers (e.g., ID phones).

> In the **one-hit flow**, you typically won’t call these directly; they are orchestrated by `/` for HTML inputs.

---

## 🗃️ MongoDB Collections
- `masking_output`                – per-run masked payloads (`message_01`, layered maps).  
- `generative_output`             – LLM outputs (`message_02`) + prompt meta.  
- `unmask_output`                 – `message_03` + resolution stats.  
- `final_reformating_output`      – `message_final`.  
- `html_freeze` / `html_reverse`  – frozen & reversed HTML audit.  
- `summary_output`                – **single compact view** for one-hit; includes:
  - `report_id`, `raw_format`, `html_format` (skeleton), `text_format`, `table_format`, `table_map`,
  - `message_01`, `message_02`, `message_03`, `final_message`, `final_html_format`,
  - `final_html_format_sha1`, `final_html_format_b64`,
  - `created_at (UTC)`, `created_at_wib`, `created_at2`, `updated_at*`.

Timestamps are written in **UTC** and **WIB** (ISO + human) via `services/db.py` helpers:
- `created_at` (`YYYY-MM-DDTHH:MM:SS+07:00`),  
- `created_at2`/`updated_at2` (`DD Month YYYY HH:MM:SS WIB`).

---

## 🔐 Headers & Auth
All mutating endpoints require:
```
X-APIKey : <one of API_KEYS in .env>
X-TocType: <context>     # e.g. general / reference_check / employment_check / address_check
X-Tenant : <tenant>      # e.g. indonesia / malaysia / thailand
X-Locale : <locale>      # e.g. id / en / my / th
```
Optional: `X-ReportID` (to reuse an existing run).

---

## 🔤 Language–Locale Guard

To keep outputs consistent with the requested `locale`, the service validates the language of `data` **before** running the proofreading pipeline.

**Flow**
1) **Primary detector:** Lingua (pure-Python, robust for Indonesian/Malay/Thai).  
2) **Fallback:** Claude (only if detection is low-confidence or ambiguous).  
   If detection is **high-confidence but mismatched**, the API fails fast with **HTTP 400** (no LLM call).

**Allowed languages per locale (default)**
> If your DTO uses `locale="my"` for Malaysia, keep the key as `"my"`; Lingua still returns ISO `ms` for Malay.
```python
# app/core/lang_detect.py
LOCALE_ALLOWED_LANGS = {
  "id": {"id"},      # Indonesian only (strict)
  "th": {"th"},      # Thai only
  "my": {"ms"},       # Malay (detector returns "ms")
  "en": {"en"}
}

---

## 🧪 Examples

### Mode A — Manual (Most Precise)
1. **Freeze** → `POST {BASE_PREFIX}/html_tag_freeze` → get `html_format`, `text_format`, `table_format`, `table_map`, `raw_format`.
2. **PII + Auto-chain** → `POST {BASE_PREFIX}/pii_datamasking` (body = `text_format` as **raw text**).
3. **Reverse** → `POST {BASE_PREFIX}/reverse_html_tag` with final `[TEXT_xx]` & `[TABLE_xx]` maps → `final_html_format`.
4. (Optional) **Preview** → `GET {BASE_PREFIX}/html_preview?report_id=<RID>`.

### Mode B — One-shot (Simple)
- `POST {BASE_PREFIX}/` with raw **HTML**.  
  Good for production & demos. Returns **HTML** by default; use `?format=json` for full payload.

---

## 🩹 Troubleshooting
- **JSON shows `\"`**: that’s normal JSON escaping. Use one-hit default (HTML) or `/html_preview` to get raw HTML (`text/html`).  
- **`<br>` vs `<br />`**: normalized to `<br/>` internally for consistency—rendering is identical.  
- **Different DB vs response**: one-hit responds with the document **after** `upsert_summary`, ensuring parity.  
- **429 Too Many Requests**: tune `RATE_LIMIT_RPS` / `RATE_LIMIT_WINDOW_SEC`.  
- **WIB timestamps wrong**: ensure `now_wib()` is called **inside** handlers (not at import time).

---

## 🛡️ Token Preservation (LLM)
Prompts enforce:
- **Preserve all masking tokens** (`[TEXT_*]`, `[ORG_*]`, `[DATE_*]`, `[URL_*]`, etc.) exactly & in-order.
- **Do not include** `[TEXT_*]` tokens **inside values**; non-TEXT tokens **may remain** in values (unmasked later).
- Return **exactly one JSON** object when asked.

---

## 🧾 License
Proprietary — internal use only.