from flask import Blueprint, request, jsonify
from services.utils import require_headers
from app.core.config import Config
from app.core.ratelimit import enforce_rps
from .dto import NerRequest
from .services import NerService

def create_blueprint():
  bp = Blueprint("ner", __name__)
  cfg = Config()
  svc = NerService(cfg)

  @bp.before_request
  def _guard():
    overflow = enforce_rps(bp.name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)
    if overflow: return overflow

  @bp.post("/ner/mask")
  def ner_mask():
    ok, msg = require_headers(request)
    if not ok: return jsonify({"error": msg}), 400
    body = request.get_json(silent=True) or {}
    req = NerRequest(text=(body.get("text") or "").strip(),
                      tenant=(body.get("tenant") or "").strip().lower(),
                      token_spans=body.get("token_spans") or [])
    if not req.text: return jsonify({"error": "text is required"}), 400
    out_text, pairs, maps = svc.mask_by_models(req.text, req.tenant, req.token_spans)
    return jsonify({"text": out_text, "pairs": pairs, "maps": maps}), 200

  return bp
