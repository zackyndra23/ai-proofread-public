# Pipeline

> **Last updated:** 2026-04-29 (added optional masking-results dataset mirror for model-improvement)

The canonical request flow for the one-hit `/proofread` endpoint and (more loosely) the per-stage endpoints. Every stage has corresponding code paths and persisted Mongo collections so a run can be reconstructed end-to-end.

```
       ┌─────────────────┐
HTML → │ 1. HTML Freeze  │ → skeleton + text_map + table_map
       └─────────────────┘
                ↓ (text_format)
       ┌─────────────────┐
       │ 2. PII Mask (3) │   shared counters across all 3 layers
       └─────────────────┘
                ↓ message_01 (masked text)
       ┌─────────────────┐
       │ 3. LLM (Claude) │   token-preserving prompt
       └─────────────────┘
                ↓ message_02 (LLM JSON, tokens intact)
       ┌─────────────────┐
       │ 4. Unmask       │   non-TEXT tokens → originals
       └─────────────────┘
                ↓ message_03
       ┌─────────────────┐
       │ 5. Reformat     │   ID phones, dates, intl numbers
       └─────────────────┘
                ↓ message_final
       ┌─────────────────┐
       │ 6. Reverse HTML │   fill skeleton from final maps
       └─────────────────┘
                ↓ final_html_format
       ┌─────────────────┐
       │ 7. Persist      │   summary_output + per-stage docs
       └─────────────────┘
                ↓
              Response (HTML or JSON)
```

Pre-pipeline (only on `/proofread`): payload validation, locale/tenant guard, symbol-only rejection (when enabled), HTML/SQLi scan (when enabled), semantic-text guard, language-locale guard. See [§0](#0-pre-pipeline-guards).

---

## 0. Pre-pipeline guards (`/proofread` only)

Order in `app/modules/proofread/routes.py::proofread()`:

1. `require_headers(request)` — checks `X-APIKey`, `X-TocType`, `X-Tenant`, `X-Locale`.
2. `request.is_json` check.
3. `validate_locale_tenant(payload)` — hard locale/tenant validation **before** any deeper scan.
4. `is_symbol_only_text(payload["data"])` — only when `Config.REJECT_SYMBOL_ONLY` (env `REJECT_SYMBOL_ONLY`) is on.
5. `validate_and_scan(...)` — combined Pydantic-shape + security scan. `enable_html` / `enable_sql` from `Config.DETECT_HTML` / `Config.DETECT_SQLI`. `reject_on_html` is true only if HTML detection is on **and** the user did not request `format=html|markdown`.
6. `validate_semantic_text(locale, data)` — checks min chars, min words, "meaningful" criteria. Failure → 422 with one of `TEXT_TOO_SHORT`, `TEXT_TOO_FEW_WORDS`, `TEXT_NOT_MEANINGFUL`, `TEXT_INVALID_SEMANTIC`.
7. `validate_language_locale(locale, data)` — Lingua first; Claude fallback if `LLM_LANG_VALIDATION=1`. Failure → 422 `LOCALE_LANGUAGE_MISMATCH`.
8. `ProofreadRequest(**payload)` — final Pydantic gate (`extra = "forbid"`).
9. `ProofreadService.run(req)` — invokes the pipeline below.

## 1. HTML Freeze (`htmlmask`)

Module: `app/modules/htmlmask/`, helpers in `services/htmltags.py`.

- Input: raw HTML.
- Output: `html_format` (skeleton with `[TEXT_xx]` and `[TABLE_xx]` placeholders), `text_format` (map of `[TEXT_xx] → original text`), `table_format` (list of `[TABLE_xx]` tokens), `table_map` (map of `[TABLE_xx] → original HTML table`), and `raw_format` (untouched original).
- Persists to `html_freeze` collection (`HtmlRepository.save_freeze`).
- Direct endpoint: `POST /v1/htmlmask/freeze` — returns `{report_id, html_format, text_format, table_format, table_map, raw_format}`.

## 2. PII Mask (`services/masking.py`) — 3 layers, shared counters

The masking service is invoked by `MaskingService.run_layers(text, locale)`. All three layers receive a single `counters: Dict[str, int]` so token IDs (e.g. `[EMAIL_0]`, `[PHONE_NUMBER_0]`) are unique across layers.

### Layer 1 — `mask_with_piiregex`

- Provider: the `piiregex` package.
- Categories: `EMAIL` → `[EMAIL_n]`, `CREDIT_CARD` → `[CREDIT_CARD_n]`.
- Phones are explicitly **not** done here — Layer 2 is authoritative for phones.
- Span overlap protection via `_find_token_spans` + `_overlaps`.

### Layer 2 — `mask_with_phones_lib(text, region, counters)`

- Step 1: `PhoneNumberMatcher(text, region)` collects candidate spans. Each span is expanded by ±1 char to grab any wrapping `(` / `)`.
- Step 2: candidates sorted by start; longest-at-same-start preferred; non-overlapping selection left → right.
- Step 3: each candidate is parsed with `pn_parse(raw, region)`. If `is_possible_number` is true → mask as `[PHONE_NUMBER_n]`. If parsing/possibility fails → skip; the fallback below picks it up.
- Step 4 (fallback): `_mask_generic_numeric_phones` runs over remaining text using `PHONE_GENERIC_RE = r"\+?\d[\d\-\s]{5,20}"`. Length filter: **6–12 digits** without `+`, **7–13 digits** with `+`. Same overlap protection.

### Layer 3 — `mask_with_patterns` (regex catch-all)

Pattern list in source order (`services/masking.py`, around lines 330–395):

| Pattern (sketch) | Token category |
|---|---|
| `[\w.+-]+@[\w-]+\.[\w-.]+` (email fallback) | `EMAIL` |
| `https?://\S+` and `www\.\S+` | `URL` |
| `(?<!\w)@[A-Za-z0-9_]…` (handle, avoids emails) | `SOCMED_ACCOUNT` |
| `(?<!\w)#[A-Za-z0-9_]{1,50}\b` | `KEYWORD` |
| `"[^"\r\n]{1,200}"` (double-quoted text — added in `improvement03`) | `KEYWORD` |
| ID month + year, day + ID month [+ year], with `Mei`/`Mar` etc. | `DATE` |
| English month + year, day + EN month [+ year], `from YYYY to YYYY`, etc. | `DATE` |
| Numeric `dd/mm/yyyy`, `dd-mm-yy`, etc. | `DATE` |
| `(?:Ibu|Bapak|Pak|Bu)\s+[A-Z]\w+` (one-word honorific person) | `PERSON` |
| `PT\.? … (Persero)? Tbk\.?` | `ORG` |
| `\b\d{16}\b` | `NIK` |
| `\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}` | `NPWP` |
| `(?:\d{1,3}\.){3}\d{1,3}` | `IP_ADDRESS` |
| `(Jl\.|Jalan)\s\S+` | `ADDRESS` |
| `(\+62|62|0)\s?(?:\(?\d{2,4}\)?[\s-]?){2,6}\d{2,4}` (fallback ID phone) | `PHONE_NUMBER` |

Conflict resolution: collect all candidate matches, sort by `(start, -length)`, pick longest-at-same-start, walk left → right skipping overlaps. Span overlap with already-tokenized text is rejected up front via `_find_token_spans`.

### Output of stage 2

`message_01` (masked text) plus `layered_maps` (per-category dict for unmasking) and `order` (the order tokens were applied — used for stable reverse).

## 3. LLM (`services/llm.py` + `llm_prompt/`)

- Prompt file is selected by `type_of_check` and `format`. HTML/markdown variants under `llm_prompt/`, plain-text under `llm_prompt/plain/`.
- Prompt enforces: preserve every `[CATEGORY_n]` token exactly and in original order; do NOT embed `[TEXT_*]` tokens inside JSON string values; non-TEXT tokens may sit inside values.
- Model and temperature from `Config.ANTHROPIC_MODEL`, env `LLM_TEMPERATURE`. `MAX_INPUT_TOKEN` (env) gates oversize payloads → HTTP 400 `input_too_large`.
- Response stored as `message_02`. Persisted to `generative_output`.

## 4. Unmask

Module: `app/modules/masking/services.py::MaskingService.unmask`.

- Input: `message_02` and the `layered_maps` from stage 2.
- Behaviour: replaces every non-`TEXT_*` token (`[EMAIL_*]`, `[PHONE_NUMBER_*]`, `[DATE_*]`, `[ORG_*]`, `[KEYWORD_*]`, etc.) with its original value. `[TEXT_*]` tokens remain in place — they're filled later in stage 6.
- Output: `message_03`. Persisted to `unmask_output`.

## 5. Reformat (`services/phonefmt.py`)

- Indonesian landline: `_RE_ID_LANDLINE = r'(?<!\d)0(2\d{1,2})(\d{6,8})(?!\d)'` → `_format_id_landline(area, sub)` (greedy "021" normalization included).
- Indonesian mobile: `_RE_ID_MOBILE = r'(?<!\d)0(?:[ .()-]?\d){9,11}(?!\d)'`. The replacement function `mobile_sub` re-extracts digits, asserts `digits.startswith("08")` and `10 ≤ len(digits) ≤ 12`, then runs `_format_intl_mobile("62", digits)`.
- International candidates (no `+`, no leading `0`): country code detected from `WORLD_CC` (1–3 leading digits); reformatted with `_format_intl_mobile(cc, "0" + rest)`.
- `+`-prefix tokens: routed to `_format_with_cc_as_zero(s)`. The `+`-freeze trick (`_freeze_plus` / `_unfreeze_plus`, `​`) keeps already-handled tokens out of subsequent passes.
- Date normalization helpers exist alongside (`_DATE_DDMMYYYY`, etc.).
- Output: `message_final`. Persisted to `final_reformating_output`.

## 6. Reverse HTML (`htmlmask/services.py::HtmlMaskService.reverse`)

- Inputs: `html_skeleton` (from stage 1), `text_map_new` (post-LLM map of `[TEXT_xx] → final text`), `table_map`.
- Output: `final_html_format` — placeholders filled, original markup intact.
- Direct endpoint: `POST /v1/htmlmask/reverse`. Persisted to `html_reverse`.

## 7. Persistence (`services/db.py`)

- Per-stage collections: `masking_output`, `generative_output`, `unmask_output`, `final_reformating_output`, `html_freeze`, `html_reverse`.
- One-hit consolidated record: `summary_output` — includes `report_id`, `raw_format`, `html_format`, `text_format`, `table_format`, `table_map`, every `message_*`, `final_message`, `final_html_format`, plus `final_html_format_sha1`, `final_html_format_b64`.
- Timestamps: UTC ISO **and** WIB (UTC+7) ISO + WIB human format. Helper `now_wib()` must be called inside a request handler, not at import time.

## 8. Optional: Result Analysis (Google Sheets)

- Activated when `RESULT_ANALYZE=ACTIVATE`.
- Triggered as a `repo` hook in `ProofreadRepo(hooks={"after_final": append_row_from_report})` (`app/modules/proofread/routes.py`).
- Implementation: `app/modules/result_analyse/services.py::QAAutomationService` → `services/gsheets_client.py`.
- Manual ops endpoint: `POST /v1/result-analyse/append` (see [ENDPOINTS.md](./ENDPOINTS.md)).

## 9. Where each stage lives

| Stage | Service | Direct endpoint | DTO | Repository | Mongo collection |
|---|---|---|---|---|---|
| 1. HTML Freeze | `app/modules/htmlmask/services.py::HtmlMaskService.freeze` | `POST /v1/htmlmask/freeze` | `htmlmask/dto.py::FreezeRequest` | `htmlmask/repositories.py::HtmlRepository` | `html_freeze` |
| 2. PII Mask | `services/masking.py` (called via `app/modules/masking/services.py::MaskingService.run_layers`) | `POST /v1/masking/mask` | `masking/dto.py::MaskRequest` | `masking/repositories.py::MaskingRepository` | `masking_output` (+ optional 9-field mirror to `MASKING_RESULTS_DC`, see §10) |
| 3. LLM | `services/llm.py` (orchestrated by `proofread/services.py`) | (none direct in code; only via `/proofread`) | — | — | `generative_output` |
| 4. Unmask | `app/modules/masking/services.py::MaskingService.unmask` | `POST /v1/masking/unmask` | `masking/dto.py::UnmaskRequest` | (shared) | `unmask_output` |
| 5. Reformat | `services/phonefmt.py` (called via `app/modules/reformat/services.py`) | `POST /v1/reformat` | `reformat/dto.py::ReformatRequest` | `reformat/repositories.py::ReformatRepository` | `final_reformating_output` |
| 6. Reverse HTML | `app/modules/htmlmask/services.py::HtmlMaskService.reverse` | `POST /v1/htmlmask/reverse` | `htmlmask/dto.py::ReverseRequest` | `htmlmask/repositories.py::HtmlRepository` | `html_reverse` |
| One-hit pipeline | `app/modules/proofread/services.py::ProofreadService.run` | `POST /v1/proofread` | `proofread/dto.py::ProofreadRequest` | `proofread/repositories.py::ProofreadRepo` | `summary_output` (consolidated) |

> All endpoints live under the `/v1/...` prefix. See [ENDPOINTS.md](./ENDPOINTS.md) for the full surface.

---

## 10. Masking-results dataset mirror (optional, off by default)

A non-load-bearing side-write that copies a 9-field whitelist of every `masking_output` document produced by the `/v1/proofread` flow to a separate Mongo collection. Intended as a curated dataset for future masking-model improvement.

- **Toggle:** `Config.MASKING_RESULTS_FEATURE` — strict parse, only literal `ON` (case-insensitive) enables. Default OFF (fail-safe).
- **Destination collection:** `MASKING_RESULTS_DC` env var (default `masking_results`). Bound and indexed in `services/db.py::init_db()` regardless of toggle.
- **Whitelist:** `_id, report_id, toc_type, tenant, locale, message_01, layers, created_at, created_at2`. Defined in `app/modules/proofread/repositories.py::_MASKING_RESULTS_FIELDS`. Field non-whitelist (`body`, `order`) is **not** copied.
- **`_id` reuse:** the source document's `_id` is pre-generated as `bson.ObjectId()` in `ProofreadRepo.save_masking` and copied into the mirror — gives a 1:1 trace.
- **Timestamps:** `created_at`/`created_at2` are copied from source (snapshot consistency).
- **Scope:** only the `/v1/proofread` flow (jalur B). The standalone `POST /v1/masking/mask` endpoint (jalur A) is **not** mirrored — its repo (`MaskingRepository`) is unchanged.
- **Failure isolation:** mirror insert routes through `safe_insert` → returns `bool`, never raises. A Mongo blip, missing collection, or `DB_DISABLED` causes the mirror to silently skip; the main `/proofread` response is unaffected. Hard rule: **mirror failure must not fail the request**.
- **Indexes (auto in `init_db`):** `(report_id ASC, created_at DESC)` and `(tenant ASC, created_at DESC)`. Non-unique by design — duplicate `report_id` entries are tolerated; deduplication is a downstream preprocessing concern.
- **Logging:** missing-field warnings and Mongo errors use `print` with the existing `⚠️` / `❌` prefix convention (see `services/db.py`).
