# app/core/swagger.py
from flasgger import Swagger

def init_swagger(app, cfg):
  template = {
    "swagger": "2.0",
    "info": {
      "title": "AI Proofreading API",
      "description": "Swagger UI untuk dev",
      "version": cfg.APP_VERSION or "0.1.0",
    },
    "basePath": "/",   # blueprint sudah punya prefix (/v1)
    "schemes": ["http", "https"],
    "securityDefinitions": {
      "ApiKeyAuth": {
        "type": "apiKey",
        "name": "X-APIKey",
        "in": "header"
      }
    },
  }
  config = {
    "headers": [],
    "specs": [
      {
        "endpoint": "v1_spec",
        "route": "/v1/openapi.json",    # URL JSON spec
        "rule_filter": lambda rule: True,   # ambil semua route
        "model_filter": lambda tag: True,
      }
    ],
    "static_url_path": "/swagger_static",
    "swagger_ui": True,
    "specs_route": "/v1/docs/",           # URL Swagger UI
  }
  Swagger(app, template=template, config=config)
