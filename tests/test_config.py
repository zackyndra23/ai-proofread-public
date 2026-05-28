from app.core.config import Config


def test_config_on():
    assert Config._on("on") is True
    assert Config._on("off") is False
    assert Config._on(None, default="on") is True
