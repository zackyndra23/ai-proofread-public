import json
from typing import Any, Dict, Optional
from services.htmltags import freeze_html, reverse_html

def as_json_dict_if_possible(s: str) -> Optional[Dict[str, Any]]:
  try:
    obj = json.loads(s)
    if isinstance(obj, dict): return obj
  except Exception:
    pass
  return None

class HtmlMaskService:
  def freeze(self, raw_html: str):
    return freeze_html(raw_html)

  def reverse(self, skeleton: str, text_map_new: dict, table_map: dict):
    return reverse_html(skeleton, text_map_new, table_map)
