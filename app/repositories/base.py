# app/repositories/base.py
import services.db as db

class BaseRepo:
  def __init__(self):
    self.db = db  # akses: self.db.col_generative, self.db.safe_insert, dll.

  def _ins(self, col, doc) -> bool:
    # helper insert aman dengan log
    ok = self.db.safe_insert(col, doc)
    return ok

  def _ins_force(self, col, doc) -> bool:
    # insert paksa untuk audit (abaikan STORE_DB)
    ok = self.db.safe_insert_force(col, doc)
    return ok

  def _now_iso(self) -> str:
    return self.db.wib_iso()

  def _now_human(self) -> str:
    return self.db.wib_human()
