import services.db as db
from app.core.config import Config
from app.modules.htmlmask.repositories import HtmlRepository
from app.modules.masking.repositories import MaskingRepository
from app.modules.proofread.repositories import ProofreadRepo
from app.modules.reformat.repositories import ReformatRepository


class DummyCol:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(doc)


def test_html_repository_inserts(monkeypatch):
    col = DummyCol()
    monkeypatch.setattr(db, "col_html_freeze", col)
    monkeypatch.setattr(db, "col_html_reverse", col)

    repo = HtmlRepository()
    repo.save_freeze({"report_id": "r1"})
    repo.save_reverse({"report_id": "r2"})

    assert col.docs[0]["report_id"] == "r1"
    assert "created_at" in col.docs[0]
    assert "created_at2" in col.docs[0]


def test_masking_repository_inserts(monkeypatch):
    col = DummyCol()
    monkeypatch.setattr(db, "col_masking", col)

    repo = MaskingRepository()
    repo.save_masking({"report_id": "r1"})

    assert col.docs[0]["report_id"] == "r1"
    assert "created_at" in col.docs[0]


def test_reformat_repository_inserts(monkeypatch):
    col = DummyCol()
    monkeypatch.setattr(db, "col_final", col)

    repo = ReformatRepository()
    repo.save_final({"report_id": "r1"})

    assert col.docs[0]["report_id"] == "r1"
    assert "created_at" in col.docs[0]


# === Masking Results Feature (jalur B / ProofreadRepo) ==================
# 9-field whitelist mirror untuk dataset improvement model.
# Lihat: docs/superpowers/specs/2026-04-29-masking-results-feature-design.md

_MASKING_META = {"toc_type": "general", "tenant": "indonesia", "locale": "id"}
_MASKING_LAYERS = [{"layer": "regex_PERSON", "pairs": []}]
_MASKING_ORDER = ["regex_PERSON"]


def _call_save_masking(repo: ProofreadRepo, rid: str = "rid-test") -> None:
    repo.save_masking(
        rid=rid,
        meta=_MASKING_META,
        body="halo dunia",
        masked="halo [TEXT_1]",
        layers=_MASKING_LAYERS,
        order=_MASKING_ORDER,
    )


def _safe_insert_passthrough(col, doc):
    """Bypass services.db.safe_insert / safe_insert_force checks (DB_DISABLED,
    STORE_DB, db is None, dst.) yang berbeda antara environment lokal dan CI.
    Tetap respect col is None (failure isolation untuk mirror)."""
    if col is None:
        return False
    col.insert_one(doc)
    return True


def _isolate_proofread_repo_io(monkeypatch):
    """Lepas ketergantungan test ke STORE_DB / col_summary / db internals yang
    bisa berbeda per environment. Test fokus ke logika ProofreadRepo, bukan
    ke safe_insert / safe_insert_force atau upsert_summary."""
    monkeypatch.setattr(db, "safe_insert", _safe_insert_passthrough)
    monkeypatch.setattr(db, "safe_insert_force", _safe_insert_passthrough)
    monkeypatch.setattr(db, "upsert_summary", lambda *a, **k: None)


def test_proofread_save_masking_mirrors_when_feature_on(monkeypatch):
    col_source = DummyCol()
    col_mirror = DummyCol()
    _isolate_proofread_repo_io(monkeypatch)
    monkeypatch.setattr(db, "col_masking", col_source)
    monkeypatch.setattr(db, "col_masking_results", col_mirror)
    monkeypatch.setattr(Config, "MASKING_RESULTS_FEATURE", True)

    repo = ProofreadRepo()
    _call_save_masking(repo, rid="rid-mirror")

    # Source ter-write seperti sebelumnya
    assert len(col_source.docs) == 1
    src = col_source.docs[0]
    assert src["report_id"] == "rid-mirror"
    assert src["body"] == "halo dunia"
    assert src["order"] == _MASKING_ORDER

    # Mirror ter-write dengan whitelist 9 field saja
    assert len(col_mirror.docs) == 1
    mir = col_mirror.docs[0]
    expected_fields = {
        "_id", "report_id", "toc_type", "tenant", "locale",
        "message_01", "layers", "created_at", "created_at2",
    }
    assert set(mir.keys()) == expected_fields, f"unexpected fields: {set(mir.keys()) ^ expected_fields}"

    # _id reuse (trace 1:1 source ↔ mirror)
    assert mir["_id"] == src["_id"]

    # Timestamp identik (snapshot dari source)
    assert mir["created_at"] == src["created_at"]
    assert mir["created_at2"] == src["created_at2"]

    # Field non-whitelist tidak bocor
    assert "body" not in mir
    assert "order" not in mir


def test_proofread_save_masking_skips_mirror_when_feature_off(monkeypatch):
    col_source = DummyCol()
    col_mirror = DummyCol()
    _isolate_proofread_repo_io(monkeypatch)
    monkeypatch.setattr(db, "col_masking", col_source)
    monkeypatch.setattr(db, "col_masking_results", col_mirror)
    monkeypatch.setattr(Config, "MASKING_RESULTS_FEATURE", False)

    repo = ProofreadRepo()
    _call_save_masking(repo)

    assert len(col_source.docs) == 1
    assert len(col_mirror.docs) == 0  # mirror skipped


def test_proofread_save_masking_survives_mirror_db_off(monkeypatch):
    col_source = DummyCol()
    _isolate_proofread_repo_io(monkeypatch)
    monkeypatch.setattr(db, "col_masking", col_source)
    monkeypatch.setattr(db, "col_masking_results", None)  # simulate DB-off mirror
    monkeypatch.setattr(Config, "MASKING_RESULTS_FEATURE", True)

    repo = ProofreadRepo()
    # Tidak boleh raise — passthrough respects col is None untuk mirror
    _call_save_masking(repo)

    # Source tetap ter-write
    assert len(col_source.docs) == 1


def test_proofread_save_masking_mirror_bypasses_store_db_false(monkeypatch):
    """Regression guard untuk matrix row 3:
    STORE_DB=False + MASKING_RESULTS_FEATURE=True →
      - source masking_output ❌ skip (gated by STORE_DB via safe_insert)
      - masking_results ✅ write (bypass via safe_insert_force)

    Test ini sengaja TIDAK pakai _isolate_proofread_repo_io — kita justru perlu
    safe_insert & safe_insert_force yang asli supaya logika gating-nya teruji.
    """
    col_source = DummyCol()
    col_mirror = DummyCol()

    # State globals services/db.py: koneksi hidup (DB_DISABLED off), tapi STORE_DB off
    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", False)
    monkeypatch.setattr(db, "db", object())  # cukup truthy supaya guard "db is None" lolos
    monkeypatch.setattr(db, "col_masking", col_source)
    monkeypatch.setattr(db, "col_masking_results", col_mirror)
    monkeypatch.setattr(db, "upsert_summary", lambda *a, **k: None)  # bukan fokus test
    monkeypatch.setattr(Config, "MASKING_RESULTS_FEATURE", True)

    repo = ProofreadRepo()
    _call_save_masking(repo, rid="rid-bypass")

    # Source ke-gate oleh STORE_DB=False → tidak nulis
    assert len(col_source.docs) == 0, "source masking_output harus skip saat STORE_DB=False"

    # Mirror bypass STORE_DB lewat safe_insert_force → tetap nulis
    assert len(col_mirror.docs) == 1, "mirror harus nulis meski STORE_DB=False (gated only by FEATURE)"
    mir = col_mirror.docs[0]
    assert mir["report_id"] == "rid-bypass"
    # Whitelist tetap dihormati di jalur bypass
    expected_fields = {
        "_id", "report_id", "toc_type", "tenant", "locale",
        "message_01", "layers", "created_at", "created_at2",
    }
    assert set(mir.keys()) == expected_fields
