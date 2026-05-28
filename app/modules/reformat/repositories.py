import services.db as db
from services.db import now_wib, wib_iso, wib_human

class ReformatRepository:
  def save_final(self, payload: dict):
    noww = now_wib()
    db.col_final.insert_one({**payload, "created_at": wib_iso(noww), "created_at2": wib_human(noww)})
