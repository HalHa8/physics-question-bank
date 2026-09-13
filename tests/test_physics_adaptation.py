from mathbank.curriculums import build_default_metadata, get_curriculum_preset
from mathbank.prompts import (
    COMMON_OCR_PROMPT,
    build_ai_solve_prompts,
    build_pdf_parse_system_prompt,
    build_tikz_draw_prompt,
)


def test_physics_curriculum_is_default_and_complete():
    metadata = build_default_metadata()
    curriculum = metadata["curriculum"]

    assert "必修第一册" in curriculum
    assert "必修第三册" in curriculum
    assert "选择性必修第三册" in curriculum
    assert "第四章 运动和力的关系" in curriculum["必修第一册"]
    assert "第十章 静电场中的能量" in curriculum["必修第三册"]
    assert get_curriculum_preset()["version"] == "P"


def test_physics_question_types_are_the_default():
    labels = {
        item["value"]: item["label"]
        for item in build_default_metadata()["question_types"]
    }

    assert labels["experiment"] == "实验题"
    assert labels["detailed_answer"] == "计算题"
    assert labels["short_answer"] == "简答题"


def test_physics_prompts_preserve_units_and_modeling_discipline():
    system_prompt, _ = build_ai_solve_prompts(
        "detailed_answer", "质量为 $m$ 的物体在恒力作用下运动。"
    )
    parse_prompt = build_pdf_parse_system_prompt(
        {"必修第一册": {"第四章 运动和力的关系": []}}, False
    )
    draw_prompt = build_tikz_draw_prompt("物体沿斜面下滑", multimodal=False)

    assert "物理量、单位与公式" in COMMON_OCR_PROMPT
    assert "研究对象、物理过程、正方向" in system_prompt
    assert "量纲、数量级、边界条件和物理意义" in system_prompt
    assert "experiment / detailed_answer / short_answer" in parse_prompt
    assert "受力图、电路图、光路图" in draw_prompt
