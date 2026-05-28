import uuid
from flask import Blueprint, request, jsonify
from services.utils import require_headers
from app.core.config import Config
from app.core.ratelimit import enforce_rps
from .dto import FreezeRequest, ReverseRequest
from .services import HtmlMaskService
from .repositories import HtmlRepository

def create_blueprint():
  bp = Blueprint("htmlmask", __name__)
  cfg = Config()
  svc = HtmlMaskService()
  repo = HtmlRepository()

  @bp.before_request
  def _guard():
    overflow = enforce_rps(bp.name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)
    if overflow: return overflow

  @bp.post("/htmlmask/freeze")
  def freeze():
    ok, msg = require_headers(request)
    if not ok: return jsonify({"error": msg}), 400
    body = request.get_json(silent=True) or {}
    req = FreezeRequest(
      html=(body.get("html") or ""),
      report_id=(body.get("report_id") or None),
      toc_type=(body.get("toc_type") or "general"),
      tenant=(body.get("tenant") or ""),
      locale=(body.get("locale") or "id").lower(),
    )
    if not req.html.strip(): return jsonify({"error": "html is required"}), 400
    fr = svc.freeze(req.html)
    rid = req.report_id or str(uuid.uuid4())
    repo.save_freeze({"report_id": rid, "report_id_html": rid, "toc_type": req.toc_type,
                      "tenant": req.tenant, "locale": req.locale, "html_tag": True, "body_html": req.html, **fr})
    return jsonify({"report_id": rid, **fr}), 200

  @bp.post("/htmlmask/reverse")
  def reverse():
    ok, msg = require_headers(request)
    if not ok: return jsonify({"error": msg}), 400
    body = request.get_json(silent=True) or {}
    req = ReverseRequest(
      html_skeleton=body.get("html_skeleton") or "",
      text_map_new=body.get("text_map_new") or {},
      table_map=body.get("table_map") or {},
      report_id=(body.get("report_id") or None),
      toc_type=(body.get("toc_type") or "general"),
      tenant=(body.get("tenant") or ""),
      locale=(body.get("locale") or "id").lower(),
    )
    if not req.html_skeleton.strip(): return jsonify({"error": "html_skeleton is required"}), 400
    final_html = svc.reverse(req.html_skeleton, req.text_map_new, req.table_map)
    rid = req.report_id or str(uuid.uuid4())
    repo.save_reverse({"report_id": rid, "report_id_html": rid, "toc_type": req.toc_type,
                        "tenant": req.tenant, "locale": req.locale, "html_final": final_html})
    return jsonify({"report_id": rid, "html_final": final_html}), 200

  return bp
