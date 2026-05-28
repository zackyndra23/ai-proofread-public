from app.modules.masking import routes as mr


def test_masking_routes(flask_app, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1")
    monkeypatch.setattr(mr, "enforce_rps", lambda *a, **k: None)

    class DummySvc:
        def run_layers(self, text, locale):
            return "masked", [{"type": "pii_EMAIL", "map": {}}], {"[X_0]": "y"}, ["pii_EMAIL"], []

        def unmask(self, text, layered_maps):
            return "unmasked"

    class DummyRepo:
        def save_masking(self, payload):
            self.payload = payload

    monkeypatch.setattr(mr, "MaskingService", lambda: DummySvc())
    monkeypatch.setattr(mr, "MaskingRepository", lambda: DummyRepo())

    bp = mr.create_blueprint()
    flask_app.register_blueprint(bp, url_prefix="")
    client = flask_app.test_client()

    resp = client.post("/masking/mask", json={"text": "hi", "locale": "id"})
    assert resp.status_code == 400

    resp = client.post(
        "/masking/mask",
        json={"text": "hi", "locale": "id"},
        headers={"X-APIKey": "k1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["masked"] == "masked"

    resp = client.post(
        "/masking/unmask",
        json={"text": "[X_0]", "layered_maps": {"[X_0]": "y"}},
        headers={"X-APIKey": "k1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["unmasked"] == "unmasked"
