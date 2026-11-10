import json

import pytest

from mathbank import content_sources
from mathbank.paper_parse import parse_paper_completion


def test_pdf_partial_questions_keep_physics_content_and_reject_invalid_items():
    stem = "电流为 −1.20 A，坐标轴沿水平方向。"
    reply = {"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps({"questions": [
            {"content": stem, "answer_markdown": None},
            {"content": "坏答案", "answer_markdown": {}},
            {"content": ""},
        ]}),
    }}]}
    report = {}
    cards = parse_paper_completion(reply, diagnostics=report, allow_partial_questions=True)
    assert [card["content"] for card in cards] == [stem]
    assert cards[0]["answer_markdown"] == ""
    assert report["pdf_question_validation"]["rejected_count"] == 2
    assert "坏答案" not in str(report)
    with pytest.raises(ValueError):
        parse_paper_completion(reply)
    reply["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ValueError, match="截断"):
        parse_paper_completion(reply, allow_partial_questions=True)


def test_local_credits_append_without_overriding_physics_catalog(tmp_path, monkeypatch):
    public = content_sources.load_content_sources(content_sources.CONTENT_SOURCES_PATH)
    path = tmp_path / "content_sources.local.json"
    monkeypatch.setattr(content_sources, "LOCAL_CONTENT_SOURCES_PATH", path)
    assert content_sources.load_content_sources() == public
    entry = {
        "id": "synthetic-test-source", "name": "测试来源", "authors": ["测试作者"],
        "scope": "合成数据", "changes": "测试记录", "url": "https://example.org/source",
        "license": {"name": "测试许可", "url": "https://example.org/license"},
    }
    path.write_text(json.dumps({**public, "sources": [entry]}), encoding="utf-8")
    assert content_sources.load_content_sources()["sources"] == public["sources"] + [entry]
    path.write_text(json.dumps({**public, "sources": [entry, entry]}), encoding="utf-8")
    with pytest.raises(ValueError):
        content_sources.load_content_sources()
