# Masking Results Feature — Design Spec

**Tanggal:** 2026-04-29
**Branch awal:** `task/regex-reformatting-improvement03` (user akan re-branch manual)
**Status:** Design approved, ready for implementation

---

## 1. Tujuan

Menyimpan subset 9 field dari hasil masking ke collection MongoDB terpisah (`AIProofread_Masking_Results` by default) sebagai dataset untuk **improvement model masking** ke depan. Fitur harus bisa di-toggle ON/OFF lewat `.env` agar tidak menambah I/O saat tidak dibutuhkan.

## 2. Scope

- **In scope:** Mirror dokumen masking dari flow `POST /v1/proofread` (jalur B) ke collection baru, dengan whitelist 9 field.
- **Out of scope:**
  - Endpoint standalone `POST /v1/masking/mask` (jalur A) — payload-nya tidak punya `report_id/toc_type/tenant`, tidak fit dataset training.
  - Backfill tooling untuk mismatch source vs mirror.
  - Migrasi `print` → `logging` library.
  - Threading / async / queue infrastructure baru.
  - Replica-set / change stream Mongo-native approach.

## 3. Whitelist Field (9 field)

```
_id, report_id, toc_type, tenant, locale, message_01, layers, created_at, created_at2
```

Field non-whitelist dari source (`body`, `order`, dll.) **tidak** disimpan ke mirror.

## 4. Keputusan Desain

| Aspek | Keputusan | Rasional |
|---|---|---|
| Arsitektur | Inline sync via `_ins`/`safe_insert` | Konsisten 7 collection lain; failure isolation gratis; YAGNI threading |
| Toggle parsing | Strict `"ON"` case-insensitive, default OFF | Fail-safe untuk fitur I/O persistensi; konsisten dengan `RESULT_ANALYZE` |
| Toggle lifecycle | Parsed sekali saat startup (atribut `Config`) | Hot-path; konsisten dengan `AUTO_CHAIN_*`, `DETECT_*` |
| Nama collection | ENV `MASKING_RESULTS_DC`, default `AIProofread_Masking_Results` | Flexibility per-env tanpa redeploy code |
| Whitelist | Hardcoded konstanta 9 field di repo module | Schema-sensitive; ENV CSV terlalu rawan typo silent break |
| `_id` strategy | Reuse `_id` source (pre-generate `ObjectId()` di repo) | Trace 1:1 source↔mirror; idempotency natural |
| `created_at`/`created_at2` | Copy dari source (snapshot konsisten) | Trace timestamp identik antara source & mirror |
| Field hilang | Simpan apa adanya (jangan skip), log warning | Defensive logging, tidak kehilangan entry |
| Failure isolation | `safe_insert` (sudah ada) — return bool, tidak raise | Guarantee tidak ganggu response utama |
| Logging | `print` + emoji ikut pola repo | Konsistensi > generic best-practice |
| Index mirror | 2 compound: `(report_id, created_at DESC)`, `(tenant, created_at DESC)` | Mirror access pattern source + filter training pipeline by tenant |
| Unique-by-`report_id`? | **No** (non-unique) | Dataset lebih baik kelebihan entry; dedup adalah tugas preprocessing |
| Bind & index | Selalu, terlepas toggle | Idempotent, low cost; toggle ON tanpa restart tetap aman |
| `MASKING_RESULTS_DC` lokasi baca | `services/db.py` via `os.getenv` | Konsisten style file (sejajar `MONGO_URI`, `DB_NAME`) |
| `Config` import di repo | Import langsung di `proofread/repositories.py` | Read class attribute (resolved sekali di startup) |

## 5. Hard Rule

**Kegagalan write ke `col_masking_results` TIDAK BOLEH menggagalkan response utama.**

Aturan ini terpenuhi otomatis karena:
1. Insert lewat `_ins` → `safe_insert` (try/except, return bool, tidak raise)
2. Guard `col is None` / `DB_DISABLED` di `safe_insert`
3. Tidak ada exception path yang bisa propagate ke handler

## 6. File yang Disentuh

| File | Aksi |
|---|---|
| `env.example` | Tambah blok `MASKING_RESULTS_FEATURE` & `MASKING_RESULTS_DC` |
| `app/core/config.py` | Tambah atribut `Config.MASKING_RESULTS_FEATURE` (strict ON parse) |
| `services/db.py` | Tambah `MASKING_RESULTS_DC` env, global `col_masking_results`, binding, 2 index |
| `app/modules/proofread/repositories.py` | Modifikasi `save_masking()`: pre-generate `_id`, mirror conditional |
| `tests/test_repositories.py` | Tambah 3 unit test (happy path, OFF, mirror down) |
| `docs/PIPELINE.md` | Catatan tentang collection mirror & toggle |
| `docs/ENVIRONMENT.md` | Dokumentasi 2 ENV baru |
| `CLAUDE.md` (root) | 1–2 baris pointer ke fitur (opsional, untuk discoverability) |

**Tidak disentuh:** `app/modules/masking/repositories.py`, `app/modules/masking/routes.py`, `app/app.py`.

## 7. Step-by-Step Implementation Order

1. **ENV scaffolding** — `env.example`
2. **Config toggle** — `app/core/config.py`
3. **DB binding & indexes** — `services/db.py`
4. **Repo modification** — `app/modules/proofread/repositories.py`
5. **Unit tests** — `tests/test_repositories.py`
6. **Dokumentasi** — `docs/PIPELINE.md`, `docs/ENVIRONMENT.md`, opsional `CLAUDE.md`
7. **Self-verify** — pytest pass; user lanjut manual end-to-end test

## 8. Verifikasi Manual (4 Skenario)

**Skenario A — Toggle ON, full proofread**
- Hit `POST /v1/proofread` payload normal → cek kedua collection ada dokumen `_id` sama, mirror hanya 9 field.

**Skenario B — Toggle OFF**
- Set `MASKING_RESULTS_FEATURE=OFF`, restart → mirror tidak ter-write.

**Skenario C — Endpoint standalone tidak terpengaruh**
- Toggle ON, hit `POST /v1/masking/mask` → mirror tidak ter-write (out of scope).

**Skenario D — Mirror down (opsional)**
- Drop collection / set read-only → response sukses, source ter-write, mirror gagal silent.

**Index check:** `db.AIProofread_Masking_Results.getIndexes()` harus 3 entry (`_id_`, `report_id_1_created_at_-1`, `tenant_1_created_at_-1`).

## 9. ENV Format

```env
# Data Masking Model Improvement
MASKING_RESULTS_FEATURE=ON         # ON | OFF (default OFF, strict)
MASKING_RESULTS_DC=AIProofread_Masking_Results
```

## 10. Asumsi yang Dibuat

1. Setup Mongo saat ini single-node (bukan replica set) — berdasarkan `directConnection=true` di `MONGO_URI` contoh.
2. User flow normal hanya 1 dokumen masking per `report_id` per request.
3. `bson.ObjectId` tersedia (auto via pymongo dependency).
4. Test eksisting `tests/test_repositories.py:29-37` (jalur A `MaskingRepository`) tidak terganggu oleh perubahan di jalur B `ProofreadRepo`.
5. User akan handle git operasi (branch, commit, push) secara manual setelah testing.

## 11. Open Questions (Resolved)

Semua pertanyaan terbuka dari brainstorming sudah dijawab user:
- Q: Scope jalur A/B/keduanya? → **A: Hanya jalur B**
- Q: Pendekatan A/B/C? → **A: Inline sync**
- Q: Toggle pattern? → **Strict `"ON"`, parsed sekali**
- Q: Whitelist & `_id`? → **Hardcoded, reuse `_id`, copy timestamp**
- Q: Failure handling? → **`safe_insert` cukup, tidak perlu retry/CB/DLQ**
- Q: Indexing? → **2 compound, non-unique**
- Q: Testing? → **3 unit test + 4 skenario manual**

## 12. Catatan Implementasi

- User minta **tidak commit apapun**. Setelah implementasi selesai dan pytest pass, hand-off ke user untuk manual testing & git operasi.
- Stay di branch `task/regex-reformatting-improvement03` (user akan handle re-branch manual jika diperlukan).
