from app.modules.htmlmask import routes as hr


def test_htmlmask_routes(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    monkeypatch.setattr(hr, "enforce_rps", lambda *a, **k: None)

    class DummySvc:
        def freeze(self, html):
            return {
                "html_skeleton": "S",
                "text_map": {},
                "table_map": {},
                "text_format": "",
                "table_format": [],
            }

        def reverse(self, skeleton, text_map_new, table_map):
            return "<p>ok</p>"

    class DummyRepo:
        def save_freeze(self, payload):
            self.payload = payload

        def save_reverse(self, payload):
            self.payload = payload

    monkeypatch.setattr(hr, "HtmlMaskService", lambda: DummySvc())
    monkeypatch.setattr(hr, "HtmlRepository", lambda: DummyRepo())

    bp = hr.create_blueprint()
    flask_app.register_blueprint(bp, url_prefix="")
    client = flask_app.test_client()

    resp = client.post("/htmlmask/freeze", json={"html": "<p>x</p>"})
    assert resp.status_code == 400

    resp = client.post(
        "/htmlmask/freeze",
        json={"html": "<p>x</p>", "locale": "id"},
        headers={"X-APIKey": "k1"},
    )
    assert resp.status_code == 200
    assert "report_id" in resp.get_json()

    resp = client.post(
        "/htmlmask/reverse",
        json={"html_skeleton": "<p>[TEXT_01]</p>", "text_map_new": {"[TEXT_01]": "ok"}},
        headers={"X-APIKey": "k1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["html_final"] == "<p>ok</p>"
