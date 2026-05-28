from flask import Blueprint, request, jsonify
from services.utils import require_headers
from app.core.config import Config
from app.core.ratelimit import enforce_rps
from app.core.validation import validate_and_scan, is_symbol_only_text, validate_locale_tenant, _error_response, _error_response_with_detail
from .dto import ProofreadRequest, AllowedFormat
from .services import ProofreadService
from .repositories import ProofreadRepo
from app.modules.result_analyse.services import append_row_from_report
from pydantic import ValidationError
from app.core.lang_detect import validate_language_locale
from app.core.text_semantic import validate_semantic_text
from app.core.config import Config

cfg = Config()

ALLOWED_FORMATS: set[AllowedFormat] = {"plain", "html", "markdown"}

def create_blueprint():
  bp = Blueprint("proofread", __name__)
  cfg = Config()
  repo = ProofreadRepo(hooks={"after_final": append_row_from_report})
  svc = ProofreadService(cfg, repo)

  @bp.post("/proofread")
  def proofread():
    """
      Proofread (mask → LLM → unmask → reformat)
    ---
    tags:
      - Proofread
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
          required: [type_of_check, tenant, locale, format, data]
          properties:
            type_of_check:
              type: string
              example: general
            tenant:
              type: string
              example: indonesia
            locale:
              type: string
              example: en
            format:
              type: string
              enum: [plain, html]
              example: plain
            data:
              type: string
              example: "The subject's employment status was contract-based."
            report_id:
              type: string
              example: "94d579ec-11b6-48fb-a999-f0859bf7c09c"
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            report_id:
              type: string
              example: "2b58bcce-720b-4184-9a62-a2ab8e5befd0"
            result:
              type: string
              example: "The subject's employment status was contract-based."
            tenant:
              type: string
              example: indonesia
            type_of_check:
              type: string
              example: general
            version:
              type: object
              properties:
                api:
                  type: string
                  example: v1
                app:
                  type: string
                  example: "0.1.0"
      400:
        description: Bad request
    """
    ok, msg = require_headers(request)
    if not ok:
      return jsonify({"error": msg}), 400
    if not request.is_json:
      return jsonify({"error": "Body must be JSON"}), 400

    b = request.get_json(silent=True) or {}
    # payload = {
    #   "type_of_check": (b.get("type_of_check") or "general").strip(),
    #   "tenant": (b.get("tenant") or "").strip().lower(),
    #   "locale": (b.get("locale") or "id").strip().lower(),
    #   "format": (b.get("format") or "").strip().lower(),
    #   "data": (b.get("data") or "").strip(),
    #   "report_id": (b.get("report_id") or None),
    # }

    payload = {
      "type_of_check": (b.get("type_of_check") or "general").strip(),
      "tenant": (b.get("tenant") or "").strip().lower(),
      "locale": (b.get("locale") or "id").strip().lower(),
      "format": (b.get("format") or "").strip().lower(),
      "data": (b.get("data") or "").strip(),
      "report_id": (b.get("report_id") or None),
    }

    # 💡 hard check locale & tenant BEFORE any deep scanning
    bad = validate_locale_tenant(payload)
    if bad:
        return bad

    # allowed_keys harus sesuai schema DTO (ProofreadRequest)
    ALLOWED_KEYS = {"type_of_check", "tenant", "locale", "format", "data", "report_id"}

    # semantic validation - reject input yang hanya simbol/angka
    if cfg.REJECT_SYMBOL_ONLY:
        bad, reason = is_symbol_only_text(payload["data"], field_name="data")
        if bad:
            return _error_response(
                reason,                    # ini sudah persis "Field 'data' must contain readable text..."
                "INVALID_TEXT_SYMBOLS",
                400
            )

    # feature flags dari Config ===
    enable_html = cfg.DETECT_HTML
    enable_sql  = cfg.DETECT_SQLI

    # allowed_keys harus sesuai schema DTO (ProofreadRequest). Contoh:
    ALLOWED_KEYS = {"type_of_check", "tenant", "locale", "format", "data", "report_id"}

    # feature flags dari Config ===
    enable_html = cfg.DETECT_HTML
    enable_sql  = cfg.DETECT_SQLI

    # # run combined validation + security scan
    # bad_resp = validate_and_scan(payload, ALLOWED_KEYS, reject_on_html=True)
    # if bad_resp:
    #     return bad_resp

    # Jika user minta 'html'/'markdown', kita TIDAK reject HTML mentah;
    # biarkan lalu akan di-sanitize ketika reject_on_html=False.
    wants_markup = payload.get("format") in ("html", "markdown")

    # effective reject rule:
    # - kalau HTML detect dimatikan → jangan reject (skip block)
    # - kalau user memang ingin html/markdown → jangan reject, sanitize saja
    reject_on_html = bool(enable_html and not wants_markup)

    bad_resp = validate_and_scan(
        payload,
        ALLOWED_KEYS,
        reject_on_html=reject_on_html,
        enable_html=enable_html,
        enable_sql=enable_sql,
    )
    if bad_resp:
        return bad_resp

    # === Semantic Text Guard (SLM) ===
    sem_res = validate_semantic_text(payload["locale"], payload["data"])
    if not sem_res.get("passes", False):
        reason = sem_res.get("reason", "")
        chars = sem_res.get("chars", 0)
        words = sem_res.get("words", 0)
        min_chars = sem_res.get("min_chars", cfg.TEXT_SEMANTIC_MIN_CHARS)
        min_words = sem_res.get("min_words", cfg.TEXT_SEMANTIC_MIN_WORDS)

        if reason == "too_short":
            msg = (
                f"Please provide more characters so the text can be proofread. "
                f"The current text has only {chars} characters which is less than "
                f"the minimum {min_chars} characters."
            )
        elif reason == "too_few_words":
            msg = (
                f"Please provide more words so the text can be proofread. "
                f"The current text has only {words} words which is less than "
                f"the minimum {min_words} words."
            )
        elif reason == "not_meaningful":
            msg = (
                f"Please provide a meaningful input so it is valid for proofreading, "
                f"with more than {min_chars} characters and more than {min_words} words."
            )
        else:
            # fallback generic message
            msg = "Input text is not suitable for proofreading."

        # map semantic failure -> your CSV error codes
        if reason == "too_short":
            err = "TEXT_TOO_SHORT"
            status = 422
        elif reason == "too_few_words":
            err = "TEXT_TOO_FEW_WORDS"
            status = 422
        elif reason == "not_meaningful":
            err = "TEXT_NOT_MEANINGFUL"
            status = 422
        else:
            # optional fallback if you want; but for now keep semantic bucket
            err = "TEXT_INVALID_SEMANTIC"
            status = 422

        return _error_response_with_detail(
            msg,
            err,
            status,
            sem_res
        )

    lang_res = validate_language_locale(payload["locale"], payload["data"])

    if not lang_res.get("passes", False):
        return _error_response_with_detail(
            f"Text language '{lang_res.get('detected_lang')}' does not match locale '{payload.get('locale')}'.",
            "LOCALE_LANGUAGE_MISMATCH",
            422,
            lang_res
        )

    try:
      req = ProofreadRequest(**payload)   # ⬅️ validasi keras terjadi di sini
    except ValidationError as e:
      # Pydantic akan jelaskan field yang salah / tidak dikenal / enum invalid
      return jsonify({"error": "validation_error", "detail": e.errors()}), 400

    try:
      rid, result = svc.run(req)
    except ValueError as ve:
      return jsonify({"error": str(ve)}), 400
    except Exception as e:
      return jsonify({"error": "processing_failed", "message": str(e)}), 500

    return jsonify({
      "report_id": rid,
      "result": result,
      "tenant": req.tenant,
      "type_of_check": req.type_of_check,
      "version": {"app": cfg.APP_VERSION, "api": cfg.API_VERSION},
    }), 200

  return bp