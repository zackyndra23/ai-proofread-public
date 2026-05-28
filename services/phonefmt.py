"""
Utility pemformatan nomor telepon, fokus ke aturan Indonesia:
- Landline dengan kode area: "(021) 424 46 91 2" style
- Mobile 10/11/12 digit: 0XXX XXX XXX / 0XXX XXXX XXX / 0XXX XXXX XXXX
- Nomor non-Indonesia: dibiarkan apa adanya

Expose API utama:
    apply_reformatting(text: str, locale: str) -> tuple[str, dict]
"""

import re
from dataclasses import dataclass

from typing import Tuple, Dict

try:
    from phonenumbers import (
        PhoneNumberMatcher,
        parse as pn_parse,
        NumberParseException,
        format_number,
        PhoneNumberFormat,
        is_valid_number,
    )
except Exception:
    PhoneNumberMatcher = None
    pn_parse = None
    NumberParseException = Exception
    format_number = None
    PhoneNumberFormat = None
    is_valid_number = None

from services.utils import locale_to_region
from services.phone_world_cc import WORLD_CC

# --- regex token internasional +CC... ---
_RE_INTL = re.compile(r'\+\d{1,3}(?:[\s\-\.\(\)]*\d)+')

# Sisipkan Zero Width Space setelah tanda '+' agar token tidak terdeteksi lagi
_FREEZE_CHAR = "\u200B"  # ZERO WIDTH SPACE

def _freeze_plus(s: str) -> str:
    # ganti setiap '+' menjadi '+<ZWS>' agar libphonenumbers tidak match
    return s.replace("+", "+" + _FREEZE_CHAR)

def _unfreeze_plus(s: str) -> str:
    return s.replace(_FREEZE_CHAR, "")

# ----- Malayssia dan Thailand environment

@dataclass
class _ProtectedSpan:
    placeholder: str
    original: str

def _protect_spans(text: str, spans: list[tuple[int,int]], tag: str) -> tuple[str, list[_ProtectedSpan]]:
    """
    Replace spans with placeholders so downstream passes (phone/date) won't touch them.
    spans: list of (start,end) in ORIGINAL text coordinates.
    """
    if not spans:
        return text, []

    # replace from back to front to keep offsets valid
    spans_sorted = sorted(spans, key=lambda x: x[0], reverse=True)
    protected: list[_ProtectedSpan] = []
    out = text
    for i, (s, e) in enumerate(spans_sorted):
        original = out[s:e]
        ph = f"[[PROTECTED_{tag}_{i}]]"
        out = out[:s] + ph + out[e:]
        protected.append(_ProtectedSpan(placeholder=ph, original=original))
    return out, protected

def _restore_spans(text: str, protected: list[_ProtectedSpan]) -> str:
    out = text
    for p in protected:
        out = out.replace(p.placeholder, p.original)
    return out
_TH_IDCARD_LINE = re.compile(
    # r'(?im)^(?P<label>\s*ID\s*Card\s*Number\s*:\s*)(?P<num>[0-9][0-9 \-]{8,}[0-9])\s*$'
    r'(?im)^(?P<label>\s*ID\s*Card\s*Number\s*:\s*)(?P<num>\d(?:[\d\s\-]{8,}\d))\s*$'
)

def _protect_th_idcard_numbers(text: str, tenant: str) -> tuple[str, list[_ProtectedSpan]]:
    t = (tenant or "").strip().lower()

    # Kalau tenant di-set dan bukan Thailand -> jangan protect
    if t and t != "thailand":
        return text, []

    # Kalau tenant kosong -> tetap protect, karena labelnya eksplisit "ID Card Number:"
    spans = []
    for m in _TH_IDCARD_LINE.finditer(text):
        spans.append((m.start("num"), m.end("num")))

    return _protect_spans(text, spans, tag="TH_ID")

# --- Thailand: protect Buddhist year pattern in ID report lines ---
# contoh: "Date of Birth: 24 September 2543 (2000)"
_TH_IDDATE_LINE = re.compile(
    r'(?im)^(?P<label>\s*(?:Date\s+of\s+Birth|ID\s+Issued\s+Date|ID\s+Expired\s+Date)\s*:\s*)'
    r'(?P<body>.*)$'
)

_TH_BUDDHIST_PAIR = re.compile(r'\b(?P<byear>\d{4})\s*\(\s*(?P<gyear>\d{4})\s*\)')

# --- Thailand: protect Registered Address line so it won't be phone-formatted ---
_TH_REGISTERED_ADDRESS_LINE = re.compile(
    r'(?im)^(?P<label>\s*Registered\s+Address\s*:\s*)(?P<body>.*)$'
)

def _protect_th_buddhist_year_pairs(text: str, tenant: str) -> tuple[str, list[_ProtectedSpan]]:
    """
    Protect '2543 (2000)' / '2567 (2024)' / '2575 (2032)' on Thai ID report lines
    so they won't be parsed as international phone numbers.
    Tenant rule:
      - if tenant set and not thailand -> skip
      - if tenant empty -> still protect (label is explicit)
    """
    t = (tenant or "").strip().lower()
    if t and t != "thailand":
        return text, []

    spans: list[tuple[int, int]] = []

    # cari baris label yang relevan
    for m in _TH_IDDATE_LINE.finditer(text):
        body = m.group("body") or ""
        # cari semua pasangan "2543 (2000)" di body
        for ym in _TH_BUDDHIST_PAIR.finditer(body):
            # konversi offset dari body ke offset text global
            s = m.start("body") + ym.start()
            e = m.start("body") + ym.end()
            spans.append((s, e))

    return _protect_spans(text, spans, tag="TH_BYEAR")

def _protect_th_registered_address(text: str, tenant: str) -> tuple[str, list[_ProtectedSpan]]:
    """
    Protect the whole value after 'Registered Address:' on Thai ID report lines
    so phone/date reformatting will NOT touch unit numbers like '10/142 (1502B)'.

    Tenant rule:
      - if tenant set and not thailand -> skip
      - if tenant empty -> still protect (label is explicit)
    """
    t = (tenant or "").strip().lower()
    if t and t != "thailand":
        return text, []

    spans: list[tuple[int, int]] = []
    for m in _TH_REGISTERED_ADDRESS_LINE.finditer(text):
        spans.append((m.start("body"), m.end("body")))

    return _protect_spans(text, spans, tag="TH_ADDR")

_MY_IC_IN_PAREN = re.compile(
    r'(?i)(Identity\s*Card\s*number\s*\()(?P<num>[^)]{6,40})(\))'
)

def _normalize_my_identity_card_in_paren(text: str, tenant: str, changes: list[dict]) -> str:
    t = (tenant or "").strip().lower()

    # Kalau tenant di-set dan bukan Malaysia -> jangan ubah
    if t and t != "malaysia":
        return text

    def sub(m: re.Match) -> str:
        before = m.group(0)
        raw = m.group("num")
        digits = re.sub(r"\D+", "", raw)

        # NRIC biasanya 12 digit. Kalau bukan, jangan sentuh.
        if len(digits) != 12:
            return before

        after = f"{m.group(1)}{digits}{m.group(3)}"
        if after != before:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "my_nric_compact"})
        return after

    return _MY_IC_IN_PAREN.sub(sub, text)

def _protect_my_nric_in_paren(text: str, tenant: str) -> tuple[str, list[_ProtectedSpan]]:
    """
    Protect digits inside 'Identity Card number ( ... )' so it won't be phone-formatted.
    Tenant rule:
      - if tenant set and not malaysia -> skip
      - if tenant empty -> still protect (label is explicit)
    """
    t = (tenant or "").strip().lower()
    if t and t != "malaysia":
        return text, []

    spans: list[tuple[int, int]] = []
    for m in _MY_IC_IN_PAREN.finditer(text):
        raw = m.group("num")
        digits = re.sub(r"\D+", "", raw or "")
        # only protect if it looks like NRIC (12 digits)
        if len(digits) == 12:
            spans.append((m.start("num"), m.end("num")))

    return _protect_spans(text, spans, tag="MY_NRIC")

# ------------------------------
# Helpers (grouping & formatter)
# ------------------------------

def _group_chunks(s: str, sizes) -> str:
    """Bagi string s jadi potongan sesuai tuple sizes, sisanya ditaruh di belakang."""
    parts = []
    i = 0
    for sz in sizes:
        if i >= len(s):
            break
        parts.append(s[i:i + sz])
        i += sz
    if i < len(s):
        parts.append(s[i:])
    return " ".join([p for p in parts if p])


def _format_id_landline(area: str, subscriber: str) -> str:
    """
    Formatter landline Indonesia berdasarkan panjang subscriber (tanpa kode area).
    """
    n = len(subscriber)
    if   n == 6:  grp = (3, 3)
    elif n == 7:  grp = (3, 2, 2)
    elif n == 8:  grp = (4, 4)
    elif n == 9:  grp = (3, 2, 2, 2)   # fallback mendekati contoh "(021) 424 46 91 2"
    else:         grp = (3, 3, 3)      # default aman
    return f"({area}) {_group_chunks(subscriber, grp)}"

def _format_id_mobile(nsn0: str) -> str:
    """
    Formatter mobile Indonesia. nsn0 termasuk leading '0', contoh: '08157100005'
    """
    n = len(nsn0)
    if   n == 10: grp = (4, 3, 3)   # 0XXX XXX XXX
    elif n == 11: grp = (4, 4, 3)   # 0XXX XXXX XXX
    elif n == 12: grp = (4, 4, 4)   # 0XXX XXXX XXXX
    else:         grp = (4, 3, 4)   # fallback
    return _group_chunks(nsn0, grp)

def _format_intl_landline(cc: str, area_with0: str, subscriber: str, prefer_43_len7: bool = False) -> str:
    """
    '(_+CC_) <area_tanpa_0> <subscriber_groups>'
    Default grup:
      len=6  -> 3-3
      len=7  -> 3-4 (kecuali prefer_43_len7=True -> 4-3)
      len=8  -> 4-4         # <-- samakan dengan formatter nasional
      len=9  -> 3-2-2-2 (fallback)
    """
    n = len(subscriber)
    if   n == 6:  grp = (3, 3)
    elif n == 7:  grp = (4, 3) if prefer_43_len7 else (3, 2, 2)
    elif n == 8:  grp = (4, 4)        # <--- di sini diubah
    else:         grp = (3, 2, 2, 2)
    area_wo0 = area_with0[1:] if area_with0.startswith("0") else area_with0
    return f"(+{cc}) {area_wo0} {_group_chunks(subscriber, grp)}"

def _format_intl_mobile(cc: str, nsn0: str) -> str:
    """
    Render mobile internasional model baru:
    '(_+CC_) <msisdn_tanpa_0_dengan_grouping_baru>'
    Mapping dari format nasional (dengan 0):
      10 digit (0XXX XXX XXX) -> 9 digit setelah buang '0' : 3-3-3
      11 digit (0XXX XXXX XXX) -> 10 digit: 3-4-3
      12 digit (0XXX XXXX XXXX) -> 11 digit: 3-4-4
    """
    assert nsn0.startswith("0")
    msisdn = nsn0[1:]
    n = len(nsn0)
    if   n == 10: grp = (3, 3, 3)
    elif n == 11: grp = (3, 4, 3)
    elif n == 12: grp = (3, 4, 4)
    else:         grp = (3, 4, 4)  # fallback aman
    return f"(+{cc}) {_group_chunks(msisdn, grp)}"

def _format_with_cc_as_zero(raw: str) -> Tuple[str, bool]:
    """
    Angka diawali '+' akan diperlakukan seperti angka nasional:
    1) Ambil semua digit setelah '+'.
    2) Coba deteksi country code (CC) pakai WORLD_CC (1–3 digit).
       - Jika ketemu → bangun nsn0 = '0' + sisa nomor.
         * Kalau nsn0[1] == '8' → dianggap mobile → _format_intl_mobile()
         * Kalau mulai '021' / '02' / '03' → dianggap landline → _format_intl_landline()
    3) Kalau tidak ada CC yang cocok di WORLD_CC → fallback ke heuristik lama
       (supaya tetap ada behavior untuk nomor aneh / test).
    """
    s = raw.strip()

    # "+<digit ...>" saja yang kita proses
    m = re.match(r'^\+([0-9][0-9\s\-\.\(\)]*)$', s)
    if not m:
        return raw, False

    full_after_plus = re.sub(r'\D', '', m.group(1))  # hanya digit
    if not full_after_plus or len(full_after_plus) < 2:
        return raw, False

    # Hint 4-3 utk subscriber len=7 dari teks asli (contoh: "+3121 7962 777")
    prefer_43_len7 = bool(re.search(r'(\d{4})\D+(\d{3})\s*$', s))

    # ============================
    # 1) Coba dulu pakai WORLD_CC
    # ============================
    best = None
    for cc_len in (1, 2, 3):
        if cc_len >= len(full_after_plus):
            continue

        cc_candidate = full_after_plus[:cc_len]
        if cc_candidate not in WORLD_CC:
            # bukan country code resmi → skip
            continue

        rest_digits = full_after_plus[cc_len:]
        if not rest_digits:
            # cuma country code doang
            continue

        nsn0 = "0" + rest_digits  # perlakukan sebagai nomor nasional

        # Skor “kewajaran” sama seperti sebelumnya
        score = 0
        if len(nsn0) >= 2 and nsn0[1] == "8":
            score = 3  # mobile
        elif nsn0.startswith("021"):
            score = 2  # Jakarta landline
        elif nsn0.startswith("02") or nsn0.startswith("03"):
            score = 1  # landline umum

        if best is None or score > best["score"] or (score == best["score"] and cc_len < best["cc_len"]):
            best = {
                "cc": cc_candidate,
                "rest": rest_digits,
                "nsn0": nsn0,
                "score": score,
                "cc_len": cc_len,
            }

    # Kalau ketemu kandidat pakai WORLD_CC → gunakan ini
    if best is not None:
        cc = best["cc"]
        nsn0 = best["nsn0"]

        # 1) Landline Indonesia (021 / 02x / 03x)
        if nsn0.startswith("021"):
            area, subscriber = "021", nsn0[len("021"):]
            return _format_intl_landline(cc, area, subscriber, prefer_43_len7), True
        if nsn0.startswith("02") or nsn0.startswith("03"):
            area, subscriber = nsn0[:3], nsn0[3:]
            return _format_intl_landline(cc, area, subscriber, prefer_43_len7), True

        # 2) Selain itu: perlakukan sebagai mobile internasional
        return _format_intl_mobile(cc, nsn0), True

    # =====================================
    # 2) Fallback lama (tanpa WORLD_CC)
    #    – dipakai hanya kalau benar-benar
    #      tidak ada CC di WORLD_CC
    # =====================================
    best = None
    for cc_len in (1, 2, 3):
        if cc_len >= len(full_after_plus):
            continue

        cc = full_after_plus[:cc_len]
        rest_digits = full_after_plus[cc_len:]
        nsn0 = "0" + rest_digits

        score = 0
        if len(nsn0) >= 2 and nsn0[1] == "8":
            score = 3
        elif nsn0.startswith("021"):
            score = 2
        elif nsn0.startswith("02") or nsn0.startswith("03"):
            score = 1

        if best is None or score > best["score"] or (score == best["score"] and cc_len < best["cc_len"]):
            best = {
                "cc": cc,
                "rest": rest_digits,
                "nsn0": nsn0,
                "score": score,
                "cc_len": cc_len,
            }

    if best is None:
        return raw, False

    cc = best["cc"]
    nsn0 = best["nsn0"]

    # 1) Landline Indonesia (021 / 02x / 03x)
    if nsn0.startswith("021"):
        area, subscriber = "021", nsn0[len("021"):]
        return _format_intl_landline(cc, area, subscriber, prefer_43_len7), True
    if nsn0.startswith("02") or nsn0.startswith("03"):
        area, subscriber = nsn0[:3], nsn0[3:]
        return _format_intl_landline(cc, area, subscriber, prefer_43_len7), True

    # 2) Selain itu: mobile internasional
    return _format_intl_mobile(cc, nsn0), True

def _intl_plus_pass(text: str) -> tuple[str, list]:
    changes = []

    def sub(m: re.Match) -> str:
        raw = m.group(0)  # match selalu mulai dari '+...'
        start = m.start()

        # === 1) DETEKSI NOMOR YANG SUDAH DALAM FORMAT "(+CC) ...", JANGAN DIUBAH ===
        # Kita lihat 1 karakter sebelum '+' dan gabungkan:
        prev_char = text[start - 1] if start > 0 else ""
        full = prev_char + raw  # misal "(+62) 813 652 020"

        # Jika sudah cocok pola "(+CC) <digit pertama>", kita anggap sudah benar → skip
        if prev_char == "(" and re.match(r"^\(\+\d{1,3}\)\s*\d", full):
            return raw  # jangan diubah sama sekali

        # === 2) NORMAL FLOW: reformat +CCxxx → "(+CC) ..." ===
        after, changed = _format_with_cc_as_zero(raw)
        if changed and after != raw:
            after_frozen = _freeze_plus(after)
            changes.append({
                "from": raw,
                "to": _unfreeze_plus(after_frozen),
                "span": [m.start(), m.end()],
                "via": "cc-as-zero"
            })
            return after_frozen

        return raw

    return _RE_INTL.sub(sub, text), changes

# Deteksi "CC ...digit..." dengan spasi: 62 8157 100 0051, 351 912 34 5678, dst.
_RE_INTL_PLAIN_WITH_SPACES = re.compile(
    r'(?<!\d)(\d{1,3}(?:[\s\-\.\(\)]*\d){6,})(?!\d)'
)

def _intl_plain_with_spaces_pass(text: str) -> tuple[str, list]:
    """
    Tangani nomor internasional tanpa '+' tetapi punya spasi/pemisah:
      62815 7100 0051 -> treat as '+6281571000051'
    Lalu reuse _format_with_cc_as_zero untuk format "(+CC) ...".
    """
    changes = []

    def sub(m: re.Match) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw or "")
        if len(digits) < 7:
            return raw

        # kalau > 13 digit, biarkan (hindari KTP/NIK 16 digit)
        if len(digits) > 13:
            return raw

        # kalau raw cuma digit polos, skip PASS 0.5
        # biarkan PASS 1 yang handle token digit murni
        if raw.isdigit():
            return raw

        # Cek 1–3 digit depan sebagai CC yang valid
        cc = None
        for length in (1, 2, 3):
            if len(digits) > length:
                candidate = digits[:length]
                if candidate in WORLD_CC:
                    cc = candidate
                    break

        if not cc:
            return raw

        # Bentuk pseudo "+digits" -> pakai formatter internasional existing
        pseudo = "+" + digits
        formatted, changed = _format_with_cc_as_zero(pseudo)
        if not changed:
            return raw

        # Bekukan '+' supaya tidak diutak-atik lagi
        frozen = _freeze_plus(formatted)
        changes.append({
            "from": raw,
            "to": formatted,
            "span": [m.start(), m.end()],
            "via": "cc-plain-spaced"
        })
        return frozen

    new_text = _RE_INTL_PLAIN_WITH_SPACES.sub(sub, text)
    return new_text, changes

def _format_phone_token(raw: str, locale: str) -> Tuple[str, bool]:
    """
    Return (formatted_text, is_changed).

    Behaviour:
    - Jika token diawali '+'  -> _format_with_cc_as_zero (aturan internasional custom kamu).
    - Jika token berupa 'CCxxxx' (tanpa '+', tanpa leading '0'):
        -> deteksi CC pakai WORLD_CC
        -> format pakai _format_intl_mobile(cc, '0' + rest) -> pola 3-3-3 / 3-4-3 / 3-4-4
    - Selain itu: biarkan apa adanya, supaya regex Indonesia (_fallback_regex_pass)
      yang menangani 021..., 08..., dst.
    """
    s = (raw or "").strip()
    digits = re.sub(r"\D", "", raw or "")

    if not digits:
        return raw, False

    # 1) Kasus sudah ada '+' di depan (harusnya sudah di-freeze di PASS 0,
    #    tapi kita handle kalau ada yang lolos).
    if s.startswith("+"):
        return _format_with_cc_as_zero(s)

    # 2) Kandidat internasional tanpa '+' dan tanpa leading '0'
    #    contoh: 6281365202009, 601234567890, 66812345678, 336123456789, ...
    if digits and not s.startswith(("0", "+")):
        cc = None
        # cek 1–3 digit terdepan sebagai kandidat country code berdasarkan WORLD_CC
        for length in (1, 2, 3):
            if len(digits) > length:
                candidate = digits[:length]  # string
                if candidate in WORLD_CC:
                    cc = candidate
                    break

        if cc is not None:
            rest = digits[len(cc):]
            if not rest:
                # cuma country code tanpa nomor → tidak diubah
                return raw, False

            # Bangun nsn0 = '0' + sisa nomor → gunakan aturan _format_intl_mobile
            nsn0 = "0" + rest
            formatted = _format_intl_mobile(cc, nsn0)
            return formatted, True

    # 3) Selain itu (0..., 021..., 08..., angka aneh) → biarkan,
    #    akan ditangani oleh _fallback_regex_pass khusus Indonesia.
    return raw, False

# --- Fallback regex (untuk kandidat yang lolos dari PhoneNumberMatcher) ---

# 021 + 6..8 subscriber  → landline
_RE_ID_LANDLINE = re.compile(r'(?<!\d)0(2\d{1,2})(\d{6,8})(?!\d)')

# 08 + total digit 10..12, separator opsional di antara digit.
# Penting: match selalu berakhir dengan digit, jadi tanda baca penutup
# seperti "." atau "," setelah nomor tidak ikut termatch.
_RE_ID_MOBILE = re.compile(
    r'(?<!\d)0(?:[ .()-]?\d){9,11}(?!\d)'
)

def _fallback_regex_pass(text: str) -> tuple[str, list]:
    """Tangani sisa kandidat Indonesia dengan regex, return (text_baru, changes[])"""
    changes = []

    def landline_sub(m: re.Match) -> str:
        area = "0" + m.group(1)
        sub  = m.group(2)

        # Normalisasi khusus: regex kadang rakus jadi "0217" padahal area-nya "021"
        # Contoh: "0217698277" -> m.group(1)="217", sub="698277"
        # Kita ubah jadi area="021", sub="7" + "698277" = "7698277"
        if area.startswith("021") and len(area) > 3:
            extra = area[3:]      # karakter setelah "021"
            area = "021"
            sub = extra + sub

        before = m.group(0)
        after = _format_id_landline(area, sub)
        if before != after:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "regex-landline"})
        return after

    def mobile_sub(m: re.Match) -> str:
        before = m.group(0)

        # ambil semua digit di dalam match
        digits = re.sub(r"\D", "", before)
        if not digits.startswith("08"):
            return before

        # nomor mobile Indonesia total digit biasanya 10..12
        if len(digits) < 10 or len(digits) > 12:
            return before

        nsn0 = digits
        after = _format_intl_mobile("62", nsn0)

        if before != after:
            changes.append({
                "from": before,
                "to": after,
                "span": [m.start(), m.end()],
                "via": "regex-mobile"
            })
        return after

    # urutan: landline dulu supaya 021… tidak dimakan rule mobile
    out = _RE_ID_LANDLINE.sub(landline_sub, text)
    out = _RE_ID_MOBILE.sub(mobile_sub, out)
    return out, changes

# Match pola: 27/04/2025 atau 27-04-2025
_DATE_DDMMYYYY = re.compile(r'\b(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})\b')

# Match pola: 38 March 2020 / 1 Januari 2025 / 15 août 2024
_DATE_DD_MONTHNAME_YYYY = re.compile(
    r'\b(\d{1,2})\s+('
    r'January|February|March|April|May|June|July|August|September|October|November|December|'
    r'janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|'
    r'Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember'
    r')\s+(\d{4})\b',
    re.IGNORECASE
)

_DATE_MONTHNAME_DD_YYYY_NOCOMMA = re.compile(
    r'\b('
    r'January|February|March|April|May|June|July|August|September|October|November|December|'
    r'janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|'
    r'Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember'
    r')\s+(\d{1,2})\s+(\d{4})\b',
    re.IGNORECASE
)

# Range connectors (EN/ID/FR)
_RANGE_FROM = r"(?:from|dari|sejak|depuis)"
_RANGE_TO   = r"(?:until|to|sampai|hingga|sd\.?|s\.d\.?|au|à|jusqu['’]?\s*à|jusqu['’]?a)"

# ------------------------------
# Month-Year (no day) support
# ------------------------------

_MONTH_ANY = (
    r"January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|"
    r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
)

# Match "January 2022" / "January, 2022"
_MONTHYEAR_MONTH_FIRST = re.compile(rf"\b({_MONTH_ANY})\s*,?\s*(\d{{4}})\b", re.IGNORECASE)

# Match "2022 January" / "2022, January"
_MONTHYEAR_YEAR_FIRST = re.compile(rf"\b(\d{{4}})\s*,?\s*({_MONTH_ANY})\b", re.IGNORECASE)

# Range: "from January 2022 to March 2015" (connectors reuse _RANGE_FROM/_RANGE_TO)
_MONTHYEAR_STD = rf"({_MONTH_ANY})\s+(\d{{4}})"
_MONTHYEAR_RANGE_RE = re.compile(
    rf"\b{_RANGE_FROM}\b\s+{_MONTHYEAR_STD}\s+\b{_RANGE_TO}\b\s+{_MONTHYEAR_STD}\b",
    re.IGNORECASE
)

def _parse_monthyear(month_raw: str, year_s: str):
    try:
        y = int(year_s)
    except Exception:
        return None
    mi = _MONTH_MAP_ALL.get((month_raw or "").lower())
    if not mi:
        return None
    return (y, mi)


# Date yang sudah distandardisasi: "28 May 2015" / "27 Agustus 2024" / "18 janvier 2023"
# (tetap support EN/ID/FR month names)
_DATE_STD = (
    r"(\d{1,2})\s+("
    r"January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|"
    r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
    r")\s+(\d{4})"
)

# Full pattern: "from <date1> until/to <date2>"
_DATE_RANGE_RE = re.compile(
    rf"\b{_RANGE_FROM}\b\s+{_DATE_STD}\s+\b{_RANGE_TO}\b\s+{_DATE_STD}",
    re.IGNORECASE
)

# Month map universal (EN/ID/FR) → month index
_MONTH_MAP_ALL = {
    # English
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    # Indonesian
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    # French
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

# --- PASS X: Honorific/title capitalization (ID/EN/FR) ---

# Catatan:
# - Hanya trigger kalau setelahnya ada "nama" (kata berawalan huruf) atau token nama seperti [PER_0]
# - Tidak menyentuh isi token masking sama sekali.

_RE_NAME_OR_TOKEN = r"(?:\[[A-Z]{2,5}_\d+\]|[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*)"

_HONORIFICS = [
    # Indonesian (tanpa titik)
    (r"ibu", "Ibu"),
    (r"bapak", "Bapak"),
    (r"tuan", "Tuan"),
    (r"nyonya", "Nyonya"),
    (r"saudara", "Saudara"),
    (r"saudari", "Saudari"),

    # English (pakai titik)
    (r"mr\.?", "Mr."),
    (r"mrs\.?", "Mrs."),
    (r"ms\.?", "Ms."),
    (r"miss\.?", "Miss"),
    (r"dr\.?", "Dr."),
    (r"prof\.?", "Prof."),

    # French (umum)
    (r"m\.?", "M."),       # Monsieur
    (r"mme\.?", "Mme"),    # Madame (sering tanpa titik dalam praktik modern)
    (r"mlle\.?", "Mlle"),  # Mademoiselle (jarang)
    (r"dr\.?", "Dr."),
    (r"pr\.?", "Pr."),
]

_ID_HONORIFIC_EXCEPTIONS = {
    "tuan rumah",
    "tuan tanah",
    "tuan putri",
    "ibu kota",
    "ibu jari",
    "ibu hamil",
    "ibu menyusui",
    "ibu rumah tangga",
    "ibu pertiwi",
    "bapak kos",
    "bapak angkat",
    "bapak tiri",
    "bapak bangsa",
    "bapak pembangunan",
    "bapak reformasi",
    "bapak proklamator",
    "bapak negara",
    "saudara kandung",
    "saudara tiri",
    "saudara sepupu",
    "saudara ipar",
    "saudara seiman",
    "saudara sebangsa",
    "saudara serumah",
}

def _honorific_capitalization_pass(text: str, locale: str) -> tuple[str, list]:
    changes = []
    out = text

    # loop tiap honorific biar replacement-nya sederhana dan bisa log changes
    for patt, repl in _HONORIFICS:
        rx = re.compile(
            rf"(?<!\w)({patt})\s+({_RE_NAME_OR_TOKEN})",
            flags=re.IGNORECASE
        )

        def sub(m: re.Match) -> str:
            honor_raw = m.group(1)
            next_tok = m.group(2)

            # cek false positive khusus Indonesia: "tuan rumah", "ibu kota", dll
            phrase = f"{honor_raw} {next_tok}".strip().lower()
            if phrase in _ID_HONORIFIC_EXCEPTIONS:
                return m.group(0)  # jangan diubah

            before = m.group(0)
            after = f"{repl} {next_tok}"

            if after != before:
                changes.append({
                    "from": before,
                    "to": after,
                    "span": [m.start(), m.end()],
                    "via": "honorific_cap",
                })
            return after

        out = rx.sub(sub, out)

    return out, changes

def _parse_std_date(day_s: str, month_s: str, year_s: str):
    """Return tuple (year, month, day) or None if cannot parse."""
    try:
        day = int(day_s)
        year = int(year_s)
        month = _MONTH_MAP_ALL.get((month_s or "").lower())
        if not month:
            return None
        # Optional: kalau kamu mau strict valid day per month, bisa aktifkan:
        max_day = _days_in_month(year, month)
        if not (1 <= day <= max_day):
            return None
        return (year, month, day)
    except Exception:
        return None

def _date_name_reformat_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Reformat:
        - English : "November 25, 2025" atau "November 25 2025"
        - French  : "novembre 25, 2025" atau "novembre 25 2025"
        - Indonesian: "November 25, 2025" atau "Januari 25 2025"
    menjadi:
        "25 <MonthNameLocalized> 2025"

    Catatan:
    - Jika nama bulan asli berbahasa Prancis -> pakai nama bulan Prancis (août, septembre, ...)
    - Jika nama bulan asli berbahasa Indonesia -> pakai nama bulan Indonesia (Agustus, Januari, ...)
    - Jika nama bulan asli berbahasa Inggris -> ikuti locale (id/en/fr) seperti desain awal.
    """
    changes = []

    # Set untuk deteksi bahasa bulan
    EN_MONTHS = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    }
    FR_MONTHS = {
        "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
        "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    }
    ID_MONTHS = {
        "januari", "februari", "maret", "april", "mei", "juni",
        "juli", "agustus", "september", "oktober", "november", "desember",
    }

    # Map English + French + Indonesian month names to month index
    month_map = {
        # English
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        # French
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
        # Indonesian
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    }

    # Month-name first: "Month 25, 2025" atau "Month 25 2025"
    combined_regex = re.compile(
        r'\b('
        r'January|February|March|April|May|June|July|August|September|October|November|December|'
        r'janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|'
        r'Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember'
        r')\s+(\d{1,2})[,]?\s+(\d{4})\b',
        re.IGNORECASE
    )

    def sub(m: re.Match) -> str:
        before = m.group(0)
        month_name_raw = m.group(1)
        month_name_lc = month_name_raw.lower()
        day = int(m.group(2))
        year = int(m.group(3))

        month_idx = month_map.get(month_name_lc)
        if not month_idx:
            return before

        # Deteksi bahasa dari nama bulan asli
        if month_name_lc in FR_MONTHS:
            eff_locale = "fr"
        elif month_name_lc in ID_MONTHS:
            eff_locale = "id"
        else:
            # English atau lainnya → ikuti locale global
            eff_locale = locale

        # Nama bulan sesuai "effective locale"
        # month_local = _month_name(eff_locale, month_idx)
        month_local = _month_name(locale, month_idx)
        if not month_local:
            return before

        after = f"{day} {month_local} {year}"

        if after != before:
            changes.append({
                "from": before,
                "to": after,
                "span": [m.start(), m.end()],
                "via": "datefmt_name"
            })
        return after

    new_text = combined_regex.sub(sub, text)
    return new_text, changes

def _date_day_monthname_pass(text: str, locale: str) -> tuple[str, list]:
    changes = []

    # reuse map/set dari _date_name_reformat_pass supaya konsisten
    FR_MONTHS = {
        "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
        "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    }
    ID_MONTHS = {
        "januari", "februari", "maret", "april", "mei", "juni",
        "juli", "agustus", "september", "oktober", "november", "desember",
    }
    month_map = {
        # English
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        # French
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
        # Indonesian
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    }

    def sub(m: re.Match) -> str:
        before = m.group(0)
        day_s = m.group(1)              # <-- string asli (bisa '01')
        month_name_raw = m.group(2)
        month_name_lc = month_name_raw.lower()
        year_s = m.group(3)

        try:
            day = int(day_s)
            year = int(year_s)
        except Exception:
            return before

        month_idx = month_map.get(month_name_lc)
        if not month_idx:
            return before

        if month_name_lc in FR_MONTHS:
            eff_locale = "fr"
        elif month_name_lc in ID_MONTHS:
            eff_locale = "id"
        else:
            eff_locale = locale

        month_local = _month_name(locale, month_idx)
        if not month_local:
            return before

        max_day = _days_in_month(year, month_idx)
        if not (1 <= day <= max_day):
            after = _flag_invalid_date(month_local, year)
            if after != before:
                changes.append({
                    "from": before,
                    "to": after,
                    "span": [m.start(), m.end()],
                    "via": "date_invalid_dayfirst",
                })
            return after

        day_out = _render_day_preserve_zero(day_s)   # <-- preserve '01'
        after = f"{day_out} {month_local} {year_s}"

        if after != before:
            changes.append({
                "from": before,
                "to": after,
                "span": [m.start(), m.end()],
                "via": "datefmt_dayfirst",
            })
        return after

    return _DATE_DD_MONTHNAME_YYYY.sub(sub, text), changes

def _month_name(locale: str, month: int) -> str:
    """
    Kembalikan nama bulan sesuai locale:
    - id*: Bahasa Indonesia
    - fr*: Bahasa Prancis
    - lainnya: English (format "international")
    """
    loc = (locale or "").lower()

    if loc.startswith("id"):
        names = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        ]
    elif loc.startswith("fr"):
        names = [
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre",
        ]
    else:
        # "format internasional" → pakai English
        names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]

    # fallback aman
    if month < 1 or month > 12:
        return ""
    return names[month - 1].capitalize()

def _date_name_nocomma_pass(text: str, locale: str) -> tuple[str, list]:
    changes = []

    month_map = {
        # English
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        # French
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
        # Indonesian
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    }

    def sub(m: re.Match) -> str:
        before = m.group(0)
        month_name_raw = m.group(1)
        month_name_lc = month_name_raw.lower()
        day = int(m.group(2))
        year = int(m.group(3))

        month_idx = month_map.get(month_name_lc)
        if not month_idx:
            return before

        # output month ikut locale REQUEST (en/id/fr), bukan bahasa input
        month_local = _month_name(locale, month_idx)
        if not month_local:
            return before

        max_day = _days_in_month(year, month_idx)
        if not (1 <= day <= max_day):
            after = _flag_invalid_date(month_local, year)
            if after != before:
                changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "date_invalid_name_nocomma"})
            return after

        after = f"{day} {month_local} {year}"
        if after != before:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "datefmt_name_nocomma"})
        return after

    return _DATE_MONTHNAME_DD_YYYY_NOCOMMA.sub(sub, text), changes

def _date_name_reorder_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Handle pola tanggal yang urutannya salah:
    - Month YEAR DAY      : "January 2015 26"
    - DAY YEAR, Month     : "11 2015, April"
    - DAY YEAR Month      : "11 2015 April"
    - YEAR Month DAY      : "2021 August 17"
    - YEAR DAY, Month     : "2020 19, November"
    - YEAR DAY Month      : "2020 19 November"
    Output jadi: "DD Month YYYY"
    """
    changes = []

    # sets untuk deteksi bahasa month token (agar FR tetap FR, ID tetap ID)
    EN_MONTHS = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    }
    FR_MONTHS = {
        "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
        "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    }
    ID_MONTHS = {
        "januari", "februari", "maret", "april", "mei", "juni",
        "juli", "agustus", "september", "oktober", "november", "desember",
    }

    month_map = _MONTH_MAP_ALL  # sudah ada global

    def pick_locale_from_month(month_lc: str) -> str:
        if month_lc in FR_MONTHS:
            return "fr"
        if month_lc in ID_MONTHS:
            return "id"
        if month_lc in EN_MONTHS:
            return "en"
        # fallback: ikut request locale
        return locale

    def day_out(day_s: str) -> str:
        # preserve '01' (jangan jadi '1') untuk locale non-ID
        try:
            d = int(day_s)
        except Exception:
            return day_s
        if len(day_s) == 2 and day_s.startswith("0") and not (locale or "").lower().startswith("id"):
            return day_s
        return str(d)

    # Month token pattern (EN/ID/FR)
    MONTH_ANY = (
        r"January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|"
        r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
    )

    # 1) Month YEAR DAY  -> January 2015 26
    re_month_year_day = re.compile(rf"\b({MONTH_ANY})\s+(\d{{4}})\s+(\d{{1,2}})\b", re.IGNORECASE)

    # 2) DAY YEAR, Month  -> 11 2015, April
    re_day_year_month_comma = re.compile(rf"\b(\d{{1,2}})\s+(\d{{4}})\s*,\s*({MONTH_ANY})\b", re.IGNORECASE)

    # 3) DAY YEAR Month -> 11 2015 April
    re_day_year_month = re.compile(rf"\b(\d{{1,2}})\s+(\d{{4}})\s+({MONTH_ANY})\b", re.IGNORECASE)

    # 4) YEAR Month DAY -> 2021 August 17
    re_year_month_day = re.compile(rf"\b(\d{{4}})\s+({MONTH_ANY})\s+(\d{{1,2}})\b", re.IGNORECASE)

    # 5) YEAR DAY, Month -> 2020 19, November
    re_year_day_month_comma = re.compile(rf"\b(\d{{4}})\s+(\d{{1,2}})\s*,\s*({MONTH_ANY})\b", re.IGNORECASE)

    # 6) YEAR DAY Month -> 2020 19 November
    re_year_day_month = re.compile(rf"\b(\d{{4}})\s+(\d{{1,2}})\s+({MONTH_ANY})\b", re.IGNORECASE)

    def repl(d_s: str, mon_raw: str, y_s: str, m: re.Match) -> str:
        before = m.group(0)
        mon_lc = (mon_raw or "").lower()
        mon_idx = month_map.get(mon_lc)
        if not mon_idx:
            return before

        eff = pick_locale_from_month(mon_lc)
        mon_local = _month_name(eff, mon_idx)
        if not mon_local:
            return before

        # validasi day in month
        try:
            y = int(y_s)
            d = int(d_s)
        except Exception:
            return before
        max_day = _days_in_month(y, mon_idx)
        if not (1 <= d <= max_day):
            # flag invalid (pakai bahasa month yg dipilih)
            after = _flag_invalid_date(mon_local, y)
        else:
            after = f"{day_out(d_s)} {mon_local} {y_s}"

        if after != before:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "datefmt_reorder"})
        return after

    def sub_month_year_day(m):   return repl(m.group(3), m.group(1), m.group(2), m)
    def sub_day_year_month_c(m): return repl(m.group(1), m.group(3), m.group(2), m)
    def sub_day_year_month(m):   return repl(m.group(1), m.group(3), m.group(2), m)
    def sub_year_month_day(m):   return repl(m.group(3), m.group(2), m.group(1), m)
    def sub_year_day_month_c(m): return repl(m.group(2), m.group(3), m.group(1), m)
    def sub_year_day_month(m):   return repl(m.group(2), m.group(3), m.group(1), m)

    out = text
    out = re_month_year_day.sub(sub_month_year_day, out)
    out = re_day_year_month_comma.sub(sub_day_year_month_c, out)
    out = re_day_year_month.sub(sub_day_year_month, out)
    out = re_year_month_day.sub(sub_year_month_day, out)
    out = re_year_day_month_comma.sub(sub_year_day_month_c, out)
    out = re_year_day_month.sub(sub_year_day_month, out)

    return out, changes

def _monthyear_reformat_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Standardize month-year expressions (no day):
      - "January 2022" / "January, 2022"  -> "January 2022" (localized month)
      - "2022 January" / "2022, January"  -> "January 2022" (localized month)
    Output month name follows request locale via _month_name(locale, idx).
    """
    changes = []
    out = text

    # 1) Year-first -> Month Year
    def sub_year_first(m: re.Match) -> str:
        before = m.group(0)
        year_s = m.group(1)
        mon_raw = m.group(2)

        parsed = _parse_monthyear(mon_raw, year_s)
        if not parsed:
            return before
        y, mi = parsed
        mon_local = _month_name(locale, mi)
        if not mon_local:
            return before

        after = f"{mon_local} {year_s}"
        if after != before:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "monthyear_yearfirst"})
        return after

    out = _MONTHYEAR_YEAR_FIRST.sub(sub_year_first, out)

    # 2) Month-first -> ensure localized month + keep "Month YYYY"
    # Guard: jangan sentuh kalau sebenarnya full date "Month DD YYYY" (sudah ditangani pass lain)
    def sub_month_first(m: re.Match) -> str:
        before = m.group(0)

        # kalau setelah month ada day (contoh "January 26 2022") -> skip
        # (biarkan pass full-date yang handle)
        tail = text[m.end():m.end()+10]
        if re.match(r"\s+\d{1,2}\b", tail):
            return before

        mon_raw = m.group(1)
        year_s = m.group(2)

        parsed = _parse_monthyear(mon_raw, year_s)
        if not parsed:
            return before
        _y, mi = parsed
        mon_local = _month_name(locale, mi)
        if not mon_local:
            return before

        after = f"{mon_local} {year_s}"
        if after != before:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "monthyear_monthfirst"})
        return after

    out = _MONTHYEAR_MONTH_FIRST.sub(sub_month_first, out)

    return out, changes

def _date_reformat_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Ubah '27/04/2025' atau '27-04-2025' menjadi:
      - locale 'id'  → '27 April 2025'
      - locale 'fr'  → '27 Avril 2025'
      - lainnya      → '27 April 2025' (English)
    Asumsi: pola dd/mm/yyyy (bukan mm/dd).
    """
    changes = []

    def sub(m: re.Match) -> str:
        before = m.group(0)
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))

        # validasi sederhana range tanggal
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return before

        month_name = _month_name(locale, month)
        if not month_name:
            return before

        after = f"{day} {month_name} {year}"
        if after != before:
            changes.append({
                "from": before,
                "to": after,
                "span": [m.start(), m.end()],
                "via": "datefmt",
            })
        return after

    new_text = _DATE_DDMMYYYY.sub(sub, text)
    return new_text, changes

def _is_leap_year(year: int) -> bool:
    return (year % 4 == 0) and ((year % 100 != 0) or (year % 400 == 0))

def _days_in_month(year: int, month: int) -> int:
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if month in (4, 6, 9, 11):
        return 30
    if month == 2:
        return 29 if _is_leap_year(year) else 28
    return 0

def _render_day_preserve_zero(day_s: str) -> str:
    """
    Preserve leading zero if user already typed it (e.g., '01' stays '01').
    Otherwise render as integer string (e.g., '1' stays '1').
    """
    try:
        d = int(day_s)
    except Exception:
        return day_s

    if len(day_s) == 2 and day_s.startswith("0"):
        return day_s
    return str(d)

def _flag_invalid_date(month_local: str, year: int) -> str:
    # format sesuai requirement kamu: bracket sebelum Month Year
    return f"[PLEASE REVIEW] {month_local} {year}"

def _date_range_order_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Deteksi "from <date1> until/to <date2>" (EN/ID/FR connectors) setelah tanggal distandardisasi.
    Jika date1 > date2 → swap urutan.
    """
    changes = []

    def sub(m: re.Match) -> str:
        before = m.group(0)

        # group layout:
        # from <d1> <m1> <y1>  to/until <d2> <m2> <y2>
        d1, mon1, y1 = m.group(1), m.group(2), m.group(3)
        d2, mon2, y2 = m.group(4), m.group(5), m.group(6)

        t1 = _parse_std_date(d1, mon1, y1)
        t2 = _parse_std_date(d2, mon2, y2)

        # kalau salah satu tidak bisa diparse (atau invalid) → jangan swap
        if not t1 or not t2:
            return before

        if t1 <= t2:
            return before

        # swap: tetap pakai month token yang sudah ada di text (sudah dinormalisasi oleh pass sebelumnya)
        # rebuild dengan bagian connector original supaya tidak mengubah wording.
        # Kita ambil "from" dan connector tengah dari match dengan slicing:
        # pattern match memuat FROM + date1 + TO + date2, jadi cara aman:
        # - cari posisi date1 dan date2 berdasarkan groups.
        # We'll rebuild menggunakan regex groups dan replace manual.

        # Kita reconstruct minimal:
        # "from <date2> <connector> <date1>"
        # Ambil kata FROM dan kata connector (to/until/hingga/au/à/...) dari original:
        # Trick: ambil substring di antara date1 dan date2 sebagai mid connector.
        full = before

        # Cari string date1 dan date2 yang persis seperti di input matched (preserve casing/spaces)
        date1_str = f"{m.group(1)} {m.group(2)} {m.group(3)}"
        date2_str = f"{m.group(4)} {m.group(5)} {m.group(6)}"

        # Ambil prefix "from ... " sampai sebelum date1
        # paling aman: split sekali
        try:
            left, rest = full.split(date1_str, 1)
            mid, _right = rest.split(date2_str, 1)  # mid berisi " <connector> "
        except ValueError:
            return before

        after = f"{left}{date2_str}{mid}{date1_str}"

        if after != before:
            changes.append({
                "from": before,
                "to": after,
                "span": [m.start(), m.end()],
                "via": "date_range_swap",
            })
        return after

    return _DATE_RANGE_RE.sub(sub, text), changes

def _monthyear_range_order_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Detect "from <Month YYYY> to/until <Month YYYY>" and swap if left > right.
    Example:
      "from January 2022 to March 2015" -> "from March 2015 to January 2022"
    Assumes month names already normalized via _monthyear_reformat_pass.
    """
    changes = []

    def sub(m: re.Match) -> str:
        before = m.group(0)

        mon1, y1 = m.group(1), m.group(2)
        mon2, y2 = m.group(3), m.group(4)

        t1 = _parse_monthyear(mon1, y1)
        t2 = _parse_monthyear(mon2, y2)
        if not t1 or not t2:
            return before

        if t1 <= t2:
            return before

        # rebuild: keep the exact connector words from original by slicing
        # We reuse matched pieces to minimize wording changes.
        left = f"{m.group(1)} {m.group(2)}"
        right = f"{m.group(3)} {m.group(4)}"

        try:
            a, rest = before.split(left, 1)
            mid, _ = rest.split(right, 1)
        except ValueError:
            return before

        after = f"{a}{right}{mid}{left}"

        if after != before:
            changes.append({"from": before, "to": after, "span": [m.start(), m.end()], "via": "monthyear_range_swap"})
        return after

    return _MONTHYEAR_RANGE_RE.sub(sub, text), changes

# --- PASS X: Zero pad single-digit day for Indonesian locale ---

# Reuse month list yang sudah ada (EN/ID/FR)
_MONTHS_ANY = (
    r"January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|"
    r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
)

# Match tanggal yang sudah distandardisasi jadi: "3 Maret 2025", "4 December 2025", dst
# (tidak match "[PLEASE REVIEW] March 2025" karena tidak ada day di depan)
_DATE_STD_DAYFIRST_RE = re.compile(
    rf"\b([1-9])\s+({_MONTHS_ANY})\s+(\d{{4}})\b"
)

def _zero_pad_day_pass(text: str, locale: str) -> tuple[str, list]:
    """
    Untuk locale Indonesia (semua): ubah "3 Maret 2025" -> "03 Maret 2025".
    Dilakukan setelah semua standardisasi tanggal & range-swap.
    """
    changes = []

    # # hanya untuk Indonesia
    # if not (locale or "").lower().startswith("id"):
    #     return text, changes

    def sub(m: re.Match) -> str:
        before = m.group(0)
        day = int(m.group(1))
        month = m.group(2)
        year = m.group(3)

        after = f"{day:02d} {month} {year}"
        if after != before:
            changes.append({
                "from": before,
                "to": after,
                "span": [m.start(), m.end()],
                "via": "date_zero_pad",
            })
        return after

    return _DATE_STD_DAYFIRST_RE.sub(sub, text), changes

def apply_reformatting(text: str, locale: str, tenant: str = "") -> Tuple[str, Dict]:
    region_primary = locale_to_region(locale)
    changes = []
    out = text

    # --- PASS 0: tangani semua '+CC...' dulu, TANPA tergantung phonenumbers ---
    out, ch0 = _intl_plus_pass(out)
    if ch0: changes.extend(ch0)

    # --- PASS 0.4: protect tenant-specific ID BEFORE phone formatting ---
    protected_all: list[_ProtectedSpan] = []

    # Thailand: protect number part after "ID Card Number:"
    out, protected_th = _protect_th_idcard_numbers(out, tenant)
    protected_all.extend(protected_th)

    # Thailand: protect Buddhist year pairs like "2543 (2000)" on ID date lines
    out, protected_th_dates = _protect_th_buddhist_year_pairs(out, tenant)
    protected_all.extend(protected_th_dates)

    out, protected_th_addr = _protect_th_registered_address(out, tenant)
    protected_all.extend(protected_th_addr)

    # Malaysia: (optional) normalize dulu kalau ada spasi/dash di dalam kurung
    out = _normalize_my_identity_card_in_paren(out, tenant, changes)

    # Malaysia: protect NRIC inside "Identity Card number ( ... )"
    out, protected_my = _protect_my_nric_in_paren(out, tenant)
    protected_all.extend(protected_my)

    # --- PASS 0.5: tangani "CC ...." dengan spasi (tanpa '+') ---
    out, ch0_5 = _intl_plain_with_spaces_pass(out)
    if ch0_5: changes.extend(ch0_5)

    # --- PASS 1: deteksi global numeric tokens 7–13 digits ---
    pattern = re.compile(r"\b\d{7,13}\b")
    parts = []
    last = 0

    for m in pattern.finditer(out):
        st, en = m.start(), m.end()
        raw_tok = out[st:en]

        # Guard tambahan: skip token digit panjang (kalau suatu hari pattern berubah)
        if len(raw_tok) >= 15:
            parts.append(out[last:st])
            parts.append(raw_tok)
            last = en
            continue

        fmt, changed = _format_phone_token(raw_tok, locale)

        parts.append(out[last:st])
        parts.append(fmt)
        last = en

    parts.append(out[last:])
    out = "".join(parts)

    # --- PASS 2: fallback regex Indonesia (021..., 08...) ---
    out2, regex_changes = _fallback_regex_pass(out)
    if regex_changes:
        changes.extend(regex_changes)

    # --- Unfreeze semua '+' yang dibekukan ---
    out2 = _unfreeze_plus(out2)

    # --- Normalisasi defensif: buang pola "(+(+CC)" -> "(+CC)" ---
    out2 = re.sub(r'\(\+\(\+(\d{1,3})\)', r'(+\1)', out2)

    # --- Normalisasi defensif: buang pola "((+CC)" -> "(+CC)" ---
    out2 = re.sub(r'\(\(\+(\d{1,3})\)', r'(+\1)', out2)

    # --- Restore protected tenant ID spans (so phone formatter can't touch them) ---
    if protected_all:
        out2 = _restore_spans(out2, protected_all)

    # --- PASS 3a: Month-name-first dengan koma ("March 28, 2020") ---
    out2a, name_changes = _date_name_reformat_pass(out2, locale)
    if name_changes:
        changes.extend(name_changes)

    # --- PASS 3a1: Month-name-first tanpa koma ("March 28 2020") ---
    out2a1, nocomma_changes = _date_name_nocomma_pass(out2a, locale)
    if nocomma_changes:
        changes.extend(nocomma_changes)

    # --- PASS 3a2: Day-first month-name ("28 March 2020") ---
    out2b, dayname_changes = _date_day_monthname_pass(out2a1, locale)
    if dayname_changes:
        changes.extend(dayname_changes)

    # --- PASS 3b: numeric ("27/04/2025" / "27-04-2025") ---
    out3, date_changes = _date_reformat_pass(out2b, locale)
    if date_changes:
        changes.extend(date_changes)

    # --- PASS 3c: reorder month/year/day patterns ("January 2015 26", "2021 August 17", dst) ---
    out3c, reorder_changes = _date_name_reorder_pass(out3, locale)
    if reorder_changes:
        changes.extend(reorder_changes)

    # --- PASS 3d (NEW): normalize Month-Year only (no day) ---
    out3d, my_changes = _monthyear_reformat_pass(out3c, locale)
    if my_changes:
        changes.extend(my_changes)

    # --- PASS 4b: zero pad day ("3 Maret 2025" -> "03 Maret 2025") untuk locale id ---
    out4b, pad_changes = _zero_pad_day_pass(out3d, locale)
    if pad_changes:
        changes.extend(pad_changes)

    # --- PASS 4 (NEW): swap Month-Year ranges (no day) ---
    out4my, myrange_changes = _monthyear_range_order_pass(out4b, locale)
    if myrange_changes:
        changes.extend(myrange_changes)

    # --- PASS 4: order employment date range ("from X until Y") ---
    out4, range_changes = _date_range_order_pass(out4my, locale)
    if range_changes:
        changes.extend(range_changes)

    # --- PASS 5: honorific capitalization ---
    out5, honor_changes = _honorific_capitalization_pass(out4, locale)
    if honor_changes:
        changes.extend(honor_changes)

    meta = {
        "locale": locale,
        "region": region_primary,
        "changed_count": len(changes),
        "changes": changes
    }
    out_final = out5
    return out_final, meta