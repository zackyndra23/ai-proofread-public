from datetime import datetime
import pytest
from services import db


def test_dbname_from_uri():
    assert db._dbname_from_uri("mongodb://localhost:27017/mydb", "fallback") == "mydb"
    assert db._dbname_from_uri("mongodb://localhost:27017/", "fallback") == "fallback"


def test_dbname_from_uri_bad_input_returns_default():
    assert db._dbname_from_uri(None, "fallback") == "fallback"


def test_dbname_from_uri_exception_returns_default():
    class Bad:
        def __str__(self):
            raise RuntimeError("boom")

    assert db._dbname_from_uri(Bad(), "fallback") == "fallback"


def test_now_utc_tzinfo():
    out = db.now_utc()
    assert out.tzinfo is not None
    assert out.tzinfo.utcoffset(out).total_seconds() == 0


def test_wib_iso_and_human():
    dt = datetime(2025, 1, 2, 3, 4, 5, tzinfo=db.TZ_WIB)
    assert db.wib_iso(dt) == "2025-01-02T03:04:05+07:00"
    assert db.wib_human(dt) == "02 Januari 2025 03:04:05 WIB"


def test_keys_equal():
    assert db._keys_equal([("a", 1)], [("a", 1)]) is True
    assert db._keys_equal([("a", 1)], [("b", 1)]) is False


def test_ensure_index_creates_and_reuses():
    class DummyCol:
        def __init__(self):
            self._info = {}

        def index_information(self):
            return self._info

        def create_index(self, keys, **kwargs):
            name = "idx_%d" % (len(self._info) + 1)
            self._info[name] = {"key": keys, **kwargs}
            return name

    col = DummyCol()
    name = db._ensure_index(col, [("a", 1)])
    assert name in col.index_information()
    name2 = db._ensure_index(col, [("a", 1)])
    assert name2 == name


def test_ensure_index_conflict():
    class DummyCol:
        def __init__(self):
            self._info = {"idx": {"key": [("a", 1)], "unique": True}}
            self.name = "dummy"

        def index_information(self):
            return self._info

        def create_index(self, keys, **kwargs):
            raise AssertionError("should not create")

    col = DummyCol()
    name = db._ensure_index(col, [("a", 1)], unique=False)
    assert name == "idx"


def test_ensure_ttl():
    class DummyCol:
        def __init__(self):
            self._info = {}

        def index_information(self):
            return self._info

        def create_index(self, keys, **kwargs):
            self._info["ttl"] = {"key": keys, **kwargs}
            return "ttl"

    col = DummyCol()
    db._ensure_ttl(col, field="expireAt", expireAfterSeconds=0)
    assert col.index_information()["ttl"]["expireAfterSeconds"] == 0


def test_ensure_ttl_skips_when_existing():
    class DummyCol:
        def __init__(self):
            self._info = {"ttl": {"key": [("expireAt", 1)], "expireAfterSeconds": 0}}
            self.create_called = False

        def index_information(self):
            return self._info

        def create_index(self, keys, **kwargs):
            self.create_called = True
            raise AssertionError("should not create")

    col = DummyCol()
    db._ensure_ttl(col, field="expireAt", expireAfterSeconds=0)
    assert col.create_called is False


def test_ensure_index_operation_failure(monkeypatch):
    class DummyCol:
        name = "dummy"

        def index_information(self):
            from pymongo.errors import OperationFailure

            raise OperationFailure("conflict", code=85, details={"errmsg": "conflict"})

    assert db._ensure_index(DummyCol(), [("a", 1)]) is None


def test_ensure_index_operation_failure_raises():
    from pymongo.errors import OperationFailure

    class DummyCol:
        name = "dummy"

        def index_information(self):
            raise OperationFailure("boom", code=50, details={"errmsg": "boom"})

    import pytest
    with pytest.raises(OperationFailure):
        db._ensure_index(DummyCol(), [("a", 1)])


def test_upsert_summary(monkeypatch):
    class DummySummary:
        def find_one_and_update(self, filt, update, upsert=False, return_document=None):
            doc = {"report_id": filt["report_id"]}
            doc.update(update["$set"])
            doc.update(update["$setOnInsert"])
            return doc

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", True)
    monkeypatch.setattr(db, "db", object())
    monkeypatch.setattr(db, "col_summary", DummySummary())

    out = db.upsert_summary("r1", {"a": 1})
    assert out["report_id"] == "r1"
    assert out["a"] == 1


def test_safe_insert_paths(monkeypatch):
    class DummyCol:
        def __init__(self):
            self.docs = []

        def insert_one(self, doc):
            self.docs.append(doc)

    monkeypatch.setattr(db, "DB_DISABLED", True)
    monkeypatch.setattr(db, "STORE_DB", True)
    assert db.safe_insert(DummyCol(), {"a": 1}) is False

    class BadCol:
        def insert_one(self, doc):
            raise RuntimeError("fail")

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", True)
    monkeypatch.setattr(db, "db", object())
    assert db.safe_insert(BadCol(), {"a": 1}) is False


def test_store_db_off_skips_writes(monkeypatch):
    class DummySummary:
        def __init__(self):
            self.called = False

        def find_one_and_update(self, *args, **kwargs):
            self.called = True
            return {"report_id": "r1"}

    class DummyCol:
        def __init__(self):
            self.docs = []

        def insert_one(self, doc):
            self.docs.append(doc)

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", False)
    monkeypatch.setattr(db, "db", object())
    monkeypatch.setattr(db, "col_summary", DummySummary())

    assert db.upsert_summary("r1", {"a": 1}) is None
    assert db.safe_insert(DummyCol(), {"a": 1}) is False


def test_safe_insert_db_unavailable(monkeypatch):
    class DummyCol:
        def insert_one(self, doc):
            raise AssertionError("should not insert")

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", True)
    monkeypatch.setattr(db, "db", None)
    assert db.safe_insert(DummyCol(), {"report_id": "r1"}) is False


def test_safe_insert_success(monkeypatch):
    class DummyCol:
        def __init__(self):
            self.docs = []

        def insert_one(self, doc):
            self.docs.append(doc)

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", True)
    monkeypatch.setattr(db, "db", object())
    col = DummyCol()
    assert db.safe_insert(col, {"a": 1}) is True
    assert col.docs == [{"a": 1}]

def test_safe_insert_force_ignores_store_db(monkeypatch):
    class DummyCol:
        def __init__(self):
            self.docs = []

        def insert_one(self, doc):
            self.docs.append(doc)

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "STORE_DB", False)
    monkeypatch.setattr(db, "db", object())
    col = DummyCol()
    assert db.safe_insert_force(col, {"a": 1}) is True
    assert col.docs == [{"a": 1}]

def test_safe_insert_force_respects_db_disabled(monkeypatch):
    class DummyCol:
        def insert_one(self, doc):
            raise AssertionError("should not insert")

    monkeypatch.setattr(db, "DB_DISABLED", True)
    monkeypatch.setattr(db, "STORE_DB", True)
    monkeypatch.setattr(db, "db", object())
    assert db.safe_insert_force(DummyCol(), {"a": 1}) is False


def test_init_db_disabled(monkeypatch):
    monkeypatch.setattr(db, "DB_DISABLED", True)
    monkeypatch.setattr(db, "client", None)
    monkeypatch.setattr(db, "db", None)
    db.init_db()
    assert db.client is None
    assert db.db is None


def test_init_db_success(monkeypatch):
    class DummyCollection:
        def __init__(self, name):
            self.name = name

        def index_information(self):
            return {}

    class DummyDB:
        def __init__(self, name):
            self.name = name
            self.cols = {}

        def __getitem__(self, item):
            col = self.cols.get(item)
            if col is None:
                col = DummyCollection(item)
                self.cols[item] = col
            return col

    class DummyAdmin:
        @staticmethod
        def command(_):
            return {"ok": 1}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.admin = DummyAdmin()
            self._dbs = {}

        def __getitem__(self, name):
            if name not in self._dbs:
                self._dbs[name] = DummyDB(name)
            return self._dbs[name]

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "FAIL_ON_DB", False)
    monkeypatch.setattr(db, "MongoClient", DummyClient)
    monkeypatch.setattr(db, "_ensure_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(db, "_ensure_ttl", lambda *args, **kwargs: None)

    db.init_db()
    assert db.db is not None
    assert db.col_summary is not None


def test_init_db_raises_when_fail_on_db(monkeypatch):
    class DummyClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "FAIL_ON_DB", True)
    monkeypatch.setattr(db, "MongoClient", DummyClient)

    with pytest.raises(RuntimeError):
        db.init_db()


def test_ratelimit_incr_db_path(monkeypatch):
    class DummyRateCol:
        def __init__(self):
            self.doc = None

        def find_one_and_update(self, filt, update, upsert=False, return_document=None):
            if "$inc" in update:
                return None
            self.doc = {
                "count": update["$set"]["count"],
                "expireAt": update["$set"]["expireAt"],
            }
            return self.doc

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "db", object())
    monkeypatch.setattr(db, "col_ratelimit", DummyRateCol())

    count, exp = db.ratelimit_incr("k", 10)
    assert count == 1
    assert exp > 0


def test_ratelimit_incr_db_existing(monkeypatch):
    class DummyRateCol:
        def __init__(self):
            self.doc = {"count": 2, "expireAt": datetime.utcnow()}

        def find_one_and_update(self, filt, update, upsert=False, return_document=None):
            if "$inc" in update:
                return self.doc
            return self.doc

    monkeypatch.setattr(db, "DB_DISABLED", False)
    monkeypatch.setattr(db, "db", object())
    monkeypatch.setattr(db, "col_ratelimit", DummyRateCol())

    count, exp = db.ratelimit_incr("k", 10)
    assert count == 2
    assert exp > 0


def test_ratelimit_incr_fallback_resets(monkeypatch):
    monkeypatch.setattr(db, "DB_DISABLED", True)
    monkeypatch.setattr(db, "db", None)
    monkeypatch.setattr(db, "col_ratelimit", None)
    db._mem_rate.clear()

    t = {"now": 1000.0}
    monkeypatch.setattr(db.time, "time", lambda: t["now"])

    c1, exp1 = db.ratelimit_incr("k", 10)
    assert c1 == 1

    t["now"] = exp1 + 0.1
    c2, exp2 = db.ratelimit_incr("k", 10)
    assert c2 == 1
    assert exp2 > exp1
