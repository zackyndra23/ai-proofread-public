from app.core import text_semantic as ts


def test_validate_semantic_text_too_short(monkeypatch):
    monkeypatch.setattr(ts, "_MIN_CHARS", 5)
    monkeypatch.setattr(ts, "_MIN_WORDS", 1)
    monkeypatch.setattr(ts, "_USE_LLM", False)
    res = ts.validate_semantic_text("id", "hi")
    assert res["reason"] == "too_short"


def test_validate_semantic_text_too_few_words(monkeypatch):
    monkeypatch.setattr(ts, "_MIN_CHARS", 1)
    monkeypatch.setattr(ts, "_MIN_WORDS", 3)
    monkeypatch.setattr(ts, "_USE_LLM", False)
    res = ts.validate_semantic_text("id", "hello world")
    assert res["reason"] == "too_few_words"


def test_validate_semantic_text_length_only_ok(monkeypatch):
    monkeypatch.setattr(ts, "_MIN_CHARS", 1)
    monkeypatch.setattr(ts, "_MIN_WORDS", 1)
    monkeypatch.setattr(ts, "_USE_LLM", False)
    res = ts.validate_semantic_text("id", "hello world")
    assert res["passes"] is True
    assert res["reason"] == "length_only_ok"


def test_validate_semantic_text_llm_path(monkeypatch):
    monkeypatch.setattr(ts, "_MIN_CHARS", 1)
    monkeypatch.setattr(ts, "_MIN_WORDS", 1)
    monkeypatch.setattr(ts, "_USE_LLM", True)
    monkeypatch.setattr(ts, "_semantic_check_with_llm", lambda locale, text: {"passes": True, "reason": "ok_llm", "quality_score": 0.9, "used_llm": True})
    res = ts.validate_semantic_text("id", "hello world")
    assert res["passes"] is True
    assert res["used_llm"] is True


def test_semantic_check_with_llm(monkeypatch):
    monkeypatch.setattr(ts, "call_claude_json", lambda prompt, max_tokens=200: {"is_meaningful": True, "quality_score": 0.8, "reasons": "ok"})
    res = ts._semantic_check_with_llm("id", "hello world")
    assert res["passes"] is True
    assert res["used_llm"] is True


def test_semantic_check_with_llm_fallback_template(monkeypatch):
    import builtins
    import io

    def fake_open(*args, **kwargs):
        return io.StringIO("Locale: {LOCALE}\nTEXT:\n<<<\n{TEXT}\n>>>")

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(ts, "call_claude_json", lambda prompt, max_tokens=200: {"is_meaningful": True, "quality_score": "bad", "reasons": "x"})
    res = ts._semantic_check_with_llm("id", "hello world")
    assert res["passes"] is True
    assert res["quality_score"] == 0.0
    assert res["reasons"] == "x"


def test_semantic_check_with_llm_non_dict(monkeypatch):
    monkeypatch.setattr(ts, "call_claude_json", lambda prompt, max_tokens=200: "oops")
    res = ts._semantic_check_with_llm("id", "hello world")
    assert res["passes"] is False
    assert res["reason"] == "not_meaningful"
