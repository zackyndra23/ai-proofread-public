from __future__ import annotations
import os, json, gspread
from google.oauth2.service_account import Credentials

def get_worksheet(sheet_id: str | None = None, tab_name: str | None = None):
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    ]

    # 1) Coba pakai JSON di env
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT")
    if sa_json:
        try:
            info = json.loads(sa_json)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT bukan JSON yang valid: {e}")

        creds = Credentials.from_service_account_info(info, scopes=scope)

    else:
        # 2) Fallback: pakai file path seperti sebelumnya
        sa_path = os.getenv("GOOGLE_SA_JSON_PATH")
        if not sa_path or not os.path.exists(sa_path):
            raise RuntimeError(
                "Credential Google Sheets tidak ditemukan. "
                "Set GOOGLE_SERVICE_ACCOUNT atau GOOGLE_SA_JSON_PATH."
            )

        creds = Credentials.from_service_account_file(sa_path, scopes=scope)

    client = gspread.authorize(creds)

    sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID belum di-set.")

    sh = client.open_by_key(sheet_id)
    tab_name = tab_name or os.getenv("RESULT_ANALYZE_SHEET_TAB", "Process_Result_Analysis")
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=20)
        ws.update("A1:M1", [[
            "no","report_id","type","tenant","locale","processed_at",
            "before","report_01","pii_dictionary","llm_prompt",
            "report_02","report_03","final_report"
        ]])
    return ws