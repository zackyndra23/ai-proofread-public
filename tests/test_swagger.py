from flask import Flask
from app.core import swagger


class DummyCfg:
    APP_VERSION = "1.2.3"


def test_init_swagger(monkeypatch):
    called = {}

    def dummy_swagger(app, template=None, config=None):
        called["template"] = template
        called["config"] = config

    monkeypatch.setattr(swagger, "Swagger", dummy_swagger)

    app = Flask(__name__)
    swagger.init_swagger(app, DummyCfg())

    assert called["template"]["info"]["version"] == "1.2.3"
    assert called["config"]["swagger_ui"] is True
