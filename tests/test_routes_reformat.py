from app.modules.reformat import routes as rr


def test_reformat_route(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    monkeypatch.setattr(rr, "enforce_rps", lambda *a, **k: None)

    class DummySvc:
        def run(self, text, locale):
            return "out", {"changed": 1}

    class DummyRepo:
        def save_final(self, payload):
            self.payload = payload

    monkeypatch.setattr(rr, "ReformatService", lambda: DummySvc())
    monkeypatch.setattr(rr, "ReformatRepository", lambda: DummyRepo())

    bp = rr.create_blueprint()
    flask_app.register_blueprint(bp, url_prefix="")
    client = flask_app.test_client()

    resp = client.post("/reformat", json={"text": "hi", "locale": "id"})
    assert resp.status_code == 400

    resp = client.post(
        "/reformat",
        json={"text": "hi", "locale": "id"},
        headers={"X-APIKey": "k1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["result"] == "out"
