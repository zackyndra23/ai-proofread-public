from app.modules.htmlmask import services as hs


def test_as_json_dict_if_possible():
    assert hs.as_json_dict_if_possible('{"a": 1}') == {"a": 1}
    assert hs.as_json_dict_if_possible("[1, 2]") is None
    assert hs.as_json_dict_if_possible("not json") is None


def test_htmlmask_service_calls(monkeypatch):
    monkeypatch.setattr(hs, "freeze_html", lambda html: {"html_skeleton": "S"})
    monkeypatch.setattr(hs, "reverse_html", lambda skeleton, text_map_new, table_map: "OK")
    svc = hs.HtmlMaskService()
    assert svc.freeze("<p>x</p>") == {"html_skeleton": "S"}
    assert svc.reverse("S", {}, {}) == "OK"
