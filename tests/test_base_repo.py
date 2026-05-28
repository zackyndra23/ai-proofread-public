from app.repositories.base import BaseRepo
import services.db as db


def test_base_repo_helpers(monkeypatch):
    monkeypatch.setattr(db, "safe_insert", lambda col, doc: True)
    monkeypatch.setattr(db, "wib_iso", lambda: "ISO")
    monkeypatch.setattr(db, "wib_human", lambda: "HUM")

    repo = BaseRepo()
    assert repo._ins("col", {"a": 1}) is True
    assert repo._now_iso() == "ISO"
    assert repo._now_human() == "HUM"
