from flask import Blueprint, request, jsonify
from app.core.config import Config
from app.core.ratelimit import enforce_rps
from services.utils import require_headers
from .dto import MaskRequest, UnmaskRequest
from .services import MaskingService
from .repositories import MaskingRepository

def create_blueprint():
  bp = Blueprint("masking", __name__)
  cfg = Config()
  svc = MaskingService()
  repo = MaskingRepository()

  @bp.before_request
  def _guard():
    overflow = enforce_rps(bp.name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)
    if overflow: return overflow

  @bp.post("/masking/mask")
  def mask():
    """
    Masking text (PII, phone, patterns)
    ---
    tags:
      - Masking
    consumes:
      - application/json
    produces:
      - application/json
    security:
      - ApiKeyAuth: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [text]
          properties:
            text:
              type: string
              example: "Halo Rizal, no saya 09281819."
            locale:
              type: string
              example: id
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            masked: { type: string }
            layers: { type: array, items: { type: object } }
            layered_maps: { type: object }
            order: { type: array, items: { type: string } }
      400:
        description: Bad request
    """
    ok, msg = require_headers(request)
    if not ok: return jsonify({"error": msg}), 400
    body = request.get_json(silent=True) or {}
    req = MaskRequest(text=(body.get("text") or "").strip(), locale=(body.get("locale") or "id").strip().lower())
    if not req.text: return jsonify({"error": "text is required"}), 400

    masked, layers, layered_maps, order, token_spans = svc.run_layers(req.text, req.locale)
    repo.save_masking({"body": req.text, "message_01": masked, "layers": layers, "order": order, "locale": req.locale})
    return jsonify({"masked": masked, "layers": layers, "layered_maps": layered_maps, "order": order}), 200

  @bp.post("/masking/unmask")
  def unmask():
    ok, msg = require_headers(request)
    if not ok: return jsonify({"error": msg}), 400
    body = request.get_json(silent=True) or {}
    req = UnmaskRequest(text=(body.get("text") or "").strip(), layered_maps=body.get("layered_maps") or {})
    if not req.text: return jsonify({"error": "text is required"}), 400
    out = svc.unmask(req.text, req.layered_maps)
    return jsonify({"unmasked": out}), 200

  return bp
