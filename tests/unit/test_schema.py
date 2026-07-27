from dffrnt_assistant.schema import page_label, to_source


def test_page_label_prefers_page_then_slide():
    assert page_label({"page_number": 3, "slide_index": 7}) == 3
    assert page_label({"slide_index": 7}) == 7
    assert page_label({}) == 0


def test_to_source_shape():
    source = to_source({"filename": "a.pdf", "page_number": 2}, 0.98765)
    assert source["filename"] == "a.pdf"
    assert source["page"] == 2
    assert source["score"] == round(0.98765, 4)


def test_to_source_handles_missing_score():
    source = to_source({"filename": "a.pdf"}, None)
    assert source["score"] is None
    assert source["page"] == 0
