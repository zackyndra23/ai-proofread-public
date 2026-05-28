from dataclasses import dataclass

@dataclass
class NerRequest:
  text: str
  tenant: str = ""
  token_spans: list = None  # optional: untuk hindari overlap token masking
