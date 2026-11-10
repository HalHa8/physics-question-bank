import pytest

from mathbank.pdf_page_fragments import SCHEMA, validate_pdf_page_fragments


@pytest.mark.parametrize("flag", [None, 0, 1, "false", "true"])
def test_fragment_protocol_rejects_non_boolean_completeness(flag):
    response = {
        "schema": SCHEMA,
        "blocks": [],
        "figures": [],
        "ignored_candidates": [],
        "page_complete": flag,
        "warnings": [],
    }
    with pytest.raises(ValueError, match="协议字段或版本无效"):
        validate_pdf_page_fragments(response, {"page_index": 0})
