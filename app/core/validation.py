from flask import jsonify, request
import re
import bleach
from typing import Any, Tuple

# ALLOWED_LOCALES = {"en", "id", "th", "ms"}
ALLOWED_LOCALES = {"en", "id", "ms"}
ALLOWED_TENANTS = {"indonesia", "thailand", "malaysia"}

# --- configurable patterns ---
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_XSS_DANGERS = re.compile(r"(javascript:)|(<script\b)|(\bon\w+\s*=)", re.IGNORECASE)
_RE_SQL_SUSP  = re.compile(
    r"(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|--|;|\bOR\s+1=1\b)",
    re.IGNORECASE,
)

def _error_response(message: str, error: str, status_code: int):
    resp = jsonify({
        "message": message,
        "error": error,
        "statusCode": status_code
    })
    resp.status_code = status_code
    return resp

def _error_response_with_detail(message: str, error: str, status_code: int, detail: dict):
    resp = jsonify({
        "detail": detail,
        "message": message,
        "error": error,
        "statusCode": status_code
    })
    resp.status_code = status_code
    return resp

def validate_payload_strict(payload: dict, allowed_keys: set):
    if not isinstance(payload, dict):
        return _error_response(
            "Payload must be a JSON object.",
            "INVALID_JSON_PAYLOAD",
            400
        )

    extra = set(payload.keys()) - set(allowed_keys)
    if extra:
        return _error_response(
            f"Unknown field(s): {sorted(list(extra))}",
            "UNKNOWN_FIELDS",
            400
        )

    return None

def validate_locale_tenant(payload: dict):
    # Check required fields
    if "locale" not in payload:
        return _error_response(
            "Field 'locale' is required.",
            "MISSING_LOCALE",
            400
        )
    if "tenant" not in payload:
        return _error_response(
            "Field 'tenant' is required.",
            "MISSING_TENANT",
            400
        )

    # Normalize input (biar 'Indonesia' == 'indonesia')
    locale = payload.get("locale")
    tenant = payload.get("tenant")
    if isinstance(locale, str):
        locale = locale.strip().lower()
        payload["locale"] = locale
    if isinstance(tenant, str):
        tenant = tenant.strip().lower()
        payload["tenant"] = tenant

    # Unsupported locale (No 1)
    if locale not in ALLOWED_LOCALES:
        allowed = ", ".join(sorted(ALLOWED_LOCALES))
        return _error_response(
            f"Unsupported locale: '{locale}'. Allowed values are: {allowed}.",
            "UNSUPPORTED_LOCALE",
            400
        )

    # Unsupported tenant (No 2)
    if tenant not in ALLOWED_TENANTS:
        allowed = ", ".join(sorted(ALLOWED_TENANTS))
        return _error_response(
            f"Unsupported tenant: '{tenant}'. Allowed values are: {allowed}.",
            "UNSUPPORTED_TENANT",
            400
        )

    return None

# --- helpers ---
def contains_html_or_xss(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if _RE_HTML_TAG.search(value):
        return True
    if _RE_XSS_DANGERS.search(value):
        return True
    return False

def contains_sql_like(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_RE_SQL_SUSP.search(value))

def sanitize_text_strict(value: str) -> str:
    """
    Remove all HTML and attributes. Use if you want to preserve plain text only.
    """
    return bleach.clean(value or "", tags=[], attributes={}, strip=True)

def sanitize_allowlist(value: str, allowed_tags=None) -> str:
    """
    If you want to allow a tiny set of safe tags (e.g. <b>, <i>), pass allowed_tags list.
    """
    return bleach.clean(value or "", tags=allowed_tags or [], attributes={}, strip=True)

# def _scan_primitive(value: Any) -> Tuple[bool, str]:
#     """
#     Returns (is_bad, reason)
#     """
#     if isinstance(value, str):
#         if contains_html_or_xss(value):
#             return True, "contains HTML/JS or XSS-like pattern"
#         if contains_sql_like(value):
#             return True, "contains SQL-like keywords/patterns"
#     return False, ""
def _scan_primitive(value: Any, *, enable_html: bool, enable_sql: bool) -> Tuple[bool, str]:
    """
    Returns (is_bad, reason) — sekarang tergantung flag enable_html/enable_sql.
    """
    if isinstance(value, str):
        if enable_html and contains_html_or_xss(value):
            return True, "contains HTML/JS or XSS-like pattern"
        if enable_sql and contains_sql_like(value):
            return True, "contains SQL-like keywords/patterns"
    return False, ""

# def scan_payload(payload: Any) -> Tuple[bool, str]:
#     """
#     Recursively scan dict/list/primitive payload for risky tokens/patterns.
#     Returns (is_malicious, reason). Use this in validate functions.
#     Also block keys that start with '$' to prevent Mongo operator injection.
#     """
#     if payload is None:
#         return False, ""
#     if isinstance(payload, dict):
#         for k, v in payload.items():
#             if isinstance(k, str) and k.startswith("$"):
#                 return True, f"forbidden key: {k}"
#             bad, reason = scan_payload(v)
#             if bad:
#                 return True, reason
#         return False, ""
#     if isinstance(payload, (list, tuple)):
#         for item in payload:
#             bad, reason = scan_payload(item)
#             if bad:
#                 return True, reason
#         return False, ""
#     # primitive types
#     return _scan_primitive(payload)
def scan_payload(payload: Any, *, enable_html: bool = True, enable_sql: bool = True) -> Tuple[bool, str]:
    """
    Recursively scan dict/list/primitive payload for risky tokens/patterns.
    Returns (is_malicious, reason).
    """
    if payload is None:
        return False, ""
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(k, str) and k.startswith("$"):
                return True, f"forbidden key: {k}"
            bad, reason = scan_payload(v, enable_html=enable_html, enable_sql=enable_sql)
            if bad:
                return True, reason
        return False, ""
    if isinstance(payload, (list, tuple)):
        for item in payload:
            bad, reason = scan_payload(item, enable_html=enable_html, enable_sql=enable_sql)
            if bad:
                return True, reason
        return False, ""
    # primitive types
    return _scan_primitive(payload, enable_html=enable_html, enable_sql=enable_sql)

# --- integration helpers for routes ---
# def validate_and_scan(payload: dict, allowed_keys: set, *,
#                       reject_on_html=True) -> None:
#     """
#     Combined helper that:
#       1) checks payload shape (unknown keys)
#       2) scans payload for XSS/SQL/Mongo-operator injection
#     If an issue is found, returns a Flask response (400) same as existing helpers.
#     Otherwise returns None.
#     """
#     # strict shape check (existing)
#     bad = validate_payload_strict(payload, allowed_keys)
#     if bad:
#         return bad

#     # scan content
#     malicious, reason = scan_payload(payload)
#     if malicious:
#         return _bad_request(f"malicious_payload: {reason}")

#     # optionally sanitize fields that are allowed to contain some HTML (example)
#     if not reject_on_html and isinstance(payload.get("data"), str):
#         # keep only safe text (no tags)
#         payload["data"] = sanitize_text_strict(payload["data"])

#     return None
def validate_and_scan(
    payload: dict,
    allowed_keys: set,
    *,
    reject_on_html: bool = True,
    enable_html: bool = True,
    enable_sql: bool = True,
) -> None:
    """
    1) shape check
    2) content scan (XSS/SQL) — sekarang bisa di-ON/OFF via enable_html/enable_sql.
    3) optional sanitize jika reject_on_html=False
    """
    bad = validate_payload_strict(payload, allowed_keys)
    if bad:
        return bad

    malicious, reason = scan_payload(payload, enable_html=enable_html, enable_sql=enable_sql)
    if malicious:
        return _error_response(
            f"malicious_payload: {reason}",
            "MALICIOUS_PAYLOAD",
            400
        )

    # Jika tidak menolak HTML, lakukan sanitasi (hapus tag) utk field 'data'
    if not reject_on_html and isinstance(payload.get("data"), str):
        payload["data"] = sanitize_text_strict(payload["data"])

    return None

# === Token counting & input limit ============================================
# Prefer exact tokenizer kalau tersedia; fallback ke estimasi aman.
_tokenizer = None
try:
    # Opsi A: anthropic-tokenizer (paling dekat untuk Claude)
    # pip install anthropic-tokenizer
    from anthropic_tokenizer import get_tokenizer  # type: ignore
    _tokenizer = get_tokenizer()
except Exception:
    try:
        # Opsi B: tiktoken (cl100k_base) sebagai pendekatan umum
        # pip install tiktoken
        import tiktoken  # type: ignore
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tokenizer = None

def _count_tokens_fallback(text: str) -> int:
    # Estimasi konservatif: ~4 char per token
    if not text:
        return 0
    return max(1, len(text) // 4)

def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _tokenizer is None:
        return _count_tokens_fallback(text)
    try:
        # anthropic_tokenizer: callable -> list[int]
        if hasattr(_tokenizer, "__call__"):
            return len(_tokenizer(text))
        # tiktoken: .encode -> list[int]
        if hasattr(_tokenizer, "encode"):
            return len(_tokenizer.encode(text))
    except Exception:
        pass
    return _count_tokens_fallback(text)

def ensure_under_input_token_limit(parts, limit: int, context_name: str = "input") -> int:
    """
    parts: iterable of strings (potongan input yang akan jadi prompt)
    limit: 0 berarti unlimited
    return: total tokens
    raise: ValueError jika melebihi limit
    """
    total = 0
    for p in parts or []:
        if p:
            total += count_tokens(p)
    if limit and total > limit:
        raise ValueError(f"{context_name} tokens {total} exceeds MAX_INPUT_TOKEN={limit}")
    return total

def is_symbol_only_text(value: Any, field_name: str = "data") -> Tuple[bool, str]:
    """
    Returns (is_bad, reason).

    Rule:
    - Strip whitespace.
    - Kalau kosong → bad.
    - Kalau tidak mengandung huruf sama sekali (cuma simbol/angka/whitespace) → bad.
    - Minimal 1 huruf (any locale) supaya dianggap "ada teks yang bisa diproofread".
    """
    if not isinstance(value, str):
        return True, f"Field '{field_name}' must be a string."

    text = value.strip()
    if not text:
        return True, f"Field '{field_name}' must not be empty."

    # cek apakah ada huruf sama sekali (A–Z, a–z, huruf lokal, dll)
    has_letter = any(ch.isalpha() for ch in text)
    if not has_letter:
        return True, f"Field '{field_name}' must contain readable text, not only symbols or digits."

    return False, ""