from typing import Dict, Any
import re

from services.llm import call_claude_json
from app.core.config import Config

cfg = Config()

# Ambang dari ENV / Config
_MIN_CHARS = cfg.TEXT_SEMANTIC_MIN_CHARS
_MIN_WORDS = cfg.TEXT_SEMANTIC_MIN_WORDS  
_USE_LLM = bool(cfg.LLM_SEMANTIC_VALIDATION)

# Reuse normalizer sederhana (mirip lang_detect)
_WS = re.compile(r"\s+")
_TOKEN_PATTERN = re.compile(r"\[[A-Z_0-9]+\]")


def _strip_tokens(text: str) -> str:
    # buang token masking seperti [PER_0], [LOC_1], dll ke spasi
    return _TOKEN_PATTERN.sub(" ", text or "")


def _clean_for_semantic(text: str, limit: int = 4000) -> str:
    t = (text or "")[:limit]
    # buang URL & angka panjang supaya nggak ngacaukan heuristik
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\d{3,}", " ", t)
    t = _WS.sub(" ", t).strip()
    return t


def _split_words(text: str):
    text = _WS.sub(" ", text).strip()
    return [w for w in text.split(" ") if w]


def _semantic_check_with_llm(locale: str, text: str) -> Dict[str, Any]:
    """
    Pakai Claude buat cek apakah teks mengandung makna yang cukup
    untuk di-proofread. Diaktifkan kalau LLM_SEMANTIC_VALIDATION=1.
    """
    try:
        with open("llm_prompt/plain/text_semantic_guard_prompt.txt", "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        template = (
            "You are a strict text quality validator for a proofreading API.\n"
            "Locale: {LOCALE}\n"
            "Decide if the text below is meaningful enough to be proofread "
            "(not random characters, not only one word, not pure noise).\n"
            "Return ONLY JSON with keys: is_meaningful (bool), quality_score (0-1), reasons (string).\n"
            "TEXT:\n<<<\n{TEXT}\n>>>"
        )

    prompt = template.replace("{LOCALE}", locale or "") \
                     .replace("{TEXT}", text[:4000])

    data = call_claude_json(prompt, max_tokens=200)

    if isinstance(data, dict):
        is_meaningful = bool(data.get("is_meaningful", False))
        try:
            score = float(data.get("quality_score", 0.0) or 0.0)
        except Exception:
            score = 0.0
        reasons = data.get("reasons", "")
    else:
        is_meaningful = False
        score = 0.0
        reasons = ""

    return {
        "passes": is_meaningful,
        "reason": "not_meaningful" if not is_meaningful else "ok_llm",
        "quality_score": score,
        "reasons": reasons,
        "used_llm": True,
    }


def validate_semantic_text(locale: str, text: str) -> Dict[str, Any]:
    """
    Entry point utama (dipanggil dari routes):

    1) Bersihkan text → hitung chars & words.
    2) Jika chars < MIN_CHARS → FAIL (reason='too_short', tanpa LLM).
    3) Jika words < MIN_WORDS → FAIL (reason='too_few_words', tanpa LLM).
    4) Jika cukup panjang:
       - Kalau LLM_SEMANTIC_VALIDATION=0 → PASS (length_only_ok).
       - Kalau =1 → panggil Claude; kalau meaningful → PASS,
         kalau tidak → FAIL (reason='not_meaningful').
    """
    cleaned = _clean_for_semantic(_strip_tokens(text))
    words = _split_words(cleaned)
    chars = len(cleaned)

    result: Dict[str, Any] = {
        "chars": chars,
        "words": len(words),
        "min_chars": _MIN_CHARS,
        "min_words": _MIN_WORDS,
        "used_llm": False,
        "passes": False,
        "reason": "",
    }

    # 1) Terlalu pendek secara karakter → langsung tolak
    if chars < _MIN_CHARS:
        result["reason"] = "too_short"
        return result

    # 2) Terlalu sedikit kata → langsung tolak
    if len(words) < _MIN_WORDS:
        result["reason"] = "too_few_words"
        return result

    # 3) Panjang cukup, tapi LLM semantic check dimatikan → auto PASS
    if not _USE_LLM:
        result["passes"] = True
        result["reason"] = "length_only_ok"
        return result

    # 4) Panjang cukup & LLM_SEMANTIC_VALIDATION=1 → tanya Claude
    llm_res = _semantic_check_with_llm(locale, cleaned)
    result.update(llm_res)
    # result["reason"] sudah di-set 'not_meaningful' atau 'ok_llm' di llm_res
    result["passes"] = bool(llm_res.get("passes", False))
    return result