from flask import Blueprint, Flask
import app.app as appmod
from app.core.config import Config
import runpy
import sys
import types
import flask


def _mk_bp(name):
    bp = Blueprint(name, __name__)

    @bp.get("/ping")
    def _ping():
        return "ok"

    return bp


def test_create_app_registers_blueprints_and_headers(monkeypatch):
    monkeypatch.setattr(appmod, "init_db", lambda: None)
    monkeypatch.setattr(appmod, "masking_bp", lambda: _mk_bp("masking"))
    monkeypatch.setattr(appmod, "ner_bp", lambda: _mk_bp("ner"))
    monkeypatch.setattr(appmod, "htmlmask_bp", lambda: _mk_bp("htmlmask"))
    monkeypatch.setattr(appmod, "reformat_bp", lambda: _mk_bp("reformat"))
    monkeypatch.setattr(appmod, "proofread_bp", lambda: _mk_bp("proofread"))
    monkeypatch.setattr(appmod, "meta_bp", lambda: _mk_bp("meta"))
    monkeypatch.setattr(appmod, "result_analyse_bp", lambda: _mk_bp("result_analyse"))

    called = {"swagger": False}

    def _init_swagger(app, cfg):
        called["swagger"] = True

    monkeypatch.setattr(appmod, "init_swagger", _init_swagger)

    app = appmod.create_app()
    client = app.test_client()

    resp = client.get("/v1/ping")
    assert resp.status_code == 200
    assert "X-App-Version" in resp.headers
    assert "X-API-Version" in resp.headers
    assert called["swagger"] is True


def test_attach_rate_limit_blocks(monkeypatch):
    app = Flask(__name__)
    bp = Blueprint("bp", __name__)

    @bp.get("/ping")
    def _ping():
        return "ok"

    monkeypatch.setattr(appmod, "enforce_rps", lambda name, rps, window: ("blocked", 429, {}))

    appmod._attach_rate_limit(bp, "bp", Config())
    app.register_blueprint(bp, url_prefix="/x")

    client = app.test_client()
    resp = client.get("/x/ping")
    assert resp.status_code == 429


def test_create_app_sets_git_sha_header(monkeypatch):
    monkeypatch.setattr(appmod, "init_db", lambda: None)
    monkeypatch.setattr(appmod, "masking_bp", lambda: _mk_bp("masking"))
    monkeypatch.setattr(appmod, "ner_bp", lambda: _mk_bp("ner"))
    monkeypatch.setattr(appmod, "htmlmask_bp", lambda: _mk_bp("htmlmask"))
    monkeypatch.setattr(appmod, "reformat_bp", lambda: _mk_bp("reformat"))
    monkeypatch.setattr(appmod, "proofread_bp", lambda: _mk_bp("proofread"))
    monkeypatch.setattr(appmod, "meta_bp", lambda: _mk_bp("meta"))
    monkeypatch.setattr(appmod, "result_analyse_bp", lambda: _mk_bp("result_analyse"))
    monkeypatch.setattr(appmod, "init_swagger", lambda app, cfg: None)
    monkeypatch.setattr(appmod.Config, "GIT_SHA", "abc123")

    app = appmod.create_app()
    client = app.test_client()
    resp = client.get("/v1/ping")
    assert resp.headers["X-Git-SHA"] == "abc123"


def test_app_main_invokes_run_and_handles_dotenv_failure(monkeypatch):
    def _stub_bp(name):
        bp = Blueprint(name, __name__)
        return bp

    def _mk_routes_module(name):
        mod = types.ModuleType(name)
        mod.create_blueprint = lambda: _stub_bp(name)
        return mod

    # stub dotenv to force load_dotenv failure path
    dotenv_mod = types.ModuleType("dotenv")
    def _boom():
        raise RuntimeError("boom")
    dotenv_mod.load_dotenv = _boom
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_mod)

    # stub route modules
    monkeypatch.setitem(sys.modules, "app.modules.masking.routes", _mk_routes_module("masking"))
    monkeypatch.setitem(sys.modules, "app.modules.ner.routes", _mk_routes_module("ner"))
    monkeypatch.setitem(sys.modules, "app.modules.htmlmask.routes", _mk_routes_module("htmlmask"))
    monkeypatch.setitem(sys.modules, "app.modules.reformat.routes", _mk_routes_module("reformat"))
    monkeypatch.setitem(sys.modules, "app.modules.proofread.routes", _mk_routes_module("proofread"))
    monkeypatch.setitem(sys.modules, "app.modules.meta.routes", _mk_routes_module("meta"))
    monkeypatch.setitem(sys.modules, "app.modules.result_analyse.routes", _mk_routes_module("result_analyse"))

    # stub services.db
    db_mod = types.ModuleType("services.db")
    db_mod.init_db = lambda: None
    monkeypatch.setitem(sys.modules, "services.db", db_mod)

    # avoid swagger init
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("ENABLE_SWAGGER", "0")

    called = {"ran": False}
    def _fake_run(self, *args, **kwargs):
        called["ran"] = True

    monkeypatch.setattr(flask.Flask, "run", _fake_run, raising=True)

    runpy.run_module("app.app", run_name="__main__")
    assert called["ran"] is True
