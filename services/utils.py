# services/utils.py
import os, hmac, logging
from typing import Tuple, Dict, Optional
from flask import Request
from pathlib import Path

logger = logging.getLogger(__name__)

# --- API key ---
APIKEY_CANDIDATES = ("X-APIKey", "X-apikey")

# --- Locale ---
# ALLOWED_LOCALES = {"en", "id", "th", "ms"}
ALLOWED_LOCALES = {"en", "id", "ms"}
DEFAULT_EN_REGION = os.getenv("DEFAULT_EN_REGION", "US")
# LOCALE_TO_REGION = {
#     "id": "ID",
#     "th": "TH",
#     "ms": "MS",
#     "en": DEFAULT_EN_REGION,
# }
LOCALE_TO_REGION = {
    "id": "ID",
    "ms": "MS",
    "en": DEFAULT_EN_REGION,
}

# --- API key helpers ---
def _expected_api_keys():
    raw = os.getenv("API_KEYS") or os.getenv("API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]

def _read_api_key(req: Request) -> str:
    for h in APIKEY_CANDIDATES:
        v = req.headers.get(h)
        if v:
            return v.strip()
    return ""

def _api_key_valid(provided: str) -> bool:
    keys = _expected_api_keys()
    return bool(keys) and any(hmac.compare_digest(provided, k) for k in keys)

def _read_locale(req: Request) -> str:
    """Locale dibaca dari body JSON (fallback 'id')."""
    if req.is_json:
        body = req.get_json(silent=True) or {}
        if isinstance(body, dict) and body.get("locale"):
            return str(body["locale"]).strip().lower()
    return ""

# --- Validasi utama ---
def require_headers(req: Request) -> Tuple[bool, str]:
    """
    Validasi request:
      - X-APIKey wajib & valid
      (body akan divalidasi di layer lain)
    """
    provided_key = _read_api_key(req)
    if not provided_key:
        return False, "Missing header X-APIKey"
    if not _api_key_valid(provided_key):
        return False, "Invalid X-APIKey."
    return True, ""

def extract_headers(req: Request) -> Dict[str, str]:
    """Gabungkan API key (header) + field lain (body)."""
    apikey = _read_api_key(req)
    body = req.get_json(silent=True) or {}
    return {
        "apikey": apikey,
        "toc_type": str(body.get("type_of_check") or "").strip(),
        "tenant": str(body.get("tenant") or "").strip().lower(),
        "locale": str(body.get("locale") or "id").strip().lower(),
        "report_id": str(body.get("report_id") or "").strip(),
    }

def locale_to_region(locale_str: Optional[str]) -> str:
    loc = (locale_str or "").strip().lower()
    return LOCALE_TO_REGION.get(loc, "ID")

# --- Helpers lama untuk kompatibilitas ---
API_KEY = os.getenv("API_KEY", "cdcd0b30-334a-45e6-a340-488b91b96e1d")
EXPECTED_APIKEY = API_KEY

def _get_header(req, key: str) -> str:
    return (req.headers.get(key) or req.headers.get(key.title()) or req.headers.get(key.lower()) or "").strip()

def require_llm_headers(req):
    """
    Validasi untuk /llm-claude:
      - X-APIKey (header)
      - report_id & type_of_check (body)
    """
    x_api = _read_api_key(req)
    if not x_api:
        return False, "Missing header X-APIKey", None
    if not _api_key_valid(x_api):
        return False, "Invalid X-APIKey", None

    if not req.is_json:
        return False, "Body must be JSON", None
    body = req.get_json(silent=True) or {}

    report_id = str(body.get("report_id") or "").strip()
    if not report_id:
        return False, "Missing body field report_id", None

    toc_type = str(body.get("type_of_check") or "").strip()
    if not toc_type:
        return False, "Missing body field type_of_check", None

    return True, "", {"report_id": report_id, "toc_type": toc_type}

def require_unmask_headers(req):
    """
    Validasi untuk /unmask:
      - X-APIKey (header)
      - report_id (body)
      - opsional: message_field (body atau querystring)
    """
    api = _read_api_key(req)
    if not api:
        return False, "Missing X-APIKey", None
    if not _api_key_valid(api):
        return False, "Invalid X-APIKey", None

    if not req.is_json:
        return False, "Body must be JSON", None
    body = req.get_json(silent=True) or {}

    report_id = str(body.get("report_id") or "").strip()
    if not report_id:
        return False, "Missing body field report_id", None

    field = str(body.get("message_field") or "").strip()
    if not field:
        field = (req.args.get("field") or "message_02").strip()

    return True, "ok", {"report_id": report_id, "field": field}

# --- Path helper ---
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

def get_env_path(key: str, default_relative: str) -> Path:
    """
    Ambil path dari ENV kalau valid;
    fallback ke HOST_<KEY> atau ../<default_relative>.
    """
    candidates = []
    if os.getenv(key):
        candidates.append(os.getenv(key))
    if os.getenv(f"HOST_{key}"):
        candidates.append(os.getenv(f"HOST_{key}"))
    candidates.append(str(_project_root() / default_relative))

    for raw in candidates:
        p = Path(raw)
        if not p.is_absolute():
            p = _project_root() / p
        if p.exists():
            return p.resolve()

    fallback = (_project_root() / default_relative).resolve()
    logger.warning("All path candidates for %s not found. Fallback to %s", key, fallback)
    return fallback
