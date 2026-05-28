import re
from typing import Dict, Tuple, List
from services.masking import (
    mask_with_piiregex, mask_with_phones_lib, mask_with_patterns,
    _find_token_spans, unmask_text
)
from services.utils import locale_to_region

TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")

class MaskingService:
  def run_layers(self, text: str, locale: str):
    layers, order = [], []
    counters: Dict[str, int] = {}

    masked, l1 = mask_with_piiregex(text, counters=counters)
    for lyr in l1: layers.append(lyr); order.append(lyr["type"])

    token_spans = _find_token_spans(masked)

    region = locale_to_region(locale)
    masked, l2 = mask_with_phones_lib(masked, region, counters=counters)
    for lyr in l2: layers.append(lyr); order.append(lyr["type"])

    masked, l3 = mask_with_patterns(masked, counters=counters)
    for lyr in l3: layers.append(lyr); order.append(lyr["type"])

    layered_maps = {}
    for lyr in layers: layered_maps.update(lyr.get("map", {}))

    return masked, layers, layered_maps, order, token_spans

  def unmask(self, text: str, layered_maps: Dict[str, dict]) -> str:
    return unmask_text(text, layered_maps)

  def extract_token_list(self, masked: str) -> list[str]:
    token_list, seen = [], set()
    for m in TOKEN_RE.finditer(masked):
      t = m.group(0)
      if t not in seen:
        seen.add(t); token_list.append(t)
    return token_list
