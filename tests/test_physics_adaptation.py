from pathlib import Path

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


def test_legacy_math_heal_does_not_rewrite_physics_book_names(db_session, monkeypatch):
    import main
    from mathbank.database import Question

    monkeypatch.setitem(
        main.METADATA_CACHE,
        "curriculum",
        build_default_metadata()["curriculum"],
    )
    question = Question(
        content="物体做匀变速直线运动。",
        question_type="detailed_answer",
        category_compulsory="必修第一册",
        category_chapter="第二章 匀变速直线运动的研究",
    )
    db_session.add(question)
    db_session.commit()

    main.heal_database_curriculum_names()
    db_session.expire_all()

    assert db_session.get(Question, question.id).category_compulsory == "必修第一册"


def test_upstream_workspaces_keep_physics_brand_and_defaults():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static/index.html").read_text(encoding="utf-8")
    paper = (root / "static/js/paper.js").read_text(encoding="utf-8")
    editor = (root / "static/js/editor.js").read_text(encoding="utf-8")
    import_ui = (root / "static/js/import.js").read_text(encoding="utf-8")
    backend = (root / "main.py").read_text(encoding="utf-8")

    assert 'aria-label="PhysicsBank 主导航"' in index
    assert '<strong>PhysicsBank</strong>' in index
    assert 'src="/static/favicon.svg"' in index
    assert 'id="editorTitle">录入新物理题' in index
    assert '<option value="exam_19"' not in index
    assert '<option value="exam_19"' not in paper
    assert "paper_type: 'exam'" in paper
    assert "数学 &nbsp; 第" not in paper
    assert "数学　 第" not in paper
    assert "录入新数学题" not in editor + import_ui
    assert 'app = FastAPI(title="本地化物理题库管理系统 API"' in backend
    assert 'payload.get("paper_type", "exam_19")' not in backend
    assert "'电磁感应'" in backend
    assert "'experiment'" in backend
