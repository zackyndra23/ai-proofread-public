from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple, Optional

# Honorifics Indonesian yang sering jadi subject manusia
# _ID_TITLES = (
#     "Ibu", "Bapak", "Tuan", "Nyonya", "Saudara", "Saudari"
# )
_ID_TITLES = (
    "Ibu", "Bapak"
)

# Nama saja sebagai subject di awal kalimat pertama paragraf
_NAME_ONLY_SENTENCE_START_RE = re.compile(
    r'^\s*([A-Z][a-z]+)\s+('
    r'menyatakan|menjelaskan|mengatakan|menambahkan|menerangkan|menuturkan|tidak|'
    r'membantu|bertemu|menemui|melihat|mengonfirmasi|mengkonfirmasi|menginformasikan'
    r')\b'
)

# Pola subject: "Ibu Nina", "Bapak Fajrul", dst (nama minimal 1 kata)
_SUBJECT_RE = re.compile(
    r'\b(' + '|'.join(_ID_TITLES) + r')\s+([A-Z][\w\-\']+(?:\s+[A-Z][\w\-\']+)*)\b'
)

_NAME_ONLY_RE = re.compile(r'\b([A-Z][a-z]+)\b')

# Split paragraf: blank line
_PARA_SPLIT_RE = re.compile(r'\n\s*\n+', re.MULTILINE)

# Split kalimat sederhana: pertahankan delimiter .!? dan spasi setelahnya
_SENT_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')

# Deteksi kalimat "tanpa subject eksplisit" (heuristic):
# - diawali huruf kecil (menyatakan/menambahkan/tidak/berkata/dst)
# - tidak diawali angka, tanda kurung, token, atau huruf kapital
_NO_SUBJECT_START_RE = re.compile(r'^[a-z]', re.UNICODE)

# Sudah ada pronoun di awal
_PRONOUN_START_RE = re.compile(r'^(Beliau|Ia|Dia)\b')

_NAME_STOPWORDS = {
    "Percobaan", "Trial", "Based", "Kemudian", "Selanjutnya", "Pada", "Dan", "Yang",
    "Indonesia", "Jakarta", "Subjek"
}

def _pick_dominant_name_only(para: str) -> str | None:
    # Ambil semua kata kapital sederhana (Name-like)
    candidates = _NAME_ONLY_RE.findall(para)
    if not candidates:
        return None

    # Filter stopword dan title (Ibu/Bapak/... bukan name-only)
    filtered = [c for c in candidates if c not in _NAME_STOPWORDS and c not in _ID_TITLES]
    if not filtered:
        return None

    # Hitung frekuensi
    freq = {}
    for c in filtered:
        freq[c] = freq.get(c, 0) + 1

    # Ambil yang paling sering
    best, best_n = None, 0
    for k, v in freq.items():
        if v > best_n:
            best, best_n = k, v

    # Konservatif: harus muncul minimal 2x agar yakin ini subject yang sama
    if best_n >= 2:
        return best
    return None

def _choose_pronoun(title: str | None) -> str:
    """
    Pronoun selection (formal report standard):
    - Ibu/Bapak/Tuan/Nyonya -> Beliau
    - Saudara/Saudari -> Ia
    - No title (name only) -> Dia
    """
    if not title:
        return "Ia"

    # if title in ("Ibu", "Bapak", "Tuan", "Nyonya"):
    #     return "Beliau"
    if title in ("Ibu", "Bapak"):
        return "Beliau"

    if title in ("Saudara", "Saudari"):
        return "Ia"

    return "Ia"

def apply_subjectfmt(text: str, locale: str, type_of_check: str, max_follow_sentences: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Apply subject continuity + subject completion untuk Bahasa Indonesia.
    Returns: (new_text, meta)
      meta = {"applied": bool, "changes": [...]}  (changes log ringan untuk audit)
    """
    meta: Dict[str, Any] = {"applied": False, "changes": []}

    # if not (locale or "").lower().startswith("id"):
    #     return text, meta
    if not (
        (locale or "").lower().startswith("id")
        and (type_of_check or "").lower() == "reference-check"
    ):
        meta["applied"] = False
        meta["skipped"] = True
        meta["reason"] = "subjectfmt_only_for_id_reference_check"
        return text, meta

    if not text or not text.strip():
        return text, meta

    paragraphs = _PARA_SPLIT_RE.split(text)
    out_paras: List[str] = []
    any_change = False

    for para in paragraphs:
        original_para = para
        # Skip paragraf yang banyak token bracket di awal (konservatif)
        # (Kalau kamu mau tetap jalan saat ada token, bisa longgarkan.)
        stripped = para.strip()
        if not stripped:
            out_paras.append(para)
            continue

        # Cari semua subject kandidat di paragraf
        subjects = list(_SUBJECT_RE.finditer(para))
        subject_strings = []

        for m in subjects:
            subj = f"{m.group(1)} {m.group(2)}"
            subject_strings.append(subj)

        # Fallback: nama saja di awal paragraf (hanya jika tidak ada subject bertitle)
        if not subject_strings:
            sent0_candidates = _SENT_SPLIT_RE.split(para)
            first_content = None
            for s0 in sent0_candidates:
                s0s = s0.strip()
                # skip header seperti "Percobaan 03:"
                if re.match(r'^(Percobaan|Trial)\s+\d+\s*:\s*$', s0s, re.IGNORECASE):
                    continue
                if s0s:
                    first_content = s0s
                    break

            if first_content:
                m_name = _NAME_ONLY_SENTENCE_START_RE.match(first_content)
                if m_name:
                    subject_strings.append(m_name.group(1))

        # Fallback #0b: name-only di awal paragraf, TANPA bergantung daftar kata kerja
        # Contoh: "Juwita Shafira membantu ..." -> ambil "Juwita Shafira" (cukup 1x)
        if not subject_strings and first_content:
            m0 = re.match(r'^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b', first_content)
            if m0:
                candidate = m0.group(1).strip()
                # skip header & stopwords & title
                if candidate not in _NAME_STOPWORDS and candidate not in _ID_TITLES:
                    subject_strings.append(candidate)

        # Fallback #2: nama dominan di paragraf (mis. "Chika" muncul berulang)
        if not subject_strings:
            dominant = _pick_dominant_name_only(para)
            if dominant:
                subject_strings.append(dominant)  # subject = "Chika" (name-only)

        uniq_subjects = list(dict.fromkeys(subject_strings))

        if len(uniq_subjects) != 1:
            # Heuristic: kalau ada name-only dominan (mis. "Chika" muncul >=3x),
            # gunakan itu sebagai subject utama, abaikan title lain yang cuma disebut sekali (mis. "Nyonya Menir").
            dominant = _pick_dominant_name_only(para)
            if dominant:
                subject = dominant
                title = None
                pronoun = _choose_pronoun(title)
            else:
                out_paras.append(para)
                continue
        else:
            subject = uniq_subjects[0]
            title = None
            for t in _ID_TITLES:
                if subject.startswith(t + " "):
                    title = t
                    break
            pronoun = _choose_pronoun(title)

        # Split kalimat
        sentences = _SENT_SPLIT_RE.split(para)
        if len(sentences) <= 1:
            out_paras.append(para)
            continue

        # Kalimat pertama: keep subject full (jangan diubah)
        new_sentences = [sentences[0]]

        # Untuk max 3 kalimat berikutnya: replace repetisi subject / isi subject hilang
        for i in range(1, len(sentences)):
            s = sentences[i]

            # Batasi hanya sampai N kalimat setelah first mention
            if (max_follow_sentences is None) or (i <= max_follow_sentences):
                s_stripped = s.lstrip()

                # 1) Jika kalimat diawali subject yang sama → ganti jadi pronoun
                #    contoh: "Ibu Nina menyampaikan..." -> "Beliau menyampaikan..."
                if s_stripped.startswith(subject):
                    replaced = s.replace(subject, pronoun, 1)
                    if replaced != s:
                        meta["changes"].append({
                            "via": "subject_repeat_to_pronoun",
                            "from": s,
                            "to": replaced,
                        })
                        s = replaced
                        any_change = True

                else:
                    # 2) Jika kalimat tidak punya subject (heuristic) dan belum ada pronoun → prefix pronoun
                    #    contoh: "menyatakan bahwa..." -> "Beliau menyatakan bahwa..."
                    #    Juga cover "tidak mengetahui..." -> "Beliau tidak mengetahui..."
                    if _NO_SUBJECT_START_RE.match(s_stripped) and not _PRONOUN_START_RE.match(s_stripped):
                        # Hindari kalau diawali token bracket atau angka/punct tertentu
                        if not s_stripped.startswith("[") and not s_stripped[0].isdigit() and s_stripped[0] not in ("(", '"', "'"):
                            prefixed = pronoun + " " + s_stripped
                            replaced = s[: len(s) - len(s_stripped)] + prefixed  # preserve leading spaces
                            meta["changes"].append({
                                "via": "missing_subject_prefix_pronoun",
                                "from": s,
                                "to": replaced,
                            })
                            s = replaced
                            any_change = True

            new_sentences.append(s)

        new_para = " ".join(new_sentences)
        out_paras.append(new_para)

        if new_para != original_para:
            meta["applied"] = True

    new_text = "\n\n".join(out_paras)
    meta["applied"] = bool(any_change)
    return new_text, meta
