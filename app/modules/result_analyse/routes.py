from flask import Blueprint, request, jsonify
from .services import QAAutomationService
from app.core.config import Config
from app.core.ratelimit import enforce_rps

def create_blueprint():
    bp = Blueprint("result_analyse", __name__, url_prefix="/v1/result-analyse")
    cfg = Config()
    svc = QAAutomationService()

    @bp.get("/health")
    def health():
        return jsonify({"module": "result_analyse", "activated": svc.is_activated()})
    
    @bp.before_request
    def _guard():
        overflow = enforce_rps(bp.name, cfg.RATE_LIMIT_RPS, cfg.RATE_LIMIT_WINDOW)
        if overflow:
            return overflow

    @bp.post("/append")
    def append():
        """
        Ops-only: manual append ke Google Sheet tanpa query DB.
        Body harus berisi paket lengkap yang biasanya dikirim hook repo.
        """
        if not request.is_json:
            return jsonify({"error": "Body must be JSON"}), 400
        b = request.get_json(silent=True) or {}

        required = [
            "request_payload", "report_id", "created_at2",
            "message_01", "message_02", "llm_prompt",
            "layered_maps", "message_03", "message_final"
        ]
        missing = [k for k in required if k not in b]
        if missing:
            return jsonify({"error": "Missing fields", "fields": missing}), 400

        try:
            no_row = svc.append_row_from_report(
                request_payload=b["request_payload"],
                report_id=b["report_id"],
                created_at2=b["created_at2"],
                message_01=b["message_01"],
                message_02=b["message_02"],
                llm_prompt=b["llm_prompt"],
                layered_maps=b["layered_maps"],
                message_03=b["message_03"],
                message_final=b["message_final"],
            )
        except Exception as e:
            return jsonify({"error": "append_failed", "message": str(e)}), 500

        return jsonify({"status": "ok", "appended_no": no_row}), 200
    
    return bp