from flask import Blueprint, request, jsonify
from services.utils import require_headers
from app.core.config import Config
from app.core.ratelimit import enforce_rps
from .dto import ReformatRequest
from .services import ReformatService
from .repositories import ReformatRepository

def create_blueprint():
  bp = Blueprint("reformat", __name__)
  cfg = Config()
  svc = ReformatService()
  repo = ReformatRepository()

  @bp.before_request
  def _guard():
    overflow = enforce_rps(bp.name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)
    if overflow: return overflow

  @bp.post("/reformat")
  def reformat():
    ok, msg = require_headers(request)
    if not ok: return jsonify({"error": msg}), 400
    body = request.get_json(silent=True) or {}
    req = ReformatRequest(text=(body.get("text") or "").strip(), locale=(body.get("locale") or "id").lower())
    if not req.text: return jsonify({"error": "text is required"}), 400
    final_message, meta = svc.run(req.text, req.locale)
    repo.save_final({"message_final": final_message, "locale": req.locale, "src": req.text})
    return jsonify({"result": final_message, "meta": meta}), 200

  return bp