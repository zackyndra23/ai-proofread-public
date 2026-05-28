from services import masking as m


class DummyMatch:
    def __init__(self, start, end):
        self.start = start
        self.end = end


def test_find_token_spans_and_overlaps():
    text = "Hi [EMAIL_0] there"
    spans = m._find_token_spans(text)
    assert spans == [(3, 12)]
    assert m._overlaps(3, 4, spans) is True
    assert m._overlaps(0, 2, spans) is False


def test_mask_generic_numeric_phones():
    masked, mp = m._mask_generic_numeric_phones("Call 0812345678 now", [], {})
    assert "[PHONE_NUMBER_0]" in masked
    assert mp["[PHONE_NUMBER_0]"].strip() == "0812345678"


def test_mask_with_piiregex_uses_counters(monkeypatch):
    class Dummy:
        def emails(self, text):
            return ["a@b.com"]

        def credit_cards(self, text):
            return ["4111 1111 1111 1111"]

    monkeypatch.setattr(m, "PiiRegex", lambda: Dummy())
    text = "Email a@b.com card 4111 1111 1111 1111"
    masked, layers = m.mask_with_piiregex(text, counters={})
    assert "[EMAIL_0]" in masked
    assert "[CREDIT_CARD_0]" in masked
    types = {l["type"] for l in layers}
    assert "pii_EMAIL" in types
    assert "pii_CREDIT_CARD" in types


def test_mask_with_piiregex_none_counters_and_overlap(monkeypatch):
    class Dummy:
        def emails(self, text):
            return ["a@b.com"]

        def credit_cards(self, text):
            return []

    monkeypatch.setattr(m, "PiiRegex", lambda: Dummy())
    monkeypatch.setattr(m, "_find_token_spans", lambda text: [(0, len(text))])
    masked, layers = m.mask_with_piiregex("a@b.com", counters=None)
    assert masked == "a@b.com"
    assert layers == []


def test_mask_with_phones_lib_uses_lib(monkeypatch):
    def matcher(text, region):
        st = text.index("0812")
        en = st + 4
        return [DummyMatch(st, en)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: object())
    monkeypatch.setattr(m, "is_possible_number", lambda parsed: True)

    text = "Call (0812) now"
    masked, layers = m.mask_with_phones_lib(text, "ID", counters={})
    assert "[PHONE_NUMBER_0]" in masked
    assert layers
    raw = layers[0]["map"]["[PHONE_NUMBER_0]"]
    assert raw.startswith("(") and raw.endswith(")")


def test_mask_with_phones_lib_fallback(monkeypatch):
    monkeypatch.setattr(m, "PhoneNumberMatcher", lambda text, region: [])
    masked, layers = m.mask_with_phones_lib("Call 0812345678 now", "ID", counters={})
    assert "[PHONE_NUMBER_0]" in masked
    assert layers


def test_mask_with_phones_lib_counters_none(monkeypatch):
    monkeypatch.setattr(m, "PhoneNumberMatcher", lambda text, region: [])
    monkeypatch.setattr(m, "_mask_generic_numeric_phones", lambda text, spans, counters: (text, {}))
    masked, layers = m.mask_with_phones_lib("Call 0812 now", "ID", counters=None)
    assert masked == "Call 0812 now"
    assert layers == []


def test_mask_with_phones_lib_overlapping_matches(monkeypatch):
    def matcher(text, region):
        return [DummyMatch(5, 9), DummyMatch(7, 11)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: object())
    monkeypatch.setattr(m, "is_possible_number", lambda parsed: True)
    monkeypatch.setattr(m, "_mask_generic_numeric_phones", lambda text, spans, counters: (text, {}))

    masked, layers = m.mask_with_phones_lib("Call 081234 now", "ID", counters={})
    assert masked.count("[PHONE_NUMBER_0]") == 1
    assert layers


def test_mask_with_phones_lib_overlaps_skip(monkeypatch):
    def matcher(text, region):
        return [DummyMatch(5, 9)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "_overlaps", lambda st, en, spans: True)
    monkeypatch.setattr(m, "_mask_generic_numeric_phones", lambda text, spans, counters: (text, {}))

    masked, layers = m.mask_with_phones_lib("Call 0812 now", "ID", counters={})
    assert masked == "Call 0812 now"
    assert layers == []


def test_mask_with_phones_lib_parse_exception(monkeypatch):
    def matcher(text, region):
        return [DummyMatch(5, 9)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: (_ for _ in ()).throw(m.NumberParseException(0, "x")))
    monkeypatch.setattr(m, "_mask_generic_numeric_phones", lambda text, spans, counters: (text, {}))

    masked, layers = m.mask_with_phones_lib("Call 0812 now", "ID", counters={})
    assert masked == "Call 0812 now"
    assert layers == []


def test_mask_with_patterns_basic():
    text = "Email test@example.com on 02 Mei 2018 #fraud"
    masked, layers = m.mask_with_patterns(text, counters={})
    assert "[EMAIL_0]" in masked
    assert "[DATE_0]" in masked
    assert "[KEYWORD_0]" in masked
    types = {l["type"] for l in layers}
    assert "regex_EMAIL" in types
    assert "regex_DATE" in types
    assert "regex_KEYWORD" in types


def test_mask_with_patterns_no_matches_and_overlap(monkeypatch):
    monkeypatch.setattr(m, "_find_token_spans", lambda text: [(0, len(text))])
    out, layers = m.mask_with_patterns("hello@example.com", counters=None)
    assert out == "hello@example.com"
    assert layers == []


def test_mask_emails_and_mask_phones(monkeypatch):
    m1, mapping, idx = m.mask_emails("Email a@b.com", start_idx=1)
    assert "{{EMAIL_1}}" in m1
    assert idx == 2

    def matcher(text, region):
        st = text.index("0812")
        return [DummyMatch(st, st + 4)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: object())
    monkeypatch.setattr(m, "is_possible_number", lambda parsed: True)

    m2, mp2, idx2 = m.mask_phones("Call 0812 now", "ID", start_idx=1)
    assert "{{PHONE_1}}" in m2
    assert idx2 == 2
    assert mp2["{{PHONE_1}}"] == "0812"


def test_mask_phones_parse_exception(monkeypatch):
    def matcher(text, region):
        st = text.index("0812")
        return [DummyMatch(st, st + 4)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: (_ for _ in ()).throw(m.NumberParseException(0, "x")))

    out, mapping, idx = m.mask_phones("Call 0812 now", "ID", start_idx=1)
    assert "{{PHONE_1}}" not in out
    assert mapping == {}
    assert idx == 1


def test_normalize_phone_numbers(monkeypatch):
    def matcher(text, region):
        st = text.index("0812")
        return [DummyMatch(st, st + 4)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: object())
    monkeypatch.setattr(m, "is_possible_number", lambda parsed: True)
    monkeypatch.setattr(m, "format_number", lambda parsed, fmt: "X")

    class F:
        E164 = "E164"
        NATIONAL = "NATIONAL"

    monkeypatch.setattr(m, "PhoneNumberFormat", F)

    out = m.normalize_phone_numbers("Call 0812 now", "ID", e164=True)
    assert "X" in out


def test_normalize_phone_numbers_parse_exception(monkeypatch):
    def matcher(text, region):
        st = text.index("0812")
        return [DummyMatch(st, st + 4)]

    monkeypatch.setattr(m, "PhoneNumberMatcher", matcher)
    monkeypatch.setattr(m, "pn_parse", lambda raw, region: (_ for _ in ()).throw(m.NumberParseException(0, "x")))

    out = m.normalize_phone_numbers("Call 0812 now", "ID", e164=True)
    assert out == "Call 0812 now"


def test_apply_mapping_reverse_and_unmask():
    text = "Hello {{EMAIL_1}}"
    out = m.apply_mapping_reverse(text, {"{{EMAIL_1}}": "a@b.com"})
    assert out == "Hello a@b.com"

    masked = "Hi [NAME_0]"
    out2 = m.unmask_text(masked, {"[NAME_0]": "Rizal"})
    assert out2 == "Hi Rizal"


def test_unmask_text_layers():
    layers = [{"map": {"{{EMAIL_1}}": "a@b.com"}}]
    out = m.unmask_text_layers("Hello {{EMAIL_1}}", layers)
    assert out == "Hello a@b.com"


def test_flatten_layered_maps():
    layers = {"L1": {"[A_0]": "x"}, "L2": {"[B_0]": "y"}}
    assert m.flatten_layered_maps(layers) == {"[A_0]": "x", "[B_0]": "y"}
    assert m.flatten_layered_maps(None) == {}


def test_mask_generic_numeric_phones_overlaps_and_length_filters(monkeypatch):
    masked, mp = m._mask_generic_numeric_phones("Call 0812345678", [(5, 15)], {})
    assert masked == "Call 0812345678"
    assert mp == {}

    masked2, mp2 = m._mask_generic_numeric_phones("Call +12345 and 12345", [], {})
    assert masked2 == "Call +12345 and 12345"
    assert mp2 == {}


def test_mask_generic_numeric_phones_overlapping_candidates(monkeypatch):
    class DummyMatch:
        def __init__(self, st, en, text):
            self._st = st
            self._en = en
            self._text = text

        def span(self):
            return (self._st, self._en)

        def group(self, _=0):
            return self._text

    def fake_finditer(text):
        return [
            DummyMatch(0, 10, "0812345678"),
            DummyMatch(5, 12, "4567890"),
        ]

    monkeypatch.setattr(m, "PHONE_GENERIC_RE", type("R", (), {"finditer": staticmethod(fake_finditer)}))
    masked, mp = m._mask_generic_numeric_phones("0812345678XXXX", [], {})
    assert len(mp) == 1
