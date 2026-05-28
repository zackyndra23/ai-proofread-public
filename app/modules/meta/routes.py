from flask import Blueprint, jsonify
from app.core.config import Config
from app.core.version import version_info

def create_blueprint():
  bp = Blueprint("meta", __name__)

  @bp.get("/meta/version")
  def get_version():
    return jsonify(version_info()), 200

  @bp.get("/meta/healthz")
  def healthz():
    return jsonify({"status": "ok"}), 200

  return bp
