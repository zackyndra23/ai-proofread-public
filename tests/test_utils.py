from flask import request
from services import utils


def test_require_headers_valid(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1,k2")
    with flask_app.test_request_context(headers={"X-APIKey": "k2"}):
        ok, msg = utils.require_headers(request)
        assert ok is True
        assert msg == ""


def test_require_headers_missing(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(headers={}):
        ok, msg = utils.require_headers(request)
        assert ok is False
        assert "Missing" in msg


def test_extract_headers(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(
        headers={"X-APIKey": "k1"},
        json={"type_of_check": "general", "tenant": "Indonesia", "locale": "ID", "report_id": "r1"},
    ):
        data = utils.extract_headers(request)
        assert data["apikey"] == "k1"
        assert data["tenant"] == "indonesia"
        assert data["locale"] == "id"
        assert data["report_id"] == "r1"


def test_read_locale(flask_app):
    with flask_app.test_request_context(json={"locale": "ID"}):
        assert utils._read_locale(request) == "id"


def test_read_locale_missing_returns_empty(flask_app):
    with flask_app.test_request_context(json={}):
        assert utils._read_locale(request) == ""


def test_require_llm_headers_ok(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(
        headers={"X-APIKey": "k1"},
        json={"report_id": "r1", "type_of_check": "general"},
    ):
        ok, msg, data = utils.require_llm_headers(request)
        assert ok is True
        assert msg == ""
        assert data["report_id"] == "r1"


def test_require_llm_headers_missing_fields(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(headers={"X-APIKey": "k1"}, json={}):
        ok, msg, _ = utils.require_llm_headers(request)
        assert ok is False
        assert "Missing" in msg


def test_require_headers_invalid(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(headers={"X-APIKey": "bad"}):
        ok, msg = utils.require_headers(request)
        assert ok is False
        assert "Invalid" in msg


def test_get_header_case_variants(flask_app):
    with flask_app.test_request_context(headers={"x-api-key": "v1"}):
        assert utils._get_header(request, "X-API-Key") == "v1"


def test_require_llm_headers_missing_and_invalid(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(headers={}):
        ok, msg, _ = utils.require_llm_headers(request)
        assert ok is False
        assert "Missing" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "bad"}, json={"report_id": "r1", "type_of_check": "x"}):
        ok, msg, _ = utils.require_llm_headers(request)
        assert ok is False
        assert "Invalid" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "k1"}):
        ok, msg, _ = utils.require_llm_headers(request)
        assert ok is False
        assert "Body must be JSON" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "k1"}, json={"type_of_check": "x"}):
        ok, msg, _ = utils.require_llm_headers(request)
        assert ok is False
        assert "report_id" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "k1"}, json={"report_id": "r1"}):
        ok, msg, _ = utils.require_llm_headers(request)
        assert ok is False
        assert "type_of_check" in msg


def test_require_unmask_headers_query_field(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(
        headers={"X-APIKey": "k1"},
        json={"report_id": "r1"},
        query_string={"field": "message_03"},
    ):
        ok, msg, data = utils.require_unmask_headers(request)
        assert ok is True
        assert data["field"] == "message_03"


def test_require_unmask_headers_errors(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    with flask_app.test_request_context(headers={}):
        ok, msg, _ = utils.require_unmask_headers(request)
        assert ok is False
        assert "Missing" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "bad"}, json={"report_id": "r1"}):
        ok, msg, _ = utils.require_unmask_headers(request)
        assert ok is False
        assert "Invalid" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "k1"}):
        ok, msg, _ = utils.require_unmask_headers(request)
        assert ok is False
        assert "Body must be JSON" in msg

    with flask_app.test_request_context(headers={"X-APIKey": "k1"}, json={}):
        ok, msg, _ = utils.require_unmask_headers(request)
        assert ok is False
        assert "report_id" in msg


def test_locale_to_region():
    assert utils.locale_to_region("id") == "ID"
    assert utils.locale_to_region("ms") == "MS"
    assert utils.locale_to_region("en") == utils.DEFAULT_EN_REGION


def test_get_env_path_prefers_env(monkeypatch, tmp_path):
    target = tmp_path / "prompts"
    target.mkdir()
    monkeypatch.setenv("LLM_PROMPT_DIR", str(target))
    path = utils.get_env_path("LLM_PROMPT_DIR", "llm_prompt")
    assert path == target.resolve()


def test_get_env_path_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_PROMPT_DIR", raising=False)
    monkeypatch.delenv("HOST_LLM_PROMPT_DIR", raising=False)

    default_dir = tmp_path / "llm_prompt"
    default_dir.mkdir()

    monkeypatch.setattr(utils, "_project_root", lambda: tmp_path)
    path = utils.get_env_path("LLM_PROMPT_DIR", "llm_prompt")
    assert path == default_dir.resolve()


def test_get_env_path_warns_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_PROMPT_DIR", raising=False)
    monkeypatch.delenv("HOST_LLM_PROMPT_DIR", raising=False)

    monkeypatch.setattr(utils, "_project_root", lambda: tmp_path)

    called = {}
    def _warn(*args, **kwargs):
        called["warned"] = True

    monkeypatch.setattr(utils.logger, "warning", _warn)

    path = utils.get_env_path("LLM_PROMPT_DIR", "llm_prompt")
    assert path == (tmp_path / "llm_prompt").resolve()
    assert called.get("warned") is True
