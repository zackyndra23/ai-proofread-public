from app.modules.result_analyse import services as svc


def test_is_activated_requires_result_analyze_and_store_gsheets(monkeypatch):
    monkeypatch.setenv("RESULT_ANALYZE", "ACTIVATE")
    monkeypatch.setenv("STORE_GSHEETS", "1")
    assert svc.is_activated() is True


def test_is_activated_disabled_when_store_gsheets_off(monkeypatch):
    monkeypatch.setenv("RESULT_ANALYZE", "ACTIVATE")
    monkeypatch.setenv("STORE_GSHEETS", "0")
    assert svc.is_activated() is False


def test_is_activated_disabled_when_result_analyze_inactive(monkeypatch):
    monkeypatch.setenv("RESULT_ANALYZE", "INACTIVE")
    monkeypatch.setenv("STORE_GSHEETS", "1")
    assert svc.is_activated() is False
