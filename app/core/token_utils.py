# app/core/token_utils.py
import re
from typing import Dict, List, Tuple, Any
from collections import defaultdict

# Token pattern: [LABEL_n]  -> [ORG_1], [DATE_2], ...
TOKEN_RE = re.compile(r"\[[A-Z]+_[0-9]+\]")
TOKEN_KEY_RE = re.compile(r"^\[([A-Z]+)_(\d+)\]$")
LOOKS_LIKE_TOKEN = re.compile(r"\[[A-Z]+_[0-9]+\]")

def _next_indices(existing_maps: Dict[str, str]) -> dict:
    """
    Hitung index berikutnya per label (ORG, PERSON, DATE, ...) dari token yang sudah ada.
    existing_maps berbentuk { "[ORG_1]": "ABC University", ... }
    """
    next_idx = defaultdict(int)
    for k in existing_maps.keys():
        m = TOKEN_KEY_RE.match(k)
        if not m:
            continue
        label, num = m.group(1), int(m.group(2))
        if num >= next_idx[label]:
            next_idx[label] = num + 1
    return next_idx

def sanitize_new_maps(new_maps: Dict[str, str],
                      existing_maps: Dict[str, str]) -> Dict[str, str]:
    """
    Bersihkan hasil NER supaya tidak menyebabkan nested/double-masking:
    - drop jika value terlihat seperti token (mis. "[ORG_1]") atau mengandung '['/']'
    - drop jika value sudah ada di existing_maps (hindari duplikat)
    - drop jika key bukan pola token [LABEL_n]
    Return tetap dalam bentuk { "[ORG_n]": "value" } (raw dari NER tapi terfilter).
    """
    existing_values = {(v or "").strip() for v in (existing_maps or {}).values()}
    clean: Dict[str, str] = {}
    for k, v in (new_maps or {}).items():
        if v is None:
            continue
        vs = str(v).strip()
        if not vs:
            continue
        # value terlihat seperti token atau mengandung bracket -> buang
        if LOOKS_LIKE_TOKEN.fullmatch(vs) or "[" in vs or "]" in vs:
            continue
        # jika sudah pernah di-map, skip
        if vs in existing_values:
            continue
        # key harus token-like juga, untuk safety
        if not TOKEN_KEY_RE.match(str(k)):
            continue
        clean[str(k)] = vs
    return clean

def reindex_new_maps(new_maps: Dict[str, str],
                     existing_maps: Dict[str, str]) -> Dict[str, str]:
    """
    Rename token hasil NER agar tidak bentrok dengan existing_maps.
    Input  : { "[ORG_1]": "ABC University", ... }  (hasil sanitize)
    Output : { "[ORG_5]": "ABC University", ... }  (lanjut index-nya)
    """
    next_idx = _next_indices(existing_maps)
    renamed: Dict[str, str] = {}
    for raw_key, val in (new_maps or {}).items():
        m = TOKEN_KEY_RE.match(raw_key)
        if not m:  # kalau format tak sesuai [LABEL_n], biarkan apa adanya
            renamed[raw_key] = val
            continue
        label = m.group(1)
        idx = next_idx[label]
        next_idx[label] += 1
        new_key = f"[{label}_{idx}]"
        renamed[new_key] = val
    return renamed

def apply_outside_tokens(text: str, token_to_val: Dict[str, str]) -> str:
    """
    Replace 'value' -> 'token' HANYA di segmen non-token.
    token_to_val: { "[ORG_5]": "ABC University", ... }
    """
    # urutkan value terpanjang dulu agar tidak partial-replace
    repl_list: List[Tuple[str, str]] = sorted(
        [(v, k) for k, v in (token_to_val or {}).items()],
        key=lambda x: len(x[0]),
        reverse=True
    )

    out_parts: List[str] = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        seg = text[pos:m.start()]
        for val, tok in repl_list:
            if val:
                seg = seg.replace(val, tok)
        out_parts.append(seg)
        out_parts.append(m.group(0))  # token as-is
        pos = m.end()

    # tail
    seg = text[pos:]
    for val, tok in repl_list:
        if val:
            seg = seg.replace(val, tok)
    out_parts.append(seg)
    return "".join(out_parts)

def rename_layer_map_for_reindexed_pairs(layer_map: Dict[str, str],
                                         reindexed_maps: Dict[str, str]) -> Dict[str, str]:
    """
    ner_pairs.map biasanya { "[ORG_1]": "ABC" } dari NER.
    Setelah reindex, kita rename key berdasar value:
      - hanya simpan entry yang valuenya memang ada di reindexed_maps.values()
      - kalau tidak ada, drop (hindari kasus value = "[ORG_1]")
    """
    inv = {v: k for k, v in (reindexed_maps or {}).items()}  # value -> new_token
    renamed: Dict[str, str] = {}
    for old_token, val in (layer_map or {}).items():
        vs = "" if val is None else str(val).strip()
        new_token = inv.get(vs)
        if not new_token:
            # value tidak ada di reindexed (mungkin "[ORG_1]" atau noise) -> drop
            continue
        renamed[new_token] = vs
    return renamed

def integrate_ner(masked: str,
                  existing_maps: Dict[str, str],
                  ner_pairs: List[Dict[str, Any]],
                  ner_maps_raw: Dict[str, str]
                  ) -> Tuple[str, List[Dict[str, Any]], Dict[str, str]]:
    """
    - Sanitize hasil NER (buang value yang terlihat token/duplikat).
    - Reindex agar tidak bentrok dengan token existing.
    - Apply ke string masked di luar token.
    - Rename layer pairs; drop pair yang valuenya tidak ada di reindexed.
    Return: (masked2, renamed_pairs, reindexed_maps)
    """
    sanitized = sanitize_new_maps(ner_maps_raw, existing_maps)
    if not sanitized or not ner_pairs:
        return masked, [], {}

    reindexed = reindex_new_maps(sanitized, existing_maps)
    masked2 = apply_outside_tokens(masked, reindexed)

    renamed_pairs: List[Dict[str, Any]] = []
    for p in ner_pairs:
        if "map" in p and isinstance(p["map"], dict):
            new_map = rename_layer_map_for_reindexed_pairs(p["map"], reindexed)
            if not new_map:
                continue
            p2 = dict(p)
            p2["type"] = (p2.get("type") or "NER").rstrip() + " / model"
            p2["map"] = new_map
            renamed_pairs.append(p2)
    return masked2, renamed_pairs, reindexed
