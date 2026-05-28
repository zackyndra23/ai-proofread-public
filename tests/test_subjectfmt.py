from services import subjectfmt as sf


def test_apply_subjectfmt_skips_non_id_or_type():
    text = "Ibu Nina menyatakan sesuatu."
    out, meta = sf.apply_subjectfmt(text, "en", "reference-check")
    assert out == text
    assert meta.get("skipped") is True
    assert meta.get("applied") is False


def test_apply_subjectfmt_replaces_repeated_subject_and_prefix():
    text = "Ibu Nina menyatakan sesuatu. Ibu Nina menambahkan hal lain. menyampaikan kabar."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert "Beliau menambahkan hal lain." in out
    assert "Beliau menyampaikan kabar." in out
    assert meta["applied"] is True


def test_apply_subjectfmt_name_only():
    text = "Rizal menyatakan ini. mengatakan lainnya."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert "Ia mengatakan lainnya." in out
    assert meta["applied"] is True


def test_pick_dominant_name_only_variants():
    assert sf._pick_dominant_name_only("123") is None
    assert sf._pick_dominant_name_only("Ibu Bapak") is None
    assert sf._pick_dominant_name_only("Rizal Anna") is None
    assert sf._pick_dominant_name_only("Rizal Rizal") == "Rizal"


def test_choose_pronoun_variants():
    assert sf._choose_pronoun(None) == "Ia"
    assert sf._choose_pronoun("Ibu") == "Beliau"
    assert sf._choose_pronoun("Saudara") == "Ia"
    assert sf._choose_pronoun("X") == "Ia"


def test_apply_subjectfmt_empty_text():
    out, meta = sf.apply_subjectfmt("   ", "id", "reference-check")
    assert out.strip() == ""
    assert meta["applied"] is False


def test_apply_subjectfmt_single_sentence():
    text = "Ibu Nina menyatakan sesuatu."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert out == text
    assert meta["applied"] is False


def test_apply_subjectfmt_header_and_blank_paragraphs():
    text = "Percobaan 03:\n\nIbu Nina menyatakan sesuatu. Ibu Nina menambahkan hal lain.\n\n   \n\nIbu Nina menambahkan hal lain."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert "Percobaan 03:" in out
    assert meta["applied"] is True


def test_apply_subjectfmt_fallback_name_only_without_verb():
    text = "Juwita Shafira hadir di sini. menyampaikan kabar."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert "Ia menyampaikan kabar." in out
    assert meta["applied"] is True


def test_apply_subjectfmt_dominant_name_fallback():
    text = "Percobaan dilakukan oleh Chika. Chika menjelaskan hal lain."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert "Beliau" not in out
    assert "Chika" in out
    assert meta["applied"] is True


def test_apply_subjectfmt_multiple_subjects_no_dominant():
    text = "Ibu Nina hadir. Bapak Andi pergi."
    out, meta = sf.apply_subjectfmt(text, "id", "reference-check")
    assert out == text
    assert meta["applied"] is False
