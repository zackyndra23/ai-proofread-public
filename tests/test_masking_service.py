from app.modules.masking import services as ms


def test_masking_service_run_layers(monkeypatch):
    monkeypatch.setattr(ms, "mask_with_piiregex", lambda text, counters=None: ("m1", [{"type": "pii_EMAIL", "map": {"[EMAIL_0]": "a"}}]))
    monkeypatch.setattr(ms, "_find_token_spans", lambda text: [(0, 1)])
    monkeypatch.setattr(ms, "mask_with_phones_lib", lambda text, region, counters=None: ("m2", [{"type": "phones_lib", "map": {"[PHONE_NUMBER_0]": "1"}}]))
    monkeypatch.setattr(ms, "mask_with_patterns", lambda text, counters=None: ("m3", [{"type": "regex_DATE", "map": {"[DATE_0]": "x"}}]))
    monkeypatch.setattr(ms, "locale_to_region", lambda loc: "ID")

    svc = ms.MaskingService()
    masked, layers, layered_maps, order, token_spans = svc.run_layers("hi", "id")

    assert masked == "m3"
    assert order == ["pii_EMAIL", "phones_lib", "regex_DATE"]
    assert layered_maps["[EMAIL_0]"] == "a"
    assert token_spans == [(0, 1)]


def test_masking_service_extract_token_list():
    svc = ms.MaskingService()
    tokens = svc.extract_token_list("Hi [A_0] [A_0] [B_1]")
    assert tokens == ["[A_0]", "[B_1]"]


def test_masking_service_unmask():
    svc = ms.MaskingService()
    out = svc.unmask("Hi [NAME_0]", {"[NAME_0]": "R"})
    assert out == "Hi R"
