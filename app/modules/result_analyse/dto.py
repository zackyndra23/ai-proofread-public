from dataclasses import dataclass
from typing import Any, List

@dataclass
class ResultAnalyzeRow:
    no: int
    report_id: str
    type_of_check: str
    tenant: str
    locale: str
    processed_at: str
    before: str
    report_01: str
    pii_dictionary: str
    llm_prompt: str
    report_02: str
    report_03: str
    final_report: str

    def to_row(self) -> List[Any]:
        return [
            self.no, self.report_id, self.type_of_check, self.tenant, self.locale,
            self.processed_at, self.before, self.report_01, self.pii_dictionary,
            self.llm_prompt, self.report_02, self.report_03, self.final_report,
        ]