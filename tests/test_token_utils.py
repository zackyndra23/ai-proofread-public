from app.core import token_utils as tu


def test_sanitize_new_maps_filters_bad_values():
    existing = {'[ORG_1]': 'Acme'}
    new_maps = {
        '[ORG_2]': '[ORG_1]',
        '[ORG_3]': 'Acme',
        '[ORG_4]': 'Beta',
        'BAD': 'Gamma',
        '[ORG_5]': 'A[B]',
    }
    clean = tu.sanitize_new_maps(new_maps, existing)
    assert clean == {'[ORG_4]': 'Beta'}


def test_sanitize_new_maps_handles_none_and_empty():
    clean = tu.sanitize_new_maps({"[ORG_1]": None, "[ORG_2]": ""}, {})
    assert clean == {}


def test_next_indices_skips_non_token_keys():
    out = tu._next_indices({"BAD": "x", "[ORG_2]": "y"})
    assert out["ORG"] == 3


def test_reindex_new_maps_advances_indices():
    existing = {'[ORG_2]': 'A', '[PERSON_5]': 'B'}
    new_maps = {'[ORG_1]': 'X', '[PERSON_1]': 'Y'}
    reindexed = tu.reindex_new_maps(new_maps, existing)
    assert reindexed == {'[ORG_3]': 'X', '[PERSON_6]': 'Y'}


def test_reindex_new_maps_keeps_invalid_key():
    reindexed = tu.reindex_new_maps({"BAD": "X"}, {})
    assert reindexed == {"BAD": "X"}


def test_apply_outside_tokens_only():
    text = 'Hello Alice [ORG_1] Alice'
    token_to_val = {'[ORG_2]': 'Alice'}
    out = tu.apply_outside_tokens(text, token_to_val)
    assert out == 'Hello [ORG_2] [ORG_1] [ORG_2]'


def test_integrate_ner_basic():
    masked = 'Hello [NAME_0] from Acme'
    existing_maps = {'[NAME_0]': 'Rizal'}
    ner_pairs = [{'type': 'NER', 'map': {'[ORG_1]': 'Acme'}}]
    ner_maps_raw = {'[ORG_1]': 'Acme'}

    masked2, pairs2, reindexed = tu.integrate_ner(masked, existing_maps, ner_pairs, ner_maps_raw)

    assert masked2 == 'Hello [NAME_0] from [ORG_0]'
    assert reindexed == {'[ORG_0]': 'Acme'}
    assert pairs2 == [{'type': 'NER / model', 'map': {'[ORG_0]': 'Acme'}}]


def test_rename_layer_map_for_reindexed_pairs_drops_unknown():
    out = tu.rename_layer_map_for_reindexed_pairs({"[ORG_1]": "X"}, {"[ORG_2]": "Y"})
    assert out == {}


def test_integrate_ner_returns_early_when_empty():
    masked2, pairs2, reindexed = tu.integrate_ner("Hi", {}, [], {})
    assert masked2 == "Hi"
    assert pairs2 == []
    assert reindexed == {}


def test_integrate_ner_skips_empty_new_map():
    masked = "Hello Acme"
    existing_maps = {}
    ner_pairs = [{"type": "NER", "map": {"[ORG_1]": "Other"}}]
    ner_maps_raw = {"[ORG_1]": "Acme"}
    masked2, pairs2, reindexed = tu.integrate_ner(masked, existing_maps, ner_pairs, ner_maps_raw)
    assert masked2 == "Hello [ORG_0]"
    assert reindexed == {"[ORG_0]": "Acme"}
    assert pairs2 == []
