import os, os.path as p

class Config:
  # Flags lama (biarkan)
  AUTO_CHAIN_LLM       = os.getenv("AUTO_CHAIN_LLM", "1").lower() in ("1","true","yes")
  AUTO_CHAIN_UNMASK    = os.getenv("AUTO_CHAIN_UNMASK", "1").lower() in ("1","true","yes")
  AUTO_CHAIN_REFORMAT  = os.getenv("AUTO_CHAIN_REFORMAT", "1").lower() in ("1","true","yes")

  #Max Token Setting
  MAX_INPUT_TOKEN = int(os.getenv("MAX_INPUT_TOKEN", "0") or "0")  # 0 = unlimited
  ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

  # Rate limit
  RATE_LIMIT_RPS       = int(os.getenv("RATE_LIMIT_RPS", "20"))
  RATE_LIMIT_WINDOW    = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))

  # API versioning
  API_PREFIX           = os.getenv("API_PREFIX", "")
  API_VERSION          = os.getenv("API_VERSION", "v1")   # ← ubah ke v2 nanti

  # App version (isi via env/CI)
  APP_VERSION          = os.getenv("APP_VERSION", "0.1.0")
  BUILD                = os.getenv("BUILD", "")
  GIT_SHA              = os.getenv("GIT_SHA", "")
  BUILD_AT             = os.getenv("BUILD_AT", "")

  # NER
  BASE_DIR             = p.dirname(p.dirname(__file__))
  NER_BASE_DIR         = p.normpath(p.join(BASE_DIR, "..", "ner_model"))
  TENANT2MODEL = {
    "indonesia": "indonlu_ner_grit",
    "malaysia":  "malay_ner_finetuned_300725_10h50_set01",
    "thailand":  "thai_nner",
  }

  # semantic text guard
  TEXT_SEMANTIC_MIN_CHARS = int(os.getenv("TEXT_SEMANTIC_MIN_CHARS", "40"))
  TEXT_SEMANTIC_MIN_WORDS = int(os.getenv("TEXT_SEMANTIC_MIN_WORDS", "10"))
  LLM_SEMANTIC_VALIDATION = int(os.getenv("LLM_SEMANTIC_VALIDATION", "1"))

    # === Security toggles ================================================
  @staticmethod
  def _on(v: str | None, default: str = "on") -> bool:
      if v is None:
          v = default
      return str(v).strip().lower() not in ("0", "false", "off", "no", "")

  DETECT_SQLI  = _on.__func__(os.getenv("SQL_INJECTION"), default="off")
  DETECT_HTML  = _on.__func__(os.getenv("HTML_FORMAT"),   default="off")
  # Reject input teks yang hanya simbol/angka (tanpa huruf)
  REJECT_SYMBOL_ONLY     = _on.__func__(os.getenv("REJECT_SYMBOL_ONLY"), default="off")

  # === Data Masking Model Improvement ================================
  # Strict toggle: hanya nilai "ON" (case-insensitive) yang mengaktifkan.
  # Default OFF (fail-safe) — termasuk env tidak diset, kosong, atau typo.
  MASKING_RESULTS_FEATURE = (os.getenv("MASKING_RESULTS_FEATURE") or "").strip().upper() == "ON"