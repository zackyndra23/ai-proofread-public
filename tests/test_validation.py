import pytest
from app.core import validation as v


def test_validate_payload_strict_non_dict(flask_ctx):
    resp = v.validate_payload_strict("nope", {"a"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "INVALID_JSON_PAYLOAD"


def test_validate_payload_strict_unknown_fields(flask_ctx):
    resp = v.validate_payload_strict({"a": 1, "b": 2}, {"a"})
    data = resp.get_json()
    assert data["error"] == "UNKNOWN_FIELDS"
    assert "b" in data["message"]


def test_validate_locale_tenant_normalizes(flask_ctx):
    payload = {"locale": "ID", "tenant": "Indonesia"}
    resp = v.validate_locale_tenant(payload)
    assert resp is None
    assert payload["locale"] == "id"
    assert payload["tenant"] == "indonesia"


def test_validate_locale_tenant_missing_locale(flask_ctx):
    resp = v.validate_locale_tenant({"tenant": "indonesia"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "MISSING_LOCALE"


def test_validate_locale_tenant_missing_tenant(flask_ctx):
    resp = v.validate_locale_tenant({"locale": "id"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "MISSING_TENANT"


def test_validate_locale_tenant_unsupported_locale(flask_ctx):
    resp = v.validate_locale_tenant({"locale": "xx", "tenant": "indonesia"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "UNSUPPORTED_LOCALE"


def test_validate_locale_tenant_unsupported_tenant(flask_ctx):
    resp = v.validate_locale_tenant({"locale": "id", "tenant": "other"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "UNSUPPORTED_TENANT"


def test_error_response_with_detail(flask_ctx):
    resp = v._error_response_with_detail("bad", "ERR", 400, {"x": 1})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["detail"]["x"] == 1


def test_contains_html_and_sql():
    assert v.contains_html_or_xss("<b>hi</b>") is True
    assert v.contains_html_or_xss("javascript:alert(1)") is True
    assert v.contains_html_or_xss("plain") is False
    assert v.contains_html_or_xss(123) is False

    assert v.contains_sql_like("SELECT * FROM users") is True
    assert v.contains_sql_like("hello") is False
    assert v.contains_sql_like(123) is False


def test_scan_payload_detects_malicious():
    bad, reason = v.scan_payload({"$where": "x"})
    assert bad is True
    assert "forbidden key" in reason

    bad, _ = v.scan_payload({"data": "<script>alert(1)</script>"}, enable_html=True, enable_sql=False)
    assert bad is True

    bad, _ = v.scan_payload({"data": "SELECT * FROM users"}, enable_html=False, enable_sql=True)
    assert bad is True

    bad, _ = v.scan_payload({"data": "<b>ok</b>"}, enable_html=False, enable_sql=False)
    assert bad is False


def test_scan_payload_none():
    bad, reason = v.scan_payload(None)
    assert bad is False
    assert reason == ""


def test_scan_payload_list_branch():
    bad, reason = v.scan_payload(["ok", "<script>alert(1)</script>"], enable_html=True, enable_sql=False)
    assert bad is True
    assert "HTML" in reason


def test_validate_and_scan_sanitizes(flask_ctx):
    payload = {"data": "<b>Hi</b>"}
    resp = v.validate_and_scan(payload, {"data"}, reject_on_html=False, enable_html=False, enable_sql=False)
    assert resp is None
    assert payload["data"] == "Hi"


def test_validate_and_scan_bad_shape(flask_ctx):
    resp = v.validate_and_scan({"a": 1, "b": 2}, {"a"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "UNKNOWN_FIELDS"


def test_validate_and_scan_malicious(flask_ctx):
    payload = {"data": "<script>1</script>"}
    resp = v.validate_and_scan(payload, {"data"}, reject_on_html=True, enable_html=True, enable_sql=False)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "MALICIOUS_PAYLOAD"


def test_sanitize_text_strict_removes_tags():
    assert v.sanitize_text_strict("<b>Hi</b>") == "Hi"


def test_sanitize_allowlist():
    assert v.sanitize_allowlist("<b>Hi</b>", allowed_tags=["b"]) == "<b>Hi</b>"
    assert v.sanitize_allowlist("<i>Hi</i>", allowed_tags=["b"]) == "Hi"


def test_count_tokens_with_encoder(monkeypatch):
    class DummyTok:
        def encode(self, text):
            return [1, 2, 3]

    monkeypatch.setattr(v, "_tokenizer", DummyTok())
    assert v.count_tokens("abc") == 3


def test_count_tokens_callable_tokenizer(monkeypatch):
    monkeypatch.setattr(v, "_tokenizer", lambda text: [1, 2])
    assert v.count_tokens("abc") == 2


def test_count_tokens_empty_and_fallback():
    assert v._count_tokens_fallback("") == 0
    assert v.count_tokens("") == 0


def test_count_tokens_encode_exception(monkeypatch):
    class DummyTok:
        def encode(self, text):
            raise RuntimeError("boom")

    monkeypatch.setattr(v, "_tokenizer", DummyTok())
    out = v.count_tokens("abcd")
    assert out >= 1


def test_ensure_under_input_token_limit_raises(monkeypatch):
    monkeypatch.setattr(v, "_tokenizer", None)
    with pytest.raises(ValueError):
        v.ensure_under_input_token_limit(["abcdefghij"], limit=1, context_name="input")


def test_ensure_under_input_token_limit_unlimited():
    total = v.ensure_under_input_token_limit(["abc"], limit=0, context_name="input")
    assert total >= 1


def test_is_symbol_only_text():
    bad, _ = v.is_symbol_only_text("12345")
    assert bad is True
    bad, _ = v.is_symbol_only_text("abc 123")
    assert bad is False
    bad, _ = v.is_symbol_only_text(123)
    assert bad is True
    bad, _ = v.is_symbol_only_text("")
    assert bad is True


def test_validation_tokenizer_import_paths(monkeypatch):
    import runpy
    import types
    import sys
    import builtins

    fake = types.ModuleType("anthropic_tokenizer")
    fake.get_tokenizer = lambda: (lambda text: [1, 2, 3])
    monkeypatch.setitem(sys.modules, "anthropic_tokenizer", fake)

    res = runpy.run_module("app.core.validation", run_name="__validation_tokenizer__")
    assert res["_tokenizer"] is not None

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("anthropic_tokenizer", "tiktoken"):
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("anthropic_tokenizer", None)
    sys.modules.pop("tiktoken", None)
    res2 = runpy.run_module("app.core.validation", run_name="__validation_tokenizer_none__")
    assert res2["_tokenizer"] is None
