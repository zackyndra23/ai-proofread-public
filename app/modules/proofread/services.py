import uuid
from typing import Tuple, Dict, Any

from app.core.config import Config
from app.core.token_utils import integrate_ner  # ← util anti double-masking dipindah ke core
from app.modules.masking.services import MaskingService
from app.modules.ner.services import NerService
from app.modules.htmlmask.services import HtmlMaskService, as_json_dict_if_possible
from app.modules.reformat.services import ReformatService
from services.llm import call_claude, tokens_preserved
from .repositories import ProofreadRepo
from .dto import ProofreadRequest

from app.modules.result_analyse.services import append_row_from_report
from services.subjectfmt import apply_subjectfmt

class ProofreadService:
  def __init__(self, cfg: Config, repo: ProofreadRepo):
    self.cfg = cfg
    self.repo = repo
    self.masking = MaskingService()
    self.ner = NerService(cfg)
    self.html = HtmlMaskService()
    self.reformat = ReformatService()

  def run(self, req: ProofreadRequest) -> Tuple[str, Any]:
    rid = req.report_id or str(uuid.uuid4())
    meta: Dict[str, Any] = {
      "report_id": rid,
      "toc_type": req.type_of_check,
      "tenant": req.tenant,
      "locale": req.locale,
      # 1) Bawa request payload ke hook (language: fallback dari locale)
      "_request_payload": {
        "type_of_check": req.type_of_check,
        "tenant": req.tenant,
        "language": req.locale,    # ganti ke body["language"] kalau route-mu sudah menampung 'language'
        "locale": req.locale,
        "data": req.data
      }
    }

    # --- HTML freeze -----------------------------------------------------
    fr = None
    text_processing = req.data
    if req.format == "html":
        fr = self.html.freeze(req.data)
        # simpan artefak html untuk audit
        self.repo.save_html_freeze(rid_html=rid, meta=meta, raw_html=req.data, fr=fr)
        text_processing = (fr.get("text_format") or "").strip()
        if not text_processing:
          # biar route balas 400, bukan 500
          raise ValueError("freeze_html produced empty text_format")

    # --- SUBJECTFMT (pre-masking, ID only) -------------------------------
    # Pronoun continuity harus sebelum masking agar masih lihat nama asli.

    subj_meta = {}
    try:
        text_processing, subj_meta = apply_subjectfmt(
            text_processing,
            req.locale,
            req.type_of_check,
            max_follow_sentences=None
        )
    except Exception as e:
        subj_meta = {
            "applied": False,
            "error": str(e)
        }

    meta["subjectfmt"] = subj_meta

    # --- Masking (regex/deterministic) ----------------------------------
    masked, layers, layered_maps, order, token_spans = self.masking.run_layers(
      text_processing, req.locale
    )

    # --- NER layer (ANTI double-masking) --------------------------------
    # Jalankan NER di TEKS ORIGINAL (text_processing), blokir area yang sudah dimasking
    # dengan token_spans. Ambil pair & map-nya saja (abaikan string preview dari NER).
    _masked_preview, ner_pairs, ner_maps_raw = self.ner.mask_by_models(
      text_processing, req.tenant, token_spans
    )

    # Gabungkan hasil NER ke string masked "di luar token" + reindex token agar tidak bentrok
    masked2, renamed_pairs, reindexed_maps = integrate_ner(
      masked=masked,
      existing_maps=layered_maps,
      ner_pairs=ner_pairs,
      ner_maps_raw=ner_maps_raw
    )

    if renamed_pairs:
      layers.extend(renamed_pairs)
      layered_maps.update(reindexed_maps)
    else:
      masked2 = masked  # tidak ada NER baru

    # Audit masking output
    self.repo.save_masking(rid, meta, text_processing, masked2, layers, order)

    # --- LLM -------------------------------------------------------------
    message_02 = masked2
    if self.cfg.AUTO_CHAIN_LLM:
      token_list = self.masking.extract_token_list(masked2)
      try:
        out, meta_llm = call_claude(
          text=masked2,
          toc_type=req.type_of_check or "general",
          fmt_txt=req.format,   # penting: ikutkan format ke prompt selector
          locale=req.locale,
          tenant=req.tenant,
          token_list=token_list,
        )
      except Exception as e:
        # fail soft: lanjut pakai masked2
        out, meta_llm = masked2, {"error": str(e), "prompt": ""}

      if tokens_preserved(masked2, out, token_list):
        message_02 = out

      # simpan jejak generative, walau hasil tidak berubah
      self.repo.save_generative(
        rid, meta, text_processing, masked2, message_02,
        prompt=meta_llm.get("prompt", ""),
        llm_meta={k: v for k, v in meta_llm.items() if k != "prompt"}
      )

      # 2a) Simpan llm_prompt ke meta agar ikut dikirim oleh hook di repo.save_final()
      meta["llm_prompt"] = meta_llm.get("prompt", "") if self.cfg.AUTO_CHAIN_LLM else ""

    # --- UNMASK ----------------------------------------------------------
    message_03 = message_02
    if self.cfg.AUTO_CHAIN_UNMASK and message_02:
      message_03 = self.masking.unmask(message_02, layered_maps)
      self.repo.save_unmask(
        rid, meta, text_processing, masked2, message_02, message_03, layered_maps
      )

    # 2b) Simpan layered_maps ke meta agar ikut dikirim oleh hook di repo.save_final()
    meta["layered_maps"] = layered_maps

    # --- REFORMAT --------------------------------------------------------
    final_message = message_03
    if self.cfg.AUTO_CHAIN_REFORMAT and message_03:
      final_message, _ = self.reformat.run(message_03, req.locale)

    # 3) SELALU panggil save_final() supaya hook after_final pasti terpanggil
    self.repo.save_final(
        rid, meta, text_processing, masked2, message_02, message_03, final_message or ""
    )

    # --- HTML reverse ----------------------------------------------------
    if req.format == "html" and fr:
      if isinstance(final_message, dict):
        text_map_new = {str(k).strip(): str(v) for k, v in final_message.items()}
      else:
        parsed = as_json_dict_if_possible(final_message) if isinstance(final_message, str) else None
        if isinstance(parsed, dict) and any(str(k).startswith("[TEXT_") for k in parsed.keys()):
          text_map_new = {str(k).strip(): str(v) for k, v in parsed.items()}
        else:
          keys = list(fr.get("text_map", {}).keys())
          text_map_new = {
            k: (final_message if isinstance(final_message, str) else str(final_message))
            for k in keys
          }

      final_html = self.html.reverse(fr["html_skeleton"], text_map_new, fr.get("table_map", {}))
      self.repo.save_html_reverse(rid_html=rid, meta=meta, html_final=final_html)
      return rid, final_html

    return rid, final_message