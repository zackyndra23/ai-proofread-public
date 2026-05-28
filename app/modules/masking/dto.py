from dataclasses import dataclass

@dataclass
class MaskRequest:
  text: str
  locale: str = "id"

@dataclass
class UnmaskRequest:
  text: str
  layered_maps: dict
