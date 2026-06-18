from dffrnt_assistant.ingest.tags import normalize_tag_payload


def test_list_of_flat_tags():
    leaf, paths = normalize_tag_payload(["finance", "healthcare"])
    assert leaf == ["finance", "healthcare"]
    assert paths == ["finance", "healthcare"]


def test_hierarchy_expands_to_prefixes():
    leaf, paths = normalize_tag_payload(["clients/acme/2024"])
    assert leaf == ["clients/acme/2024"]
    assert paths == ["clients", "clients/acme", "clients/acme/2024"]


def test_empty_input():
    assert normalize_tag_payload("") == ([], [])
    assert normalize_tag_payload(None) == ([], [])
