"""Physics-specific contracts for the shared native PDF/Word upgrade."""

from pathlib import Path

import pytest

from mathbank.curriculums import DEFAULT_QUESTION_TYPES, load_curriculum
from mathbank.docx_helper import _new_diagnostics
from mathbank.paper_parse_service import validate_import_knowledge
from mathbank.source_metadata import (
    _explicit_section_type, apply_source_metadata_response,
    build_source_metadata_messages, prepare_word_source_metadata,
)


@pytest.mark.parametrize("label,expected", [
    ("单项选择题", "single_choice"), ("多项选择题", "multi_choice"),
    ("填空题", "fill_in_blank"), ("实验题", "experiment"),
    ("计算题", "detailed_answer"), ("简答题", "short_answer"),
])
def test_physics_section_declarations_keep_all_six_types(label, expected):
    assert _explicit_section_type("一、" + label) == expected
    assert expected in {row["value"] for row in DEFAULT_QUESTION_TYPES}


def test_native_physics_source_keeps_units_vectors_polarity_and_original_answer():
    body = r"物块质量 $m=2.0\,kg$，电流为 $I=3\,mA$，时间 $t=20\,ms$。取向右为正，速度 $\vec{v}=-3.0\,m/s$。电流表正接线柱接电源正极，求加速度。"
    source = "2026年高三物理试卷\n一、计算题\n1. " + body + "\n参考答案：\n1. 向左，保留两位有效数字。"
    plan = prepare_word_source_metadata(source, _new_diagnostics())
    assert plan["eligible"], plan["fallback_reasons"]
    curriculum = load_curriculum("P")
    compulsory = next(iter(curriculum))
    chapter = next(iter(curriculum[compulsory]))
    response = {"items": [{"id": plan["questions"][0]["id"],
        "question_type": "detailed_answer", "difficulty": "normal",
        "category_compulsory": compulsory, "category_chapter": chapter,
        "category_knowledge": ""}]}
    result = apply_source_metadata_response(response, plan, curriculum)[0]
    assert result["content"] == body
    assert result["answer_markdown"] == "[EXTRACTED_ORIGINAL]向左，保留两位有效数字。"
    prompt = build_source_metadata_messages(plan, curriculum)[0]["content"]
    assert "高中物理" in prompt and "单位大小写" in prompt and "experiment" in prompt
    assert "随机变量及其分布" not in prompt


def test_import_leaf_validation_uses_physics_catalog_without_inventing_leaves():
    curriculum = load_curriculum("P")
    compulsory = next(iter(curriculum))
    chapter, leaves = next(iter(curriculum[compulsory].items()))
    row = {"category_compulsory": compulsory, "category_chapter": chapter}
    validate_import_knowledge([row], curriculum, dependencies=None)
    assert row["category_knowledge"] == ""
    validate_import_knowledge([{**row, "category_knowledge": leaves[0]}], curriculum, dependencies=None)
    with pytest.raises(ValueError, match="小节不属于"):
        validate_import_knowledge([{**row, "category_knowledge": "虚构的数学小节"}], curriculum, dependencies=None)
    assert load_curriculum("P") == curriculum


def test_markdown_upload_is_not_advertised_without_a_backend():
    source = (Path(__file__).parents[1] / "static/js/import.js").read_text(encoding="utf-8")
    assert "/api/upload/markdown-source" not in source
    assert "仅支持 .tex、.pdf 或 .docx 试卷文件。" in source
    assert "const sourceFormat = 'tex';" in source
