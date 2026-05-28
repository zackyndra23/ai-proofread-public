import re
from typing import Dict, List, Tuple

# --- PIIRegex (email/credit card) ---
from piiregex import PiiRegex

# --- Phone utils (untuk /reformating dan masking lib) ---
from phonenumbers import (
    PhoneNumberMatcher,
    parse as pn_parse,
    is_possible_number,
    format_number,
    PhoneNumberFormat,
    NumberParseException,
)

# =========================
# Helpers umum
# =========================
def _find_token_spans(text: str) -> List[Tuple[int, int]]:
    # Token bracket: [EMAIL_0], [PHONE_NUMBER_0], [PERSON_1], dst.
    return [m.span() for m in re.finditer(r"\[[A-Z0-9_]+\]", text)]

def _overlaps(start: int, end: int, spans: List[Tuple[int, int]]) -> bool:
    return any(start < e and end > s for s, e in spans)

# =========================
# LAYER-1: Masking via PiiRegex (EMAIL + CREDIT_CARD SAJA)
# =========================
def mask_with_piiregex(text: str, counters: Dict[str, int] | None = None) -> Tuple[str, List[Dict]]:
    """
    EMAIL -> [EMAIL_i], CREDIT_CARD -> [CREDIT_CARD_i]
    (Telepon JANGAN di sini; pakai mask_with_phones_lib di layer-2)
    """
    if counters is None:
        counters = {}

    parser = PiiRegex()
    result = text
    spans = _find_token_spans(result)
    layers: List[Dict] = []

    layers_map: Dict[str, Dict[str, str]] = {
        "pii_EMAIL": {},
        "pii_CREDIT_CARD": {},
    }

    def _mask_list(items, category_key: str, cat_label: str):
        nonlocal result, spans
        for itm in items:
            # cari semua kemunculan itm di 'result'
            for m in re.finditer(re.escape(itm), result):
                st, en = m.span()
                if _overlaps(st, en, spans):
                    continue
                # gunakan counters bersama lintas-layer
                idx = counters.get(cat_label, 0)         # cat_label = "EMAIL"/"CREDIT_CARD"
                token = f"[{cat_label}_{idx}]"
                counters[cat_label] = idx + 1

                layers_map[category_key][token] = itm
                result = result[:st] + token + result[en:]
                spans.append((st, st + len(token)))
                break  # sekali ganti per item (hindari double replace)

    # 1) Email
    emails = parser.emails(result)
    _mask_list(emails, "pii_EMAIL", "EMAIL")

    # 2) Credit cards
    cards = parser.credit_cards(result)
    _mask_list(cards, "pii_CREDIT_CARD", "CREDIT_CARD")

    # bungkus output per-layer
    for k, v in layers_map.items():
        if v:
            layers.append({"type": k, "map": v})

    return result, layers

# =========================
# Fallback: generic numeric phone masking (panjang digit)
# =========================
PHONE_GENERIC_RE = re.compile(r"\+?\d[\d\-\s]{5,20}")  # cukup longgar, difilter lagi pakai len digit


def _mask_generic_numeric_phones(
    text: str,
    existing_token_spans: List[Tuple[int, int]],
    counters: Dict[str, int],
) -> Tuple[str, Dict[str, str]]:
    """
    Fallback kalau libphonenumber tidak menganggap nomor tsb 'possible'.
    Aturan:
      - tanpa '+'  ->  6–12 digit
      - dengan '+' ->  7–13 digit (digit setelah '+')
    Tetap hindari overlap dengan token [XXX_i] yang sudah ada.
    """
    candidates: List[Tuple[int, int, str]] = []

    for m in PHONE_GENERIC_RE.finditer(text):
        st, en = m.span()
        if _overlaps(st, en, existing_token_spans):
            continue

        raw = m.group(0)
        raw_stripped = raw.strip()
        has_plus = raw_stripped.startswith("+")
        digits_only = re.sub(r"\D", "", raw_stripped)  # buang spasi, '-', dll
        nd = len(digits_only)

        # Filter panjang digit
        if has_plus:
            if not (7 <= nd <= 13):
                continue
        else:
            if not (6 <= nd <= 13):
                continue

        candidates.append((st, en, raw))

    if not candidates:
        return text, {}

    # Resolusi konflik: sort by start, prefer yang lebih panjang di start sama
    candidates.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    selected: List[Tuple[int, int, str]] = []
    cur_end = -1
    for st, en, raw in candidates:
        if st < cur_end:
            continue
        selected.append((st, en, raw))
        cur_end = en

    # Replace kiri -> kanan
    parts: List[str] = []
    last = 0
    mp: Dict[str, str] = {}

    for st, en, raw in selected:
        parts.append(text[last:st])
        idx = counters.get("PHONE_NUMBER", 0)
        token = f"[PHONE_NUMBER_{idx}]"
        counters["PHONE_NUMBER"] = idx + 1

        mp[token] = raw
        parts.append(token)
        last = en

    parts.append(text[last:])
    masked = "".join(parts)
    return masked, mp

# =========================
# LAYER-2: Masking nomor telepon (libphonenumber) — UTUH
# =========================
# def mask_with_phones_lib(text: str, region: str, counters: Dict[str, int] | None = None) -> Tuple[str, List[Dict]]:
#     """
#     Tangkap nomor telepon secara utuh (prefix +62/0/62, spasi/strip/kurung).
#     Penomoran token lanjut lintas-layer via `counters["PHONE_NUMBER"]`.
#     """
#     if counters is None:
#         counters = {}

#     result = text
#     spans = _find_token_spans(result)
#     mp: Dict[str, str] = {}
#     parts, last = [], 0

#     # 1) Kumpulkan semua match dari libphonenumber
#     raw_matches = [(m.start, m.end) for m in PhoneNumberMatcher(result, region)]
#     if not raw_matches:
#         return result, []

#     # 2) Perluas ke kiri/kanan untuk menyertakan '(' dan/atau ')'
#     n = len(result)
#     expanded = []
#     for st, en in raw_matches:
#         # include '(' di kiri jika ada
#         if st - 1 >= 0 and result[st - 1] == "(":
#             st -= 1
#         # include ')' di kanan jika ada
#         if en < n and result[en] == ")":
#             en += 1
#         expanded.append((st, en))

#     # 3) Resolusi konflik: sort by start, prefer yang lebih panjang di start sama
#     expanded.sort(key=lambda x: (x[0], -(x[1] - x[0])))
#     selected = []
#     cur_end = -1
#     for st, en in expanded:
#         if st < cur_end:
#             continue
#         selected.append((st, en))
#         cur_end = en

#     # 4) Replace kiri -> kanan, cek overlap dgn token yang sudah ada
#     for st, en in selected:
#         if _overlaps(st, en, spans):
#             continue

#         raw = result[st:en]
#         try:
#             parsed = pn_parse(raw, region)
#             if not is_possible_number(parsed):
#                 continue
#         except NumberParseException:
#             continue

#         # gunakan counters lintas-layer
#         idx = counters.get("PHONE_NUMBER", 0)
#         token = f"[PHONE_NUMBER_{idx}]"
#         counters["PHONE_NUMBER"] = idx + 1

#         mp[token] = raw
#         parts += [result[last:st], token]
#         spans.append((st, st + len(token)))
#         last = en

#     parts.append(result[last:])
#     masked = "".join(parts)
#     return masked, ([{"type": "phones_lib", "map": mp}] if mp else [])

def mask_with_phones_lib(
    text: str, 
    region: str, 
    counters: Dict[str, int] | None = None
) -> Tuple[str, List[Dict]]:
    """
    Tangkap nomor telepon secara utuh (prefix +62/0/62, spasi/strip/kurung).
    Penomoran token lanjut lintas-layer via `counters["PHONE_NUMBER"]`.

    Step:
      1) libphonenumber (PhoneNumberMatcher + is_possible_number)
      2) Fallback length-based:
         - 6–12 digit (tanpa '+')
         - 7–13 digit setelah '+'
    """
    if counters is None:
        counters = {}

    result = text
    spans = _find_token_spans(result)
    mp: Dict[str, str] = {}
    parts, last = [], 0

    # 1) Kumpulkan semua match dari libphonenumber
    raw_matches = [(m.start, m.end) for m in PhoneNumberMatcher(result, region)]
    if raw_matches:
        # 2) Perluas ke kiri/kanan untuk menyertakan '(' dan/atau ')'
        n = len(result)
        expanded = []
        for st, en in raw_matches:
            # include '(' di kiri jika ada
            if st - 1 >= 0 and result[st - 1] == "(":
                st -= 1
            # include ')' di kanan jika ada
            if en < n and result[en] == ")":
                en += 1
            expanded.append((st, en))

        # 3) Resolusi konflik: sort by start, prefer yang lebih panjang di start sama
        expanded.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        selected = []
        cur_end = -1
        for st, en in expanded:
            if st < cur_end:
                continue
            selected.append((st, en))
            cur_end = en

        # 4) Replace kiri -> kanan, cek overlap dgn token yang sudah ada
        for st, en in selected:
            if _overlaps(st, en, spans):
                continue

            raw = result[st:en]
            parsed_ok = False
            try:
                parsed = pn_parse(raw, region)
                if is_possible_number(parsed):
                    parsed_ok = True
            except NumberParseException:
                parsed_ok = False

            # Kalau libphonenumber bilang "tidak possible", biarkan fallback regex yang handle
            if not parsed_ok:
                continue

            # gunakan counters lintas-layer
            idx = counters.get("PHONE_NUMBER", 0)
            token = f"[PHONE_NUMBER_{idx}]"
            counters["PHONE_NUMBER"] = idx + 1

            mp[token] = raw
            parts += [result[last:st], token]
            # update span token baru
            spans.append((st, st + len(token)))
            last = en

        parts.append(result[last:])
        result = "".join(parts)

    # 5) Fallback: tangkap numeric phones berdasarkan panjang digit
    #    (6–12 digit, atau + + 7–13 digit), hindari overlap dgn token yang sudah ada
    spans = _find_token_spans(result)
    result, mp_fallback = _mask_generic_numeric_phones(result, spans, counters)
    mp.update(mp_fallback)

    return result, ([{"type": "phones_lib", "map": mp}] if mp else [])

# =========================
# LAYER-3: Masking via patterns tambahan (termasuk bulan Indonesia & honorifik)
# =========================
def mask_with_patterns(text: str, counters: Dict[str, int] | None = None) -> Tuple[str, List[Dict]]:
    """
    Kumpulkan semua kandidat match, buang overlap (prefer yang terpanjang),
    lalu replace kiri→kanan sekali jalan. Penomoran token pakai `counters` bersama.
    """
    if counters is None:
        counters = {}

    source = text
    token_spans = _find_token_spans(source)  # supaya tidak menyentuh token yang sudah ada

    # Bulan Indonesia (lengkap & singkatan)
    ID_MONTHS     = r"(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)"
    ID_MONTH_ABBR = r"(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)"

    patterns = [
        # Email (fallback)
        (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "EMAIL"),

        # URL
        (r"https?://\S+|www\.\S+", "URL"),

        # Social media account (e.g., @username) — avoid emails
        (r"(?<!\w)@[A-Za-z0-9_](?:[A-Za-z0-9_.-]{1,29})\b", "SOCMED_ACCOUNT"),

        # Hashtag / keyword (e.g., #fraud, #KYC_check)
        (r"(?<!\w)#[A-Za-z0-9_]{1,50}\b", "KEYWORD"),
        # Quoted text (double quotes) → KEYWORD
        (r'"[^"\r\n]{1,200}"', "KEYWORD"),

        # --- DATES (Indonesia) ---
        # "Mei 2018" (bulan + tahun) #test
        (rf"\b{ID_MONTHS}\s+\d{{4}}\b", "DATE"),
        (rf"\b{ID_MONTH_ABBR}\s+\d{{4}}\b", "DATE"),
        # "02 Mei 2018" (hari + bulan + tahun)
        (rf"\b\d{{1,2}}\s+{ID_MONTHS}\s+\d{{4}}\b", "DATE"),
        (rf"\b\d{{1,2}}\s+{ID_MONTH_ABBR}\s+\d{{4}}\b", "DATE"),

        # >>> TAMBAHAN: "30 April" / "06 Mei" (tanpa tahun) <<<
        (rf"\b\d{{1,2}}\s+{ID_MONTHS}\b", "DATE"),
        (rf"\b\d{{1,2}}\s+{ID_MONTH_ABBR}\b", "DATE"),

        # --- DATES (Inggris) ---
        # day-month-year
        (r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b", "DATE"),
        (r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b", "DATE"),
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s+(to|–|-)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}", "DATE"),
        (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s+(to|–|-)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}", "DATE"),
        (r"from\s+\d{4}\s+(to|–|-)\s+\d{4}", "DATE"),

        # >>> TAMBAHAN: day + month (tanpa tahun) & month + day (tanpa tahun) <<<
        (r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b", "DATE"),
        (r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep(?:t)?|Oct|Nov|Dec)\b", "DATE"),
        (r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b", "DATE"),
        (r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep(?:t)?|Oct|Nov|Dec)\s+\d{1,2}\b", "DATE"),

        # Format numerik umum
        (r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "DATE"),

        # --- PERSON (honorifik Indonesia) — HANYA 1 kata sesudahnya ---
        # contoh: Ibu Monica, Bapak Widjaya, Pak Budi, Bu Rina
        (r"\b(?:Ibu|Bapak|Pak|Bu)\s+[A-Z][a-zA-Z]+\b", "PERSON"),

        # --- ORG: PT ... Tbk. (opsional 'PT.' dan '(Persero)') ---
        # contoh: PT BUMA Internasional Grup Tbk.
        (r"\bPT\.?\s+(?:[A-Z][A-Za-z0-9&\.\-/()]*\s+){1,8}(?:\(Persero\)\s+)?Tbk\.?", "ORG"),

        # IDs
        (r"\b\d{16}\b", "NIK"),
        (r"\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}", "NPWP"),

        # IP
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP_ADDRESS"),

        # Address hint
        (r"\b(Jl\.|Jalan)\s\S+", "ADDRESS"),

        # (Fallback) phone Indonesia kalau ada yang lolos L2
        (r"(\+62|62|0)\s?(?:\(?\d{2,4}\)?[\s-]?){2,6}\d{2,4}", "PHONE_NUMBER"),
    ]

    # 1) Kumpulkan semua kandidat match (hindari token yang sudah ada)
    found = []
    for pat, cat in patterns:
        for m in re.finditer(pat, source, re.IGNORECASE):
            st, en = m.span()
            if _overlaps(st, en, token_spans):
                continue
            found.append((st, en, cat, m.group(0)))

    if not found:
        return source, []

    # 2) Resolusi konflik: sort by start; prefer yang TERPANJANG di start sama; pilih non-overlap kiri→kanan
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    selected = []
    last_end = -1
    for st, en, cat, val in found:
        if st < last_end:
            continue
        selected.append((st, en, cat, val))
        last_end = en

    # 3) Replace kiri→kanan — pakai counters BERSAMA (bukan counters lokal)
    layers_map: Dict[str, Dict[str, str]] = {}
    parts, last = [], 0
    for st, en, cat, val in selected:
        parts.append(source[last:st])
        idx = counters.get(cat, 0)
        token = f"[{cat}_{idx}]"
        counters[cat] = idx + 1
        layers_map.setdefault(cat, {})[token] = val
        parts.append(token)
        last = en
    parts.append(source[last:])
    result = "".join(parts)

    # 4) Bungkus per-kategori → per-layer
    layers: List[Dict] = []
    for cat, mp in layers_map.items():
        if mp:
            layers.append({"type": f"regex_{cat}", "map": mp})

    return result, layers

# =========================
# (Tetap ada) Fallback legacy + UNMASK + normalisasi
# =========================

RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

def mask_emails(text: str, start_idx=1) -> Tuple[str, Dict[str, str], int]:
    mapping, idx = {}, start_idx
    def repl(m):
        nonlocal idx
        token = f"{{{{EMAIL_{idx}}}}}"
        mapping[token] = m.group(0)
        idx += 1
        return token
    return RE_EMAIL.sub(repl, text), mapping, idx

def mask_phones(text: str, region: str, start_idx=1) -> Tuple[str, Dict[str, str], int]:
    mapping, idx, out, last = {}, start_idx, [], 0
    for match in PhoneNumberMatcher(text, region):
        raw = text[match.start:match.end]
        try:
            parsed = pn_parse(raw, region)
            if is_possible_number(parsed):
                token = f"{{{{PHONE_{idx}}}}}"
                mapping[token] = raw
                out += [text[last:match.start], token]
                last, idx = match.end, idx + 1
        except NumberParseException:
            pass
    out.append(text[last:])
    return "".join(out), mapping, idx

def apply_mapping_reverse(text: str, mapping: Dict[str, str]) -> str:
    for token in sorted(mapping.keys(), key=len, reverse=True):
        text = text.replace(token, mapping[token])
    return text

def unmask_text_layers(text: str, layers: List[Dict]) -> str:
    for layer in reversed(layers):
        text = apply_mapping_reverse(text, layer["map"])
    return text

def normalize_phone_numbers(text: str, region: str, e164: bool = True) -> str:
    fmt = PhoneNumberFormat.E164 if e164 else PhoneNumberFormat.NATIONAL
    parts, last = [], 0
    for match in PhoneNumberMatcher(text, region):
        raw = text[match.start:match.end]
        try:
            parsed = pn_parse(raw, region)
            if is_possible_number(parsed):
                parts += [text[last:match.start], format_number(parsed, fmt)]
                last = match.end
        except NumberParseException:
            pass
    parts.append(text[last:])
    return "".join(parts)

_TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")

def unmask_text(masked_text: str, mapping: Dict[str, str]) -> str:
    """
    Ganti semua token [TYPE_i] dengan nilai dari mapping.
    Token yang tidak ada di mapping dibiarkan apa adanya.
    """
    def _repl(m):
        tok = m.group(0)
        return mapping.get(tok, tok)
    return _TOKEN_RE.sub(_repl, masked_text)

def flatten_layered_maps(layered_maps: Dict[str, Dict[str, str]] | None) -> Dict[str, str]:
    """
    Gabungkan semua map per-layer menjadi satu dictionary token->asli.
    """
    out: Dict[str, str] = {}
    if not isinstance(layered_maps, dict):
        return out
    for mp in layered_maps.values():
        if isinstance(mp, dict):
            out.update(mp)
    return out
