import os, re
from typing import Dict
from services.ner import NerRunner, mask_by_ner
from app.core.config import Config

ALLOWED_LABELS = {
  "PER": "PER", "PERSON": "PER",
  "ORG": "ORG", "ORGANIZATION": "ORG",
  "LOC": "LOC", "GPE": "LOC", "LOCATION": "LOC",
}

def _wb_ok(t: str, st: int, en: int) -> bool:
  before = t[st-1] if st > 0 else " "
  after  = t[en]   if en < len(t) else " "
  return not before.isalnum() and not after.isalnum()

def _filter_spans(text: str, spans: list, token_spans: list):
  out = []
  token_spans = token_spans or []
  for s in spans:
    st, en = s.get("start", -1), s.get("end", -1)
    if st < 0 or en <= st: continue
    # hindari overlap dgn token
    if any(not (en <= ts or te <= st) for (ts, te) in token_spans): continue
    lbl = ALLOWED_LABELS.get(s.get("label", "").upper())
    if not lbl: continue
    seg = text[st:en]
    if len(seg) < 4: continue
    if not re.search(r"[A-Za-z]", seg): continue
    if not _wb_ok(text, st, en): continue
    out.append({"label": lbl, "start": st, "end": en})
  return out

class NerService:
  def __init__(self, cfg: Config):
    self.runner = NerRunner(base_dir=cfg.NER_BASE_DIR)
    self.cfg = cfg

  def mask_by_models(self, masked_text: str, tenant: str, token_spans: list):
    pairs = []
    text = masked_text

    if hasattr(self.runner, "base_en"):
      spans_raw_en = self.runner.infer_spans_for_model(text, self.runner.base_en)
      spans_en = _filter_spans(text, spans_raw_en, token_spans)
      text, l_en = mask_by_ner(text, spans_en)
      pairs += [{"type": n, "map": m} for (n, m) in l_en]

    model = self.cfg.TENANT2MODEL.get(tenant)
    if model:
      model_path = os.path.join(self.cfg.NER_BASE_DIR, model)
      spans_raw_tn = self.runner.infer_spans_for_model(text, model_path)
      spans_tn = _filter_spans(text, spans_raw_tn, token_spans)
      text, l_tn = mask_by_ner(text, spans_tn)
      pairs += [{"type": n, "map": m} for (n, m) in l_tn]

    # merge maps
    maps = {}
    for p in pairs: maps.update(p.get("map", {}))
    return text, pairs, maps
