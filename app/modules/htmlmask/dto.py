from dataclasses import dataclass

@dataclass
class FreezeRequest:
  html: str
  report_id: str | None = None
  toc_type: str = "general"
  tenant: str = ""
  locale: str = "id"

@dataclass
class ReverseRequest:
  html_skeleton: str
  text_map_new: dict
  table_map: dict
  report_id: str | None = None
  toc_type: str = "general"
  tenant: str = ""
  locale: str = "id"
