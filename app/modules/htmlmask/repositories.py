import services.db as db
from services.db import now_wib, wib_iso, wib_human

class HtmlRepository:
  def save_freeze(self, payload: dict):
    noww = now_wib()
    db.col_html_freeze.insert_one({**payload, "created_at": wib_iso(noww), "created_at2": wib_human(noww)})

  def save_reverse(self, payload: dict):
    noww = now_wib()
    db.col_html_reverse.insert_one({**payload, "created_at": wib_iso(noww), "created_at2": wib_human(noww)})
