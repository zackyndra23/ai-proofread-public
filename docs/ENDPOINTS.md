# Endpoints

> **Last updated:** 2026-04-28 (branch `task/regex-reformatting-improvement03`)
>
> **Truth source:** `app/modules/*/routes.py` and `app/app.py`. The README's endpoint list is partly stale — this document supersedes it.

## URL prefix

`app/app.py::create_app()`:

```python
prefix = f"/{cfg.API_VERSION}" if cfg.API_PREFIX in ("", "/") else f"{cfg.API_PREFIX}/{cfg.API_VERSION}"
```

With defaults (`API_PREFIX=""`, `API_VERSION="v1"`), all blueprint routes mount under **`/v1/...`**. The README's `BASE_PREFIX=/aitegrity-core/aiproofread` is **not** applied by Flask itself — treat it as a reverse-proxy / load-balancer convention.

> Note: `app/modules/result_analyse/routes.py` defines `Blueprint("result_analyse", __name__, url_prefix="/v1/result-analyse")` AND is also registered with the global `prefix`. The blueprint-level `url_prefix` takes effect, so its routes are reachable at the paths listed below.

## Authentication and required headers

All mutating endpoints call `services/utils.py::require_headers(req)` which validates:

- `X-APIKey` — must match one of the values in env `API_KEYS` (comma-separated) or `API_KEY`. Compared with `hmac.compare_digest`.
- (Body locale, when present, is read separately by handlers.)

Conventional request headers used elsewhere in handlers (read from body or headers depending on endpoint):

```
X-APIKey  : <key>
X-TocType : general | reference_check | employment_check | address_check
X-Tenant  : indonesia | malaysia | thailand
X-Locale  : en | id | ms
X-ReportID: <uuid>   # optional, when reusing a previous run
```

## Rate limiting

Every blueprint installs `enforce_rps(bp.name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)` in `before_request`. Defaults: **20 requests / 60 s window** (note: `Config.RATE_LIMIT_WINDOW` reads `RATE_LIMIT_WINDOW_SEC`, default `60`). Over-limit responses are HTTP 429 with `Retry-After`.

## Endpoint table

| Module | Method | Path | Purpose |
|---|---|---|---|
| meta | GET | `/v1/meta/version` | Build / version info (no auth, no rate-limit) |
| meta | GET | `/v1/meta/healthz` | Liveness check (no auth, no rate-limit) |
| masking | POST | `/v1/masking/mask` | Run 3-layer PII masking on text |
| masking | POST | `/v1/masking/unmask` | Restore PII from a masked text using `layered_maps` |
| ner | POST | `/v1/ner/mask` | NER-only masking (per tenant model) |
| htmlmask | POST | `/v1/htmlmask/freeze` | Freeze HTML into skeleton + maps |
| htmlmask | POST | `/v1/htmlmask/reverse` | Fill skeleton from final maps to produce HTML |
| reformat | POST | `/v1/reformat` | Reformat phones / dates in text |
| proofread | POST | `/v1/proofread` | One-hit pipeline: mask → LLM → unmask → reformat |
| result_analyse | GET | `/v1/result-analyse/health` | QA module health (returns activation flag) |
| result_analyse | POST | `/v1/result-analyse/append` | Ops-only manual append to Google Sheet |

> The README mentions `/aitegrity-core/aiproofread/`, `/html_tag_freeze`, `/reverse_html_tag`, `/html_preview`, `/pii_datamasking`, `/llm-claude`, `/unmask`, `/reformating` as direct paths. **None of those exist in the active blueprints.** Either they were renamed or never landed. Treat the table above as authoritative.

---

## `/v1/meta/version` (GET)

Returns `version_info()` dict (`app/core/version.py`). Adds version headers to every response (`X-App-Version`, `X-API-Version`, `X-Git-SHA`).

## `/v1/meta/healthz` (GET)

Returns `{"status": "ok"}`.

## `/v1/masking/mask` (POST)

Body:
```json
{ "text": "Halo Rizal, no saya 09281819.", "locale": "id" }
```

DTO: `MaskRequest(text: str, locale: str = "id")` — dataclass, not Pydantic. Empty `text` → 400.

Response 200:
```json
{
  "masked": "Halo [PERSON_0], no saya [PHONE_NUMBER_0].",
  "layers": [{"type": "...", "map": {"...": "..."}}],
  "layered_maps": { "pii_EMAIL": {}, "pii_CREDIT_CARD": {}, "phones_lib": {"...": "..."} },
  "order": ["EMAIL_0", "PHONE_NUMBER_0", "..."]
}
```

Persists to `masking_output` via `MaskingRepository.save_masking`.

## `/v1/masking/unmask` (POST)

Body:
```json
{ "text": "Halo [PERSON_0]", "layered_maps": { "pii_PERSON": { "[PERSON_0]": "Rizal" } } }
```

DTO: `UnmaskRequest(text: str, layered_maps: dict)`.

Response: `{ "unmasked": "..." }`.

## `/v1/ner/mask` (POST)

Body:
```json
{ "text": "...", "tenant": "indonesia", "token_spans": [] }
```

DTO: `NerRequest(text, tenant, token_spans=None)`. `tenant` selects the NER model via `Config.TENANT2MODEL`.

Response: `{ "text": "...", "pairs": [...], "maps": {...} }`.

## `/v1/htmlmask/freeze` (POST)

Body:
```json
{
  "html": "<p>...</p>",
  "report_id": "uuid-or-null",
  "toc_type": "general",
  "tenant": "indonesia",
  "locale": "id"
}
```

DTO: `FreezeRequest(html, report_id, toc_type, tenant, locale)`.

Response (200):
```json
{
  "report_id": "uuid",
  "html_format":  "<p>[TEXT_01]</p>... [TABLE_01] ...",
  "text_format":  { "[TEXT_01]": "..." },
  "table_format": [ "[TABLE_01]" ],
  "table_map":    { "[TABLE_01]": "<table>...</table>" },
  "raw_format":   "<p>...</p>"
}
```

Persists to `html_freeze`.

## `/v1/htmlmask/reverse` (POST)

Body:
```json
{
  "html_skeleton": "<p>[TEXT_01]</p>",
  "text_map_new":  { "[TEXT_01]": "final text" },
  "table_map":     { "[TABLE_01]": "<table>...</table>" },
  "report_id":     "uuid-or-null",
  "toc_type":      "general",
  "tenant":        "indonesia",
  "locale":        "id"
}
```

DTO: `ReverseRequest(...)`.

Response: `{ "report_id": "uuid", "html_final": "<p>final text</p>" }`. Persists to `html_reverse`.

## `/v1/reformat` (POST)

Body:
```json
{ "text": "...", "locale": "id" }
```

DTO: `ReformatRequest(text, locale="id")`.

Response: `{ "result": "...", "meta": {...} }`. Persists to `final_reformating_output`.

## `/v1/proofread` (POST)

The one-hit pipeline. Strict-DTO entry point.

Body:
```json
{
  "type_of_check": "general",
  "tenant":        "indonesia",
  "locale":        "id",
  "format":        "plain",
  "data":          "Halo Rizal, no saya 09281819.",
  "report_id":     "94d579ec-11b6-48fb-a999-f0859bf7c09c"
}
```

DTO: `ProofreadRequest(BaseModel)` (`app/modules/proofread/dto.py`):
- `type_of_check: str` (default `"general"`)
- `tenant: Literal["indonesia", "thailand", "malaysia"]`
- `locale: Literal["en", "id", "ms"]`
- `format: Literal["plain", "html", "markdown"]`
- `data: str`
- `report_id: Optional[str]`
- `extra = "forbid"` — unknown fields → 400.

Pre-pipeline guards (in order — see [PIPELINE.md §0](./PIPELINE.md#0-pre-pipeline-guards)):
1. `require_headers`
2. JSON content-type
3. `validate_locale_tenant`
4. `is_symbol_only_text` (when `REJECT_SYMBOL_ONLY` on)
5. `validate_and_scan` (HTML / SQLi flags from `Config.DETECT_HTML` / `DETECT_SQLI`)
6. `validate_semantic_text` → 422 if too short / too few words / not meaningful
7. `validate_language_locale` → 422 if locale mismatch
8. Pydantic strict validation
9. `ProofreadService.run`

Response 200:
```json
{
  "report_id":      "uuid",
  "result":         "final proofread text or html",
  "tenant":         "indonesia",
  "type_of_check":  "general",
  "version":        { "app": "0.1.0", "api": "v1" }
}
```

Errors:
- 400 `validation_error` (Pydantic) / `INVALID_TEXT_SYMBOLS` / locale-tenant
- 422 `TEXT_TOO_SHORT` / `TEXT_TOO_FEW_WORDS` / `TEXT_NOT_MEANINGFUL` / `TEXT_INVALID_SEMANTIC` / `LOCALE_LANGUAGE_MISMATCH`
- 429 rate-limited
- 500 `processing_failed` (with `message`)

Persists to `summary_output` and per-stage collections. May also push to Google Sheets via `repo.hooks["after_final"]`.

## `/v1/result-analyse/health` (GET)

Returns `{ "module": "result_analyse", "activated": <bool> }`. Activation flag derived from `RESULT_ANALYZE` env.

## `/v1/result-analyse/append` (POST)

Ops-only manual Google Sheets append. JSON body must include all of:

```
request_payload, report_id, created_at2,
message_01, message_02, llm_prompt,
layered_maps, message_03, message_final
```

Missing fields → 400 with the missing list. Success → `{ "status": "ok", "appended_no": <row_no> }`. Failure during append → 500 `append_failed`.

## Common error response shapes

```json
{ "error": "rate_limited", "message": "Exceeded 20 req/s" }
{ "error": "validation_error", "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }
{ "error": "Body must be JSON" }
{ "error": "<reason>" }
```

`_error_response_with_detail` (in `app/core/validation.py`) wraps richer responses with a code, status, and a detail object — used by semantic / language guards.

## Examples

### curl — `/v1/proofread`

```bash
curl -sS -X POST "http://<HOST>:2302/v1/proofread" \
  -H "Content-Type: application/json" \
  -H "X-APIKey: <KEY>" \
  -H "X-TocType: general" \
  -H "X-Tenant: indonesia" \
  -H "X-Locale: id" \
  -d '{
    "type_of_check": "general",
    "tenant": "indonesia",
    "locale": "id",
    "format": "plain",
    "data": "Mohon hubungi 0812 3456 7890."
  }'
```

### PowerShell — `/v1/masking/mask`

```powershell
$body = @{ text = 'Halo Rizal, no saya 09281819.'; locale = 'id' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://<HOST>:2302/v1/masking/mask' `
  -Method POST -ContentType 'application/json' `
  -Headers @{ 'X-APIKey' = '<KEY>' } `
  -Body $body
```
