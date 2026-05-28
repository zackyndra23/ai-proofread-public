from pydantic import BaseModel, Field
from typing import Literal, Optional

AllowedFormat = Literal["plain", "html", "markdown"]
# AllowedLocale = Literal["en", "id", "th", "ms"]
AllowedLocale = Literal["en", "id", "ms"]
AllowedTenant = Literal["indonesia", "thailand", "malaysia"]

class ProofreadRequest(BaseModel):
    type_of_check: str = Field(default="general", min_length=1)
    tenant: AllowedTenant
    locale: AllowedLocale
    format: AllowedFormat
    data: str = Field(..., min_length=1)
    report_id: Optional[str] = None

    class Config:
        extra = "forbid"   # Tolak field asing