from dataclasses import dataclass

@dataclass
class ReformatRequest:
  text: str
  locale: str = "id"
