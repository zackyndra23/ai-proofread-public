import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
  pass

from flask import Flask
from app.core.config import Config
from app.core.swagger import init_swagger
from app.core.ratelimit import enforce_rps
from app.modules.masking.routes import create_blueprint as masking_bp
from app.modules.ner.routes import create_blueprint as ner_bp
from app.modules.htmlmask.routes import create_blueprint as htmlmask_bp
from app.modules.reformat.routes import create_blueprint as reformat_bp
from app.modules.proofread.routes import create_blueprint as proofread_bp
from app.modules.meta.routes import create_blueprint as meta_bp
from app.modules.result_analyse.routes import create_blueprint as result_analyse_bp
from services.db import init_db

def _attach_rate_limit(bp, name: str, cfg: Config):
    @bp.before_request
    def _rl():
        hit = enforce_rps(name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)
        if hit is not None:
            return hit  # return Response 429 dari helper

def create_app():
  # NOSONAR - API-only service (header-based auth, no session cookies), CSRF not applicable
  app = Flask(__name__)

  init_db()

  cfg = Config()
  prefix = f"/{cfg.API_VERSION}" if cfg.API_PREFIX in ("", "/") else f"{cfg.API_PREFIX}/{cfg.API_VERSION}"

  masking = masking_bp();        _attach_rate_limit(masking, "masking", cfg)
  ner = ner_bp();                _attach_rate_limit(ner, "ner", cfg)
  htmlmask = htmlmask_bp();      _attach_rate_limit(htmlmask, "htmlmask", cfg)
  reformat = reformat_bp();      _attach_rate_limit(reformat, "reformat", cfg)
  proofread = proofread_bp();    _attach_rate_limit(proofread, "proofread", cfg)
  meta = meta_bp();              _attach_rate_limit(meta, "meta", cfg)
  result_analyse = result_analyse_bp(); _attach_rate_limit(result_analyse, "result_analyse", cfg)

  app.register_blueprint(masking,        url_prefix=prefix)
  app.register_blueprint(ner,            url_prefix=prefix)
  app.register_blueprint(htmlmask,       url_prefix=prefix)
  app.register_blueprint(reformat,       url_prefix=prefix)
  app.register_blueprint(proofread,      url_prefix=prefix)
  app.register_blueprint(meta,           url_prefix=prefix)
  app.register_blueprint(result_analyse, url_prefix=prefix)

  if os.getenv("FLASK_DEBUG", "1") == "1" or os.getenv("ENABLE_SWAGGER", "1") == "1":
    init_swagger(app, cfg)

  @app.after_request
  def add_version_headers(resp):
    resp.headers["X-App-Version"] = cfg.APP_VERSION
    resp.headers["X-API-Version"]  = cfg.API_VERSION
    if cfg.GIT_SHA:
      resp.headers["X-Git-SHA"] = cfg.GIT_SHA
    return resp

  return app

if __name__ == "__main__":
  app = create_app()
  app.run(
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "5000")),
    debug=os.getenv("FLASK_DEBUG", "1") == "1"
  )
