from typing import Dict, Any, Optional, Tuple
import os
import re

# --- ENV knobs ---
_MIN_CHARS = int(os.getenv("LANGUAGE_MIN_CHARS", "80"))
_CONF_MIN = float(os.getenv("LANGUAGE_CONFIDENCE_MIN", "0.85"))
_USE_LLM = os.getenv("LLM_LANG_VALIDATION", "0") == "1"

# --- locale -> allowed langs (ISO 639-1) ---
LOCALE_ALLOWED_LANGS = {
    "id": {"id"},              # Indonesian
#    "th": {"th"},              # Thai
    "ms": {"ms"},              # Malaysia: Malay (ms); toleransi id bila kamu mau
    "en": {"en"},
}

# --- light normalizer (jaga token masking tetap utuh) ---
_TOKEN_PATTERN = re.compile(r"\[[A-Z_0-9]+\]")
_WS = re.compile(r"\s+")

def _clean_for_detection(text: str, limit: int = 4000) -> str:
    t = text[:limit]
    t = re.sub(r"https?://\S+", " ", t)   # buang URL
    t = re.sub(r"\d{3,}", " ", t)         # buang angka panjang
    t = _WS.sub(" ", t).strip()
    return t

# --- LINGUA detector (pure-python; stabil untuk id/ms/th) ---
try:
    from lingua import Language, LanguageDetectorBuilder
    _LINGUA_LANGS = [
        Language.INDONESIAN,  # id
        Language.MALAY,       # ms
        Language.THAI,        # th
        Language.ENGLISH,     # en (buat teks campur)
        Language.SWAHILI,     # sw (mengurangi false-positive)
    ]
    _lingua_detector = LanguageDetectorBuilder.from_languages(*_LINGUA_LANGS).build()
except Exception:
    _lingua_detector = None

def _iso_from_lingua(lang_obj) -> str:
    if not lang_obj:
        return ""
    # mapping = {
    #     "INDONESIAN": "id",
    #     "MALAY": "ms",
    #     "THAI": "th",
    #     "ENGLISH": "en",
    #     "SWAHILI": "sw",
    # }
    mapping = {
        "INDONESIAN": "id",
        "MALAY": "ms",
        # "THAI": "th",
        "ENGLISH": "en",
        "SWAHILI": "sw",
    }
    return mapping.get(lang_obj.name, "").lower()

def _detect_lingua(text: str) -> Tuple[str, float]:
    if _lingua_detector is None:
        return "", 0.0
    lang_obj = _lingua_detector.detect_language_of(text)
    if not lang_obj:
        return "", 0.0
    conf = _lingua_detector.compute_language_confidence(text, lang_obj)  # 0..1
    return _iso_from_lingua(lang_obj), float(conf)

# --- Primary detector (Lingua-only) ---
def detect_language_primary(text: str) -> Dict[str, Any]:
    """
    Returns: {"lang": "id", "confidence": 0.93, "source": "lingua|none", "reason": "...?"}
    """
    snippet = _clean_for_detection(text)
    if len(snippet) < _MIN_CHARS:
        return {"lang": "", "confidence": 0.0, "source": "none", "reason": "text_too_short"}

    lang, conf = _detect_lingua(snippet)
    if not lang:
        return {"lang": "", "confidence": 0.0, "source": "none", "reason": "lingua_no_detection"}

    return {"lang": lang, "confidence": conf, "source": "lingua"}

# --- LLM fallback (Claude) ---
def detect_language_with_llm(text: str) -> Optional[Dict[str, Any]]:
    if not _USE_LLM:
        return None
    from services.llm import call_claude_json  # util kamu

    # muat prompt file
    try:
        with open("llm_prompt/plain/language_guard_prompt.txt", "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        template = (
            "You are a strict language validator.\n"
            "Return JSON with keys: lang, script, confidence, reasons.\n"
            "TEXT:\n<<<\n{TEXT_SNIPPET}\n>>>"
        )
    prompt = template.replace("{TEXT_SNIPPET}", text[:4000])

    data = call_claude_json(prompt)  # expected dict
    # contoh: {"lang":"id","script":"Latin","confidence":0.92,"reasons":"..."}
    if isinstance(data, dict) and "lang" in data:
        try:
            conf = float(data.get("confidence", 0.0) or 0.0)
        except Exception:
            conf = 0.0
        return {
            "lang": str(data.get("lang", "")).lower(),
            "confidence": conf,
            "source": "llm",
            "reasons": data.get("reasons", "")
        }
    return None

def language_matches_locale(locale: str, lang_iso2: str, allow_close: bool = False) -> bool:
    allowed = LOCALE_ALLOWED_LANGS.get(locale, set())
    if lang_iso2 in allowed:
        return True
    # Opsional: toleransi id<->ms. Ubah allow_close=True bila dibutuhkan.
    if allow_close and locale in {"id", "my"} and lang_iso2 in {"id", "ms"}:
        return True
    return False

def validate_language_locale(locale: str, text: str) -> Dict[str, Any]:
    """
    Main entry: dipanggil dari routes/validation sebelum proses proofread.
    1) Lingua → jika yakin & cocok → PASS
    2) Jika tidak yakin / mismatch → fallback ke Claude (jika diaktifkan)
    """
    first = detect_language_primary(text)
    lang = (first.get("lang") or "").lower()
    conf = float(first.get("confidence") or 0.0)

    result = {
        "detected_lang": lang,
        "confidence": conf,
        "source": first.get("source", "none"),
        "passes": False,
        "final_lang": lang,
        "used_llm": False,
        "reason": first.get("reason", "")
    }

    # PASS cepat jika yakin & match
    if lang and conf >= _CONF_MIN and language_matches_locale(locale, lang):
        result["passes"] = True
        return result

    # Ambiguous / mismatch → pakai LLM fallback bila diaktifkan
    llm_res = detect_language_with_llm(text)
    if llm_res:
        result["used_llm"] = True
        result["final_lang"] = llm_res["lang"]
        result["detected_lang"] = llm_res["lang"]
        result["confidence"] = llm_res.get("confidence", conf)
        result["source"] = llm_res.get("source", "llm")

        if language_matches_locale(locale, llm_res["lang"]):
            result["passes"] = True
            return result
        else:
            result["reason"] = "locale_language_mismatch_llm"
            return result

    # Gagal: tidak yakin atau mismatch
    if not lang:
        result["reason"] = result["reason"] or "undetected_low_confidence"
    elif not language_matches_locale(locale, lang):
        result["reason"] = "locale_language_mismatch"
    else:
        result["reason"] = "low_confidence"
    return result