from __future__ import annotations
from typing import Optional, Tuple, Any
from services.db import get_mongo  # asumsi sudah ada helper ini di proyekmu

def get_summary_by_report_id(report_id: str) -> Optional[dict]:
    """
    Ambil 1 dokumen summary_output terbaru berdasarkan report_id.
    Harap pipeline kamu menyimpan report_id di setiap stage.
    """
    db = get_mongo()
    col = db.get_collection("summary_output")
    doc = col.find_one({"report_id": report_id}, sort=[("created_at2", -1)])
    return doc

def get_unmask_by_report_id(report_id: str) -> Optional[dict]:
    """
    Ambil 1 dokumen unmask_output terbaru berdasarkan report_id.
    """
    db = get_mongo()
    col = db.get_collection("unmask_output")
    doc = col.find_one({"report_id": report_id}, sort=[("created_at2", -1)])
    return doc