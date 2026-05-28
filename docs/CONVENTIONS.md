# Conventions and Invariants

> **Last updated:** 2026-04-28
>
> Hard rules that hold the pipeline together. Skim before changing masking / phone / LLM code.

## 1. Token preservation in LLM output (sacred)

The Claude prompt commits to preserve every `[CATEGORY_n]` token exactly and in original order. Specifically:

- Tokens that must come back **untouched and in-order**: `[TEXT_*]`, `[ORG_*]`, `[DATE_*]`, `[URL_*]`, `[KEYWORD_*]`, `[PERSON_*]`, `[EMAIL_*]`, `[CREDIT_CARD_*]`, `[PHONE_NUMBER_*]`, `[SOCMED_ACCOUNT_*]`, `[NIK_*]`, `[NPWP_*]`, `[IP_ADDRESS_*]`, `[ADDRESS_*]`.
- `[TEXT_*]` tokens **must NOT appear inside JSON string values** the LLM returns; they belong only as direct keys / placeholders. Non-`TEXT_*` tokens **may** sit inside string values — they will be unmasked in stage 4.
- The LLM must return **exactly one JSON object** when asked.

Why: the unmask + reverse-HTML steps assume token uniqueness and order. Drop or reorder a token and the final HTML cannot be reassembled.

Practical consequence: don't redesign the prompt without a token-preservation regression test. Don't add a category whose token shape collides with the regex `\[[A-Z0-9_]+\]` used in `_find_token_spans`.

## 2. Shared `counters` dict across masking layers

All three masking layers (`mask_with_piiregex`, `mask_with_phones_lib`, `mask_with_patterns`) accept the same `counters: Dict[str, int]`. A token like `[PHONE_NUMBER_3]` is unique across layers because `counters["PHONE_NUMBER"]` is bumped wherever it's used.

**Don't** introduce a layer-local counter for a category another layer can produce. If you add a new category that overlaps with an existing one, route its counter through the same key.

## 3. Span overlap protection

Helpers in `services/masking.py`:

```python
def _find_token_spans(text):     # → [(start, end), ...] of all [CATEGORY_n] tokens
def _overlaps(start, end, spans): # any candidate match that hits an existing span is skipped
```

Every new pattern in `mask_with_patterns` (and every fallback) **must** consult `_overlaps` before claiming a span. Without it, a regex can chew into an already-tokenized region and produce malformed tokens like `[PHONE_NUMBER_[EMAIL_0]]`.

## 4. Conflict resolution among candidates

Within a single masking step:

```python
candidates.sort(key=lambda x: (x[0], -(x[1] - x[0])))   # by start asc, then by length desc
selected, last_end = [], -1
for st, en, ... in candidates:
    if st < last_end: continue
    selected.append(...)
    last_end = en
```

Always: **earliest start wins; ties broken by longest match; left-to-right non-overlap.** New patterns should respect this so longer matches like `"PT BUMA Internasional Grup Tbk."` aren't truncated by a shorter sibling pattern.

## 5. `+`-freeze trick (`services/phonefmt.py`)

```python
_FREEZE_CHAR = "​"  # ZERO WIDTH SPACE
def _freeze_plus(s):  return s.replace("+", "+" + _FREEZE_CHAR)
def _unfreeze_plus(s): return s.replace(_FREEZE_CHAR, "")
```

Already-handled `+CC...` international tokens are "frozen" by inserting a ZWS so subsequent libphonenumber / regex passes don't re-match them. **Always unfreeze before returning text downstream.** Anything that calls `phonenumbers` after a freeze pass on text that wasn't unfrozen will silently miss numbers.

## 6. Indonesian mobile regex constraints

Current (`improvement03`):

```python
_RE_ID_MOBILE = re.compile(r'(?<!\d)0(?:[ .()-]?\d){9,11}(?!\d)')
```

Hard requirements (don't loosen without addressing all):
- **Match must end on a digit.** Trailing `.` / `,` / `)` etc. **must not** be inside `m.group(0)`. The previous shape `r'0(?:8[\d \-\.\(\)]{8,14})'` swallowed trailing punctuation and corrupted sentence flow.
- **`mobile_sub` validates after match:** `digits.startswith("08")` AND `10 ≤ len(digits) ≤ 12`. If either fails, the function returns `before` unchanged.
- Landline regex `_RE_ID_LANDLINE = r'(?<!\d)0(2\d{1,2})(\d{6,8})(?!\d)'` runs **before** the mobile regex so `021…` numbers aren't mis-handled. Don't reverse the order.
- The `landline_sub` greedy-area normalization re-snaps `0217…` → `area=021, sub=7…`. If you change the area regex, recheck this normalization.

## 7. International phone reformatting

`_format_phone_token(raw, locale)` policy:
- `+CC…` → `_format_with_cc_as_zero` (custom intl rules).
- No `+`, no leading `0`, but a 1–3 digit prefix matching `WORLD_CC` → treat as intl, build `nsn0 = "0" + rest`, then `_format_intl_mobile(cc, nsn0)`.
- Anything else (numbers starting with `0`, `021…`, `08…`, weird shapes) → return unchanged; let `_fallback_regex_pass` handle ID-specific rules.

`WORLD_CC` lives in `services/phone_world_cc.py`. New country support means updating that map.

## 8. Strict DTO validation

`app/modules/proofread/dto.py` uses Pydantic with `extra = "forbid"`. Any new field accepted by `/v1/proofread` requires:

1. Adding it to `ProofreadRequest`.
2. Updating the route's `payload` dict in `app/modules/proofread/routes.py`.
3. Updating `ALLOWED_KEYS` in the same file.
4. Updating [ENDPOINTS.md](./ENDPOINTS.md) and (if user-facing) the README.

For other modules (masking, htmlmask, ner, reformat) DTOs are plain dataclasses, so adding a field requires updating both DTO and the route handler that constructs it.

## 9. WIB timestamps

`services/db.py::now_wib()` produces UTC+7 ISO + human format. **Must be called inside a request handler**, not at import time, otherwise the time freezes at process start. Persisted records carry both UTC and WIB.

## 10. Rate limiting

- `enforce_rps(name, rps, window_sec)` is registered in `before_request` of every blueprint (except `meta`).
- Default: 20 RPS over a 60 s window — note the README's "1 second" example does not match the active `RATE_LIMIT_WINDOW=60` default.
- Use a unique `name` per blueprint (matches `bp.name`) so counters don't collide.

## 11. Default response format

The proofread route returns JSON. The original product README describes a one-hit endpoint that returns HTML by default; that endpoint **does not exist** in current routes. Don't reintroduce it without designing the rendering / `Accept` negotiation explicitly.

## 12. Indonesian-language code comments

Most existing comments are in Indonesian/Bahasa. When adding comments **at all** — and the system default is "no comment unless WHY is non-obvious" — match the local language to keep the codebase coherent. Don't translate existing comments wholesale.

## 13. Safety toggles (off by default)

Set in `app/core/config.py` from env:

| Toggle | Env | Default | Effect |
|---|---|---|---|
| `DETECT_SQLI` | `SQL_INJECTION` | off | Rejects payloads with SQLi-shaped patterns |
| `DETECT_HTML` | `HTML_FORMAT` | off | Rejects raw HTML in `data` unless `format=html|markdown` |
| `REJECT_SYMBOL_ONLY` | `REJECT_SYMBOL_ONLY` | off | Rejects payloads that are only symbols/numbers |
| `LLM_SEMANTIC_VALIDATION` | `LLM_SEMANTIC_VALIDATION` | `1` | Runs the semantic guard; off skips it |

Tweak intentionally; production typically wants these on (per `.env`, not `env.example`).

## 14. Doc maintenance contract

When you change anything in this list of areas, update the relevant doc and bump its `Last updated` date:

| Area changed | Update |
|---|---|
| Module structure, file moves | [PROJECT_OVERVIEW.md §3](./PROJECT_OVERVIEW.md) |
| Pipeline stages, masking layers, LLM prompt shape, unmask/reformat logic | [PIPELINE.md](./PIPELINE.md) |
| HTTP routes, headers, request/response shapes | [ENDPOINTS.md](./ENDPOINTS.md) |
| Env vars, defaults, security toggles | [ENVIRONMENT.md](./ENVIRONMENT.md) |
| Hard invariants, regex constraints, naming conventions | this file |
| Tenants / locales / NER mapping | `CLAUDE.md` "Tenants and locales" + [PROJECT_OVERVIEW.md §4](./PROJECT_OVERVIEW.md) |

Always reconcile `README.md` in the same change if the change touches anything the README claims. When `README.md` and code disagree, **trust the code**.
