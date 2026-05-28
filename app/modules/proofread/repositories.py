from typing import Dict, Any, Optional, Callable
from bson import ObjectId

from app.core.config import Config
from app.repositories.base import BaseRepo

# Whitelist 9 field untuk dataset masking-model improvement.
# Lihat: docs/superpowers/specs/2026-04-29-masking-results-feature-design.md
_MASKING_RESULTS_FIELDS = (
  "_id", "report_id", "toc_type", "tenant", "locale",
  "message_01", "layers", "created_at", "created_at2",
)

class ProofreadRepo(BaseRepo):
  def __init__(self, *args, hooks: Optional[Dict[str, Callable]] = None, **kwargs):
    super().__init__(*args, **kwargs)
    self._hooks = hooks or {}
    
  def save_html_freeze(self, rid_html: str, meta: Dict[str, Any], raw_html: str, fr: dict) -> None:
    now_iso, now_hum = self._now_iso(), self._now_human()
    doc = {
      "report_id": meta["report_id"],
      "report_id_html": rid_html,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "html_tag": True,
      "body_html": raw_html,
      **fr,
      "created_at": now_iso,
      "created_at2": now_hum,
    }
    self._ins(self.db.col_html_freeze, doc)

  def save_masking(self, rid: str, meta: Dict[str, Any], body: str,
                    masked: str, layers: list, order: list) -> None:
    now_iso, now_hum = self._now_iso(), self._now_human()
    # Pre-generate _id supaya bisa di-reuse di mirror collection (trace 1:1)
    doc = {
      "_id": ObjectId(),
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": masked,
      "layers": layers,
      "order": order,
      "created_at": now_iso,
      "created_at2": now_hum,
    }
    self._ins(self.db.col_masking, doc)

    # Mirror subset whitelist ke collection dataset improvement.
    # Failure isolation otomatis lewat safe_insert_force (return bool, tidak raise).
    if Config.MASKING_RESULTS_FEATURE:
      mirror = {k: doc.get(k) for k in _MASKING_RESULTS_FIELDS}
      missing = [k for k in _MASKING_RESULTS_FIELDS if mirror.get(k) is None]
      if missing:
        print(f"⚠️  masking_results: missing fields {missing} for report_id={rid}")
      # _ins_force: bypass STORE_DB — gate independen via MASKING_RESULTS_FEATURE (pattern sama save_generative)
      self._ins_force(self.db.col_masking_results, mirror)

    self.db.upsert_summary(rid, {
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": masked,
    })

  def save_generative(self, rid: str, meta: Dict[str, Any], body: str,
                      masked: str, message_02: str, prompt: str,
                      llm_meta: Optional[dict] = None) -> None:
    now_iso, now_hum = self._now_iso(), self._now_human()
    doc = {
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": masked,
      "message_02": message_02,
      "llm_prompt": prompt or "",
      "llm_meta": llm_meta or {},
      "created_at": now_iso,
      "created_at2": now_hum,
    }
    self._ins_force(self.db.col_generative, doc)
    self.db.upsert_summary(rid, {
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": masked,
      "message_02": message_02,
      "llm_prompt": prompt or "",
    })

  def save_unmask(self, rid: str, meta: Dict[str, Any], body: str,
                  message_01: str, message_02: str, message_03: str,
                  layered_maps: Dict[str, str]) -> None:
    now_iso, now_hum = self._now_iso(), self._now_human()
    doc = {
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": message_01,
      "message_02": message_02,
      "message_03": message_03,
      "layered_maps": layered_maps,
      "created_at": now_iso,
      "created_at2": now_hum,
    }
    self._ins(self.db.col_unmask, doc)
    self.db.upsert_summary(rid, {
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": message_01,
      "message_02": message_02,
      "message_03": message_03,
    })

  def save_final(self, rid: str, meta: Dict[str, Any], body: str,
                  message_01: str, message_02: str, message_03: str,
                  message_final: str) -> None:
    now_iso, now_hum = self._now_iso(), self._now_human()
    doc = {
      "report_id": rid,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "body": body,
      "message_01": message_01,
      "message_02": message_02,
      "message_03": message_03,
      "message_final": message_final,
      "created_at": now_iso,
      "created_at2": now_hum,
    }
    self._ins(self.db.col_final, doc)

    # === Hook publish (opsional) ===
    cb = self._hooks.get("after_final")
    if cb:
      try:
        cb(
          request_payload=meta.get("_request_payload", {}),
          report_id=rid,
          created_at2=now_hum,
          message_01=message_01,
          message_02=message_02,
          llm_prompt=meta.get("llm_prompt", ""),
          layered_maps=meta.get("layered_maps", {}),
          message_03=message_03,
          message_final=message_final,
        )
      except Exception as e:
        print(f"[result_analyse hook] {e}")

  def save_html_reverse(self, rid_html: str, meta: Dict[str, Any], html_final: str) -> None:
    now_iso, now_hum = self._now_iso(), self._now_human()
    doc = {
      "report_id": meta["report_id"],
      "report_id_html": rid_html,
      "toc_type": meta["toc_type"],
      "tenant": meta["tenant"],
      "locale": meta["locale"],
      "html_final": html_final,
      "created_at": now_iso,
      "created_at2": now_hum,
    }
    self._ins(self.db.col_html_reverse, doc)
