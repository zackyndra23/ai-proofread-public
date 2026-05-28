from app.core import lang_detect as ld


def test_clean_for_detection_removes_noise():
    text = "hi  https://example.com  123456   ok"
    out = ld._clean_for_detection(text)
    assert "http" not in out
    assert "123456" not in out
    assert "  " not in out


def test_iso_from_lingua_none_and_unknown():
    assert ld._iso_from_lingua(None) == ""

    class Lang:
        name = "UNKNOWN"

    assert ld._iso_from_lingua(Lang()) == ""


def test_detect_lingua_no_detector(monkeypatch):
    monkeypatch.setattr(ld, "_lingua_detector", None)
    lang, conf = ld._detect_lingua("hello")
    assert lang == ""
    assert conf == 0.0


def test_detect_lingua_no_lang_obj(monkeypatch):
    class Det:
        def detect_language_of(self, text):
            return None

        def compute_language_confidence(self, text, lang_obj):
            raise AssertionError("should not be called")

    monkeypatch.setattr(ld, "_lingua_detector", Det())
    lang, conf = ld._detect_lingua("hello")
    assert lang == ""
    assert conf == 0.0


def test_detect_language_primary_too_short(monkeypatch):
    monkeypatch.setattr(ld, "_MIN_CHARS", 10)
    res = ld.detect_language_primary("hi")
    assert res["reason"] == "text_too_short"


def test_detect_language_primary_no_detection(monkeypatch):
    monkeypatch.setattr(ld, "_lingua_detector", None)
    monkeypatch.setattr(ld, "_MIN_CHARS", 1)
    res = ld.detect_language_primary("hello")
    assert res["reason"] == "lingua_no_detection"


def test_detect_language_primary_with_stub(monkeypatch):
    class Lang:
        name = "INDONESIAN"

    class Det:
        def detect_language_of(self, text):
            return Lang()

        def compute_language_confidence(self, text, lang_obj):
            return 0.95

    monkeypatch.setattr(ld, "_lingua_detector", Det())
    monkeypatch.setattr(ld, "_MIN_CHARS", 1)
    res = ld.detect_language_primary("ini teks")
    assert res["lang"] == "id"
    assert res["source"] == "lingua"


def test_language_matches_locale_allow_close():
    assert ld.language_matches_locale("my", "id", allow_close=True) is True


def test_detect_language_with_llm_disabled(monkeypatch):
    monkeypatch.setattr(ld, "_USE_LLM", False)
    assert ld.detect_language_with_llm("hello") is None


def test_detect_language_with_llm_fallback_template(monkeypatch):
    import builtins
    import services.llm as llm

    monkeypatch.setattr(ld, "_USE_LLM", True)
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(llm, "call_claude_json", lambda prompt: {"lang": "ID", "confidence": "bad", "reasons": "x"})

    out = ld.detect_language_with_llm("hello world")
    assert out["lang"] == "id"
    assert out["confidence"] == 0.0
    assert out["source"] == "llm"
    assert out["reasons"] == "x"


def test_detect_language_with_llm_no_lang(monkeypatch):
    import services.llm as llm

    monkeypatch.setattr(ld, "_USE_LLM", True)
    monkeypatch.setattr(llm, "call_claude_json", lambda prompt: {"confidence": 0.9})
    assert ld.detect_language_with_llm("hello") is None


def test_validate_language_locale_mismatch_no_llm(monkeypatch):
    monkeypatch.setattr(ld, "_CONF_MIN", 0.5)
    monkeypatch.setattr(ld, "detect_language_primary", lambda text: {"lang": "en", "confidence": 0.9, "source": "lingua"})
    monkeypatch.setattr(ld, "detect_language_with_llm", lambda text: None)
    res = ld.validate_language_locale("id", "hello world")
    assert res["passes"] is False
    assert res["reason"] == "locale_language_mismatch"


def test_validate_language_locale_llm_pass(monkeypatch):
    monkeypatch.setattr(ld, "detect_language_primary", lambda text: {"lang": "en", "confidence": 0.2, "source": "lingua"})
    monkeypatch.setattr(ld, "detect_language_with_llm", lambda text: {"lang": "id", "confidence": 0.9, "source": "llm"})
    res = ld.validate_language_locale("id", "halo dunia")
    assert res["passes"] is True
    assert res["used_llm"] is True
    assert res["final_lang"] == "id"


def test_validate_language_locale_llm_mismatch(monkeypatch):
    monkeypatch.setattr(ld, "detect_language_primary", lambda text: {"lang": "en", "confidence": 0.2, "source": "lingua"})
    monkeypatch.setattr(ld, "detect_language_with_llm", lambda text: {"lang": "en", "confidence": 0.9, "source": "llm"})
    res = ld.validate_language_locale("id", "hello")
    assert res["passes"] is False
    assert res["reason"] == "locale_language_mismatch_llm"


def test_validate_language_locale_undetected(monkeypatch):
    monkeypatch.setattr(ld, "detect_language_primary", lambda text: {"lang": "", "confidence": 0.0, "source": "none", "reason": "lingua_no_detection"})
    monkeypatch.setattr(ld, "detect_language_with_llm", lambda text: None)
    res = ld.validate_language_locale("id", "...")
    assert res["passes"] is False
    assert res["reason"] == "lingua_no_detection"


def test_validate_language_locale_primary_pass(monkeypatch):
    monkeypatch.setattr(ld, "_CONF_MIN", 0.5)
    monkeypatch.setattr(ld, "detect_language_primary", lambda text: {"lang": "id", "confidence": 0.9, "source": "lingua"})
    res = ld.validate_language_locale("id", "halo")
    assert res["passes"] is True
    assert res["used_llm"] is False


def test_validate_language_locale_low_confidence(monkeypatch):
    monkeypatch.setattr(ld, "_CONF_MIN", 0.9)
    monkeypatch.setattr(ld, "detect_language_primary", lambda text: {"lang": "id", "confidence": 0.1, "source": "lingua"})
    monkeypatch.setattr(ld, "detect_language_with_llm", lambda text: None)
    res = ld.validate_language_locale("id", "halo")
    assert res["passes"] is False
    assert res["reason"] == "low_confidence"


def test_lingua_import_failure_sets_detector_none(monkeypatch):
    import importlib
    import builtins
    import sys

    old = sys.modules.get("app.core.lang_detect")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "lingua":
            raise ImportError("no lingua")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    sys.modules.pop("app.core.lang_detect", None)
    mod = importlib.import_module("app.core.lang_detect")
    assert mod._lingua_detector is None
    if old is not None:
        sys.modules["app.core.lang_detect"] = old
