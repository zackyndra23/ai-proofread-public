import time
from flask import request, jsonify

from services.db import ratelimit_incr

def enforce_rps(bp_name: str, rps: int, window_sec: int):
  key_user = request.headers.get("X-APIKey") or request.remote_addr or "anon"
  key = f"rps:{bp_name}:{key_user}"
  count, expiry = ratelimit_incr(key, window_sec)
  if count > rps:
    retry_after = max(0, int(expiry - time.time()))
    return jsonify({
        "detail": f"AI Proofreading Rate Limit {rps} per {window_sec} second",
        "error": "LLM_RATE_LIMITED",
        "message": "LLM provider rate limit exceeded. Please retry later.",
        "statusCode": 429
    }), 429, {"Retry-After": str(retry_after)}

  return None