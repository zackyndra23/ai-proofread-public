# services/htmltags.py
import re
from bs4 import BeautifulSoup

TEXT_TOKEN_RE = re.compile(r"\[TEXT_\d+\]")
TABLE_TOKEN_RE = re.compile(r"\[TABLE_\d+\]")

def _iter_text_nodes(soup):
    # Ambil text nodes "layak kirim ke LLM": lewati script/style/noscript
    skip = {"script", "style", "noscript"}
    for el in soup.find_all(string=True):  # (note: 'string' bukan 'text' - yang lama deprecated)
        parent = el.parent.name if el.parent else ""
        if parent in skip:
            continue
        txt = (el.string or "").strip()
        if not txt:
            continue
        # ⛔ penting: jangan tokenisasi placeholder kita sendiri
        if TEXT_TOKEN_RE.fullmatch(txt) or TABLE_TOKEN_RE.fullmatch(txt):
            continue
        yield el, txt

def _iter_tables(soup):
    for i, tbl in enumerate(soup.find_all("table"), start=1):
        yield tbl, f"[TABLE_{i:02d}]"

def freeze_html(raw_html: str):
    """
    Return:
    {
      'html_skeleton': '<html>... [TEXT_01] ... [TABLE_01] ...</html>',
      'text_map': {'[TEXT_01]':'...', ...},
      'table_map': {'[TABLE_01]':'<table>...</table>', ...},
      'text_format': '[TEXT_01]: ...\\n[TEXT_02]: ...',
      'table_format': ['[TABLE_01]', '[TABLE_02]', ...]
    }
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    # 1) Freeze TABLES terlebih dulu
    table_map = {}
    for tbl, tk in _iter_tables(soup):
        table_map[tk] = str(tbl)
        placeholder = soup.new_string(tk)
        tbl.replace_with(placeholder)

    # 2) Freeze TEXT nodes jadi [TEXT_xx]
    text_map = {}
    counter = 0
    for node, txt in _iter_text_nodes(soup):
        counter += 1
        # tk = f"[TEXT_{counter:02d}]"
        tk = f""
        text_map[tk] = txt
        node.replace_with(tk)

    html_skeleton = str(soup)

    # Siapkan text_format untuk dikirim ke LLM (tanpa HTML/table)
    # Formatnya baris-per-baris agar deterministik saat reverse.
    # lines = [f"{k}: {v}" for k, v in text_map.items()]
    # text_format = "\n".join(lines)
    text_format = "\n".join(text_map.values())


    return {
        "html_skeleton": html_skeleton,
        "text_map": text_map,
        "table_map": table_map,
        "text_format": text_format,
        "table_format": list(table_map.keys()),
    }

def parse_text_format(text_format: str):
    """
    Balikkan string '[TEXT_01]: ...' menjadi dict { '[TEXT_01]': '...' }
    Robust ke spasi sebelum/after colon.
    """
    out = {}
    for line in (text_format or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            out[line] = ""
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = val.strip()
    return out

def reverse_html(html_skeleton: str, text_map_new: dict, table_map: dict):
    """
    Rekonstruksi HTML final:
    - Ganti [TEXT_xx] di html_skeleton dengan text_map_new[key]
    - Ganti [TABLE_xx] di html_skeleton dengan table_map[key] (as-is)
    """
    out = html_skeleton

    # Table restore
    for tk, html_tbl in (table_map or {}).items():
        out = out.replace(tk, html_tbl)

    # Text restore
    # Pastikan urutan deterministik (by numeric index)
    def _keynum(k):
        m = re.search(r"\[(?:TEXT)_(\d+)\]", k)
        return int(m.group(1)) if m else 0

    for tk in sorted(text_map_new.keys(), key=_keynum):
        out = out.replace(tk, text_map_new[tk])

    return out
