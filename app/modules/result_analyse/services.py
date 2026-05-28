from __future__ import annotations
import os, json
from typing import Any, Dict, Optional
from services.gsheets_client import get_worksheet
from .dto import ResultAnalyzeRow

class QAAutomationService:
    @staticmethod
    def is_activated() -> bool:
        result_analyze_on = os.getenv("RESULT_ANALYZE", "INACTIVE").upper() == "ACTIVATE"
        store_gsheets = os.getenv("STORE_GSHEETS", "1").lower() in ("1", "true", "yes")
        return result_analyze_on and store_gsheets

    @staticmethod
    def _safe_json_str(obj: Any) -> str:
        if obj is None: return ""
        if isinstance(obj, str): return obj  # biar “unescaped JSON” tetap apa adanya
        try: return json.dumps(obj, ensure_ascii=False)
        except Exception: return str(obj)

    @staticmethod
    def _pretty_json(obj: Any) -> str:
        """
        Buat tampilan JSON multiline (indent=2) seperti di Mongo.
        - dict/list → pretty langsung
        - string JSON → di-parse lalu pretty
        - selain itu → fallback ke _safe_json_str
        """
        if obj is None:
            return ""
        if isinstance(obj, (dict, list)):
            return json.dumps(obj, ensure_ascii=False, indent=2)
        if isinstance(obj, str):
            try:
                parsed = json.loads(obj)
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception:
                return obj
        return QAAutomationService._safe_json_str(obj)

    @staticmethod
    def _next_no(ws) -> int:
        col_a = ws.col_values(1)  # ['no','1','2',...]
        used = [x for x in col_a[1:] if str(x).strip() != ""]
        return len(used) + 1

    @staticmethod
    def _ensure_wrap_for_pii(ws):
        """
        Pastikan kolom 'pii_dictionary' di-wrap.
        Posisi kolom 'pii_dictionary' = ke-9 (A=1 → I=9), jadi range 'I:I'.
        """
        try:
            ws.format('I:I', {
                'wrapStrategy': 'WRAP',
                'horizontalAlignment': 'LEFT',
                'verticalAlignment': 'TOP'
            })
        except Exception:
            # best-effort; kalau gagal formatting, lanjutkan saja append row
            pass

    def append_row_from_report(
        self,
        *, request_payload: Dict[str, Any], report_id: str,
        created_at2: str, message_01: Any, message_02: Any, llm_prompt: Any,
        layered_maps: Any, message_03: Any, message_final: Any

    ):
        # ← panggil helper via nama class (karena staticmethod) atau via self
        if not QAAutomationService.is_activated():
            return None
        
        ws = get_worksheet()
        QAAutomationService._ensure_wrap_for_pii(ws)

        type_of_check = request_payload.get("type_of_check", "")
        tenant = request_payload.get("tenant", "")
        locale = (request_payload.get("language") or request_payload.get("locale")
                or os.getenv("DEFAULT_LOCALE", "en"))
        before_text = request_payload.get("data", "")

        row = ResultAnalyzeRow(
            no=QAAutomationService._next_no(ws),
            report_id=report_id,
            type_of_check=type_of_check,
            tenant=tenant,
            locale=str(locale),
            processed_at=str(created_at2 or ""),
            before=QAAutomationService._safe_json_str(before_text),
            report_01=QAAutomationService._safe_json_str(message_01),
            # pii_dictionary=_safe_json_str(layered_maps),
            pii_dictionary=QAAutomationService._pretty_json(layered_maps),
            llm_prompt=QAAutomationService._safe_json_str(llm_prompt),
            report_02=QAAutomationService._safe_json_str(message_02),
            report_03=QAAutomationService._safe_json_str(message_03),
            final_report=QAAutomationService._safe_json_str(message_final),
        )
        ws.append_row(row.to_row(), value_input_option="RAW")
        return row.no
    
# ==== WRAPPERS level-modul (agar bisa di-import sebagai fungsi) ====
_svc = QAAutomationService()

def is_activated() -> bool:
    return QAAutomationService.is_activated()

def append_row_from_report(
    *, request_payload: Dict[str, Any], report_id: str,
    created_at2: str, message_01: Any, message_02: Any, llm_prompt: Any,
    layered_maps: Any, message_03: Any, message_final: Any
) -> Optional[int]:
    return _svc.append_row_from_report(
        request_payload=request_payload,
        report_id=report_id,
        created_at2=created_at2,
        message_01=message_01,
        message_02=message_02,
        llm_prompt=llm_prompt,
        layered_maps=layered_maps,
        message_03=message_03,
        message_final=message_final,
    )
