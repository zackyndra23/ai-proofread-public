from app.modules.reformat import services as rs


def test_reformat_service_run(monkeypatch):
    monkeypatch.setattr(rs, "apply_reformatting", lambda text, locale: ("X", {"ok": True}))
    out, meta = rs.ReformatService().run("hi", "id")
    assert out == "X"
    assert meta["ok"] is True
