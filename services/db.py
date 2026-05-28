import os, time
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Any
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import OperationFailure

# --- ENV ---
MONGO_URI    = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/AI_Proofread")
DB_NAME      = os.getenv("MONGO_DB", "AI_Proofread")
DB_DISABLED  = os.getenv("DB_DISABLED", "0").lower() in ("1", "true", "yes")
STORE_DB     = os.getenv("STORE_DB", "1").lower() in ("1", "true", "yes")
FAIL_ON_DB   = os.getenv("FAIL_ON_DB", "0").lower() in ("1", "true", "yes")
MASKING_RESULTS_DC = os.getenv("MASKING_RESULTS_DC", "AIProofread_Masking_Results")

# parsed locally to mirror app/core/config.py:56 — hindari circular dep services/ → app/core/
_MASKING_RESULTS_FEATURE_ENV = (os.getenv("MASKING_RESULTS_FEATURE") or "").strip().upper() == "ON"
if _MASKING_RESULTS_FEATURE_ENV and not MASKING_RESULTS_DC.strip():
  raise ValueError(
    "MASKING_RESULTS_FEATURE=ON but MASKING_RESULTS_DC is empty. "
    "Set MASKING_RESULTS_DC to a valid collection name in .env."
  )

# --- Globals (diisi saat init_db) ---
client: Optional[MongoClient] = None
db = None

col_html_freeze  = None
col_html_reverse = None
col_masking      = None
col_masking_results = None
col_generative   = None
col_summary      = None
col_unmask       = None
col_final        = None
col_ratelimit    = None

# --- WIB helpers ---
TZ_WIB = timezone(timedelta(hours=7), name="WIB")
ID_MONTHS = [
  "Januari","Februari","Maret","April","Mei","Juni",
  "Juli","Agustus","September","Oktober","November","Desember"
]

def now_utc() -> datetime:
  return datetime.now(timezone.utc)

def now_wib() -> datetime:
  return datetime.now(TZ_WIB)

def wib_iso(dt: datetime | None = None) -> str:
  dt = dt or now_wib()
  return dt.replace(microsecond=0).isoformat()

def wib_human(dt: datetime | None = None) -> str:
  dt = dt or now_wib()
  return f"{dt.day:02d} {ID_MONTHS[dt.month-1]} {dt.year} {dt:%H:%M:%S} WIB"

# --- Small utils ---
def _dbname_from_uri(uri: str, default: str) -> str:
  """
  Ambil nama DB dari URI (path '/DB'), kalau kosong pakai default.
  """
  try:
    p = urlparse(uri)
    path = (p.path or "").lstrip("/")
    name = path.split("?")[0].strip()
    return name or default
  except Exception:
    return default

def _keys_equal(a: List[tuple], b: List[tuple]) -> bool:
  # Samakan bentuk list-of-tuples
  return list(a) == list(b)

def _ensure_index(col, keys: List[tuple], **kwargs) -> Optional[str]:
  """
  Buat index kalau belum ada. Jika sudah ada dengan opsi beda, TIDAK drop—
  hanya log peringatan & skip (biar aman di dev/prod).
  Jangan set 'name=' supaya selaras dengan nama auto Mongo.
  """
  try:
    info = col.index_information()
    for name, meta in info.items():
      if _keys_equal(meta.get("key", []), keys):
        # Cek opsi penting yang bisa konflik
        req_unique = kwargs.get("unique", None)
        ex_unique  = meta.get("unique", False)
        req_ttl    = kwargs.get("expireAfterSeconds", None)
        ex_ttl     = meta.get("expireAfterSeconds", None)

        unique_ok = (req_unique is None) or (req_unique == ex_unique)
        ttl_ok    = (req_ttl is None) or (req_ttl == ex_ttl)

        if unique_ok and ttl_ok:
          return name  # sudah ada & kompatibel
        else:
          print(f"⚠️  Index exists on {col.name} {keys} with different options "
                f"(existing unique={ex_unique}, ttl={ex_ttl}; requested unique={req_unique}, ttl={req_ttl}). Keep existing.")
          return name
    # Tidak ada index dengan keys tsb → buat baru
    return col.create_index(keys, **kwargs)
  except OperationFailure as e:
    # 85 IndexOptionsConflict, 86 IndexKeySpecsConflict
    if e.code in (85, 86):
      print(f"⚠️  Index conflict on {col.name} {keys}: {getattr(e, 'details', {}).get('errmsg', str(e))}")
      return None
    raise

def _ensure_ttl(col, field: str = "expireAt", expireAfterSeconds: int = 0) -> None:
  """
  Pastikan ada TTL index di 'field' (Date). Jika ada TTL lain, biarkan.
  """
  info = col.index_information()
  for _, meta in info.items():
    if meta.get("expireAfterSeconds") is not None:
      # kalau sudah ada TTL, cukup—hindari konflik
      if _keys_equal(meta.get("key", []), [(field, 1)]):
        return
  _ensure_index(col, [(field, 1)], expireAfterSeconds=expireAfterSeconds)

# --- Public: init & helpers ---
def init_db() -> None:
  """
  Hubungkan ke Mongo dan pastikan index. Aman dipanggil berulang (idempotent).
  Tidak melempar error saat gagal kecuali FAIL_ON_DB=1.
  """
  global client, db
  global col_html_freeze, col_html_reverse, col_masking, col_masking_results, col_generative
  global col_summary, col_unmask, col_final, col_ratelimit

  if DB_DISABLED:
    print("⚠️  DB_DISABLED=1 → skip Mongo init.")
    return

  try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    dbname = _dbname_from_uri(MONGO_URI, DB_NAME)
    db = client[dbname]
    client.admin.command("ping")
    print(f"✅ MongoDB connected → DB: {db.name}")

    # Bind koleksi
    col_html_freeze     = db["html_freeze_output"]
    col_html_reverse    = db["html_reverse_output"]
    col_masking         = db["masking_output"]
    col_masking_results = db[MASKING_RESULTS_DC]
    col_generative      = db["generative_output"]
    col_summary         = db["summary_output"]
    col_unmask          = db["unmask_output"]
    col_final           = db["final_reformating_output"]
    col_ratelimit       = db["rate_limit_output"]

    # Indexes (tanpa 'name=' untuk menghindari konflik nama)
    _ensure_index(col_html_freeze,     [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_html_reverse,    [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_masking,         [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_masking_results, [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_masking_results, [("tenant", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_generative,      [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_summary,         [("report_id", ASCENDING)], unique=True)
    _ensure_index(col_summary,         [("created_at", DESCENDING)])
    _ensure_index(col_unmask,          [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_final,           [("report_id", ASCENDING), ("created_at", DESCENDING)])
    _ensure_index(col_ratelimit,       [("key", ASCENDING)], unique=True)
    _ensure_ttl(col_ratelimit, field="expireAt", expireAfterSeconds=0)

  except Exception as e:
    print(f"❌ Mongo init failed: {e}")
    if FAIL_ON_DB:
      raise
    # Biarkan db/col_* None; caller harus guard saat insert

def upsert_summary(report_id: str, payload: dict):
  """
  Upsert ringkas; no-op jika DB off.
  """
  if DB_DISABLED or (not STORE_DB) or db is None or col_summary is None:
    return None
  noww = now_wib()
  doc = col_summary.find_one_and_update(
    {"report_id": report_id},
    {
      "$set": {k: v for k, v in payload.items() if v is not None},
      "$setOnInsert": {"created_at": wib_iso(noww), "created_at2": wib_human(noww)},
    },
    upsert=True,
    return_document=ReturnDocument.AFTER
  )
  return doc

# In-memory fallback untuk rate limiting (dipakai saat DB off)
_mem_rate: dict[str, Tuple[int, float]] = {}

def ratelimit_incr(key: str, window_sec: int):
    """
    Fixed-window RPS berbasis Mongo (kompatibel Mongo 4.x/5.x).
    - Langkah 1: coba INC dalam window aktif (expireAt > now)
    - Langkah 2: jika window habis / dokumen belum ada → reset count=1 dan set expireAt=now+window
    Return: (count, expiry_ts_epoch_seconds)
    """
    if DB_DISABLED or db is None or col_ratelimit is None:
        # fallback in-memory (per-proses)
        now = time.time()
        count, exp = _mem_rate.get(key, (0, now + window_sec))
        if now > exp:
            count, exp = 0, now + window_sec
        count += 1
        _mem_rate[key] = (count, exp)
        return count, exp

    now_utc = datetime.now(timezone.utc)
    # 1) Coba increment di window aktif
    doc = col_ratelimit.find_one_and_update(
        {"key": key, "expireAt": {"$gt": now_utc}},
        {"$inc": {"count": 1}},
        return_document=ReturnDocument.AFTER
    )
    if doc is None:
        # 2) Reset window (dokumen baru atau window sudah lewat)
        expire_at = now_utc + timedelta(seconds=window_sec)
        doc = col_ratelimit.find_one_and_update(
            {"key": key, "$or": [{"expireAt": {"$lte": now_utc}}, {"expireAt": {"$exists": False}}]},
            {"$set": {"key": key, "count": 1, "expireAt": expire_at}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    exp_dt = doc.get("expireAt", now_utc + timedelta(seconds=window_sec))
    # Simpan sebagai epoch seconds (UTC) untuk Retry-After
    exp_ts = exp_dt.replace(tzinfo=timezone.utc).timestamp()
    return int(doc.get("count", 1)), exp_ts

def safe_insert(col, doc: dict) -> bool:
  """
  Insert aman (silent skip saat DB off).
  """
  if col is None or db is None or DB_DISABLED or (not STORE_DB):
    if not STORE_DB:
      print("WARN STORE_DB=0 -> skip insert", doc.get("report_id"))
    elif DB_DISABLED:
      print("WARN DB_DISABLED=1 -> skip insert", doc.get("report_id"))
    else:
      print("WARN DB unavailable -> skip insert", doc.get("report_id"))
    return False
  try:
    col.insert_one(doc)
    return True
  except Exception as e:
    print(f"❌ DB insert failed: {e}")
    return False

def safe_insert_force(col, doc: dict) -> bool:
  """
  Insert paksa untuk audit: abaikan STORE_DB, tapi tetap hormati DB_DISABLED.
  """
  if col is None or db is None or DB_DISABLED:
    if DB_DISABLED:
      print("WARN DB_DISABLED=1 -> skip insert", doc.get("report_id"))
    else:
      print("WARN DB unavailable -> skip insert", doc.get("report_id"))
    return False
  try:
    col.insert_one(doc)
    return True
  except Exception as e:
    print(f"❌ DB insert failed: {e}")
    return False
