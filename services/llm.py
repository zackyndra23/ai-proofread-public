import os
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from services.utils import get_env_path
import json

try:
    import anthropic
except Exception:
    anthropic = None

# Ambil dari ENV: LLM_PROMPT_DIR (fallback: folder "llm_prompt" di root project)
PROMPT_DIR = get_env_path("LLM_PROMPT_DIR", "llm_prompt")  # -> Path object
PROMPT_DIR_PLAIN = get_env_path("LLM_PROMPT_DIR_PLAIN", "llm_prompt/plain")

# LOCALE_LANG_LABELS = {
#     "id": "Indonesian",
#     "en": "English",
#     "ms": "Malay",
#     "th": "Thai",
# }
LOCALE_LANG_LABELS = {
    "id": "Indonesian",
    "en": "English",
    "ms": "Malay"
}

# ------------------------------------------------------------
# Token helpers
# ------------------------------------------------------------
TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")

def tokens_preserved(src_text: str, out_text: str, token_list: Optional[List[str]] = None) -> bool:
    """
    Ensure every token present in src_text (or in token_list if provided)
    also appears verbatim in out_text. Order is not enforced here.
    """
    if token_list is None:
        token_list = []
        seen = set()
        for m in TOKEN_RE.finditer(src_text or ""):
            t = m.group(0)
            if t not in seen:
                seen.add(t)
                token_list.append(t)
    return all(t in (out_text or "") for t in token_list)

# ------------------------------------------------------------
# Prompt loading/rendering (FIXED)
# ------------------------------------------------------------
from pathlib import Path
from typing import Optional, List, Tuple

def _choose_prompt_file(toc_type: str, fmt_txt: str) -> Path:
    fmt = _normalize_format(fmt_txt)
    prompt_root = PROMPT_DIR_PLAIN if fmt == "plain" else PROMPT_DIR

    tt = (toc_type or "").strip().lower()
    if tt == "employment-check":
        fname = "employment_check_prompt.txt"
    elif tt == "reference-check":
        fname = "reference_check_prompt.txt"
    elif tt == "address-check":
        fname = "address_check_prompt.txt"
    else:
        fname = "general_prompt.txt"

    return (prompt_root / fname).resolve()


def _read_file(path: Path) -> str:
    """
    Baca file prompt sebagai UTF-8. Lempar FileNotFoundError kalau tidak ada.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")

def _render_prompt(
    toc_type: str,
    text: str,
    fmt_txt: str,
    token_list: Optional[List[str]],
    locale: Optional[str] = None,
) -> Tuple[str, str, str]:
    
    path = _choose_prompt_file(toc_type, fmt_txt)
    base_prompt = _read_file(path)

    # --- locale aware placeholders ---
    loc = (locale or "").lower().strip()
    lang_label = LOCALE_LANG_LABELS.get(loc, "target")

    ordered = token_list[:] if token_list else []
    if not ordered:
        seen = set()
        for m in TOKEN_RE.finditer(text or ""):
            t = m.group(0)
            if t not in seen:
                seen.add(t)
                ordered.append(t)

    critical = (
        "[CRITICAL — TOKEN PRESERVATION]\n"
        "- Keep every bracketed masking token EXACTLY as-is (same brackets, underscores, numbers, casing).\n"
        "- Do NOT delete, modify, split, merge, reorder, or invent tokens.\n"
        "- Preserve tokens in the SAME POSITIONS (left-to-right) as input.\n"
        f"- Allowed tokens (in order): {' '.join(ordered)}\n"
    )

    # Idempotent prepend:
    prompt = base_prompt if "[CRITICAL — TOKEN PRESERVATION]" in base_prompt else (critical + "\n" + base_prompt)

    # locale placeholders
    loc = (locale or "").lower().strip()
    lang_label = LOCALE_LANG_LABELS.get(loc, "target")
    if loc:
        prompt = prompt.replace("{{LOCALE_CODE}}", loc)
    else:
        prompt = prompt.replace("{{LOCALE_CODE}}", "")
    prompt = prompt.replace("{{LOCALE_LANG_NAME}}", lang_label)

    # text placeholder
    prompt = prompt.replace("{{text}}", text or "")

    return str(path), path.name, prompt

# ------------------------------------------------------------
# Claude call
# ------------------------------------------------------------
ALLOWED_FORMATS = {"html", "markdown", "plain"}

def _normalize_format(fmt: str) -> str:
    f = (fmt or "").strip().lower()
    # alias umum
    if f in ("md",): f = "markdown"
    if f in ("text", "txt"): f = "plain"
    return f

# Wajib pakai keyword-only params (tanda *):
def call_claude(
    *,
    text: str,
    toc_type: str,
    fmt_txt: str,               # <-- WAJIB
    locale: Optional[str] = None,
    tenant: Optional[str] = None,
    token_list: Optional[List[str]] = None,
) -> Tuple[str, Dict]:
    if anthropic is None:
        raise RuntimeError("anthropic SDK is not installed. Please `pip install anthropic`")

    fmt_txt = _normalize_format(fmt_txt)
    if not fmt_txt or fmt_txt not in ALLOWED_FORMATS:
        raise ValueError(f"fmt_txt is required and must be one of {sorted(ALLOWED_FORMATS)}")

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is empty. Set it in .env")

    model       = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    max_tokens  = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    temperature = float(os.getenv("LLM_TEMPERATURE", "0"))

    client = anthropic.Anthropic(api_key=api_key)

    # render prompt (gunakan fmt_txt)
    prompt_path, prompt_file, prompt = _render_prompt(
        toc_type,
        text,
        fmt_txt,
        token_list,
        locale=locale,
    )

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )

    out = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", "") == "text":
            out.append(getattr(block, "text", ""))
    out_text = "\n".join(out).strip()

    usage_obj = getattr(resp, "usage", None)
    meta = {
        "model":       getattr(resp, "model", model),
        "id":          getattr(resp, "id", None),
        "stop_reason": getattr(resp, "stop_reason", None),
        "usage": {
            "input_tokens":  getattr(usage_obj, "input_tokens", None),
            "output_tokens": getattr(usage_obj, "output_tokens", None),
        },
        "prompt": prompt,
        "prompt_path": str(prompt_path),
        "prompt_file": prompt_file,
        "fmt_txt": fmt_txt,     # simpan jejak format yang dipakai
        "toc_type": toc_type,
    }
    return out_text, meta

def call_claude_json(prompt: str, max_tokens: int = 200, model: Optional[str] = None) -> dict:
    """
    Kirim prompt ke Claude dan harapkan balikan JSON (dict).
    Mengembalikan {} jika:
      - anthropic SDK belum terpasang
      - API key kosong
      - parsing JSON gagal
    """
    if anthropic is None:
        return {}

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            # NB: system prompt opsional, lang_detect.py sudah format prompt-nya ketat
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return {}

    # Ambil teks dari response content
    try:
        text = "".join(getattr(part, "text", "") for part in (resp.content or []))
    except Exception:
        text = ""

    # Parse JSON langsung; jika gagal, coba ekstrak blok {...} terluar
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}