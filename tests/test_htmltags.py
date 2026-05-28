from services import htmltags


def test_freeze_html_tables_and_text():
    html = "<p>Hello</p><table><tr><td>1</td></tr></table>"
    res = htmltags.freeze_html(html)
    assert "[TABLE_01]" in res["html_skeleton"]
    assert res["table_map"]["[TABLE_01]"].startswith("<table")
    assert res["text_format"] == "Hello"
    assert "" in res["text_map"]


def test_iter_text_nodes_skips_script_and_empty():
    html = "<script>var a=1;</script><p> </p><p>Hi</p>"
    soup = htmltags.BeautifulSoup(html, "html.parser")
    items = list(htmltags._iter_text_nodes(soup))
    assert len(items) == 1
    assert items[0][1] == "Hi"


def test_parse_text_format_lines():
    out = htmltags.parse_text_format("Line1\n\nLine2")
    assert out["Line1"] == ""
    assert out["Line2"] == ""


def test_parse_text_format_with_colon():
    out = htmltags.parse_text_format("KEY: value")
    assert out["KEY"] == "value"


def test_reverse_html_replaces_tokens():
    skeleton = "<p>[TEXT_01]</p>[TABLE_01]"
    out = htmltags.reverse_html(
        skeleton,
        {"[TEXT_01]": "Hi"},
        {"[TABLE_01]": "<table></table>"},
    )
    assert "<p>Hi</p>" in out
    assert "<table></table>" in out
