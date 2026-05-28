from app.modules.meta.routes import create_blueprint


def test_meta_routes(flask_app):
    bp = create_blueprint()
    flask_app.register_blueprint(bp, url_prefix="")
    client = flask_app.test_client()

    resp = client.get("/meta/healthz")
    assert resp.status_code == 200

    resp = client.get("/meta/version")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "app_version" in data
