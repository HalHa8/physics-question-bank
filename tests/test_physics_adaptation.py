from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from mathbank.content_locks import _question_metadata_layout
from mathbank.curriculums import build_default_metadata, get_curriculum_preset
from mathbank.pdf_inspector_helper import _has_multiple_inline_formula_images
from mathbank.pdf_source_verify import _local_block_reason
from mathbank.prompts import (
    COMMON_OCR_PROMPT,
    build_ai_solve_prompts,
    build_docx_source_verification_prompt,
    build_pdf_layout_prompt,
    build_pdf_parse_system_prompt,
    build_pdf_source_verification_prompt,
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
    assert 'src="/static/favicon.png"' in index
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


def test_physicsbank_avatar_and_readme_assets_share_the_selected_design():
    root = Path(__file__).resolve().parents[1]
    source = Image.open(root / "docs/images/physicsbank-avatar-b.png").convert("RGB")

    for name, size in (("favicon.png", 256), ("apple-touch-icon.png", 180)):
        with Image.open(root / "static" / name) as icon:
            assert icon.size == (size, size)
            expected = source.resize((size, size), Image.Resampling.LANCZOS)
            assert ImageChops.difference(icon.convert("RGB"), expected).getbbox() is None

    with Image.open(root / "static/favicon.ico") as icon:
        assert icon.size == (256, 256)

    index = (root / "static/index.html").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert 'href="/static/favicon.png"' in index
    assert index.count('src="/static/favicon.png"') == 2
    assert "docs/images/physicsbank-avatar-b.png" in readme
    assert "docs/images/physicsbank-qq-group.png" in readme
    assert "904544454" in readme
    with Image.open(root / "docs/images/physicsbank-qq-group.png") as qr:
        assert qr.size == (313, 313)  # Preserve the code's white scan margin.


def test_physicsbank_avatar_is_served_in_the_page_and_icon_routes(client):
    page = client.get("/")
    assert page.status_code == 200
    assert page.text.count('/static/favicon.png?v=') == 3

    for route, size in (
        ("/static/favicon.png", 256),
        ("/favicon.ico", 256),
        ("/apple-touch-icon.png", 180),
    ):
        response = client.get(route)
        assert response.status_code == 200
        with Image.open(BytesIO(response.content)) as icon:
            assert icon.size == (size, size)


def test_upstream_source_review_prompts_check_physics_evidence():
    pdf_prompt = build_pdf_source_verification_prompt([{"id": "item_001"}])
    layout_prompt = build_pdf_layout_prompt("1. 物体沿斜面运动。", {"page_index": 0})
    docx_prompt = build_docx_source_verification_prompt([{"id": "word_001"}])

    for critical in ("单位大小写", "矢量方向", "有效数字", "电路连接", "实验装置"):
        assert critical in pdf_prompt
        assert critical in docx_prompt
    assert "物理试卷" in layout_prompt
    assert "受力图、电路图" in layout_prompt
    assert "坐标轴物理量与单位" in layout_prompt


@pytest.mark.parametrize("source,changed", [
    ("1. 电阻串联，电流为2 A。", "1. 电阻并联，电流为2 A。"),
    ("1. 电池正极接A。", "1. 电池负极接A。"),
    ("1. 物体匀速运动。", "1. 物体加速运动。"),
    ("1. 电压为2 V。", "1. 电压为2 mV。"),
    ("1. 磁场方向向左。", "1. 磁场方向向右。"),
])
def test_pdf_review_does_not_clear_changed_physics_conditions(source, changed):
    assert _local_block_reason(source, changed) == "condition_difference"


@pytest.mark.parametrize("label,question_type", [
    ("实验题", "experiment"),
    ("计算题", "detailed_answer"),
    ("简答题", "short_answer"),
])
def test_physics_question_type_prefix_is_metadata_only_when_verified(label, question_type):
    source = f"1. （{label}）测量小车加速度。"
    output = "1. 测量小车加速度。"
    assert label not in _question_metadata_layout(source, {
        "content": output,
        "question_type": question_type,
    })
    assert label in _question_metadata_layout(source, {
        "content": output,
        "question_type": "single_choice",
    })


def test_inline_formula_loss_detection_uses_physics_context():
    from types import SimpleNamespace

    items = []
    for index in range(3):
        y = 80 + index * 40
        items.extend([
            SimpleNamespace(item_type="text", x=30, y=y, width=50, height=10, text="已知加速度"),
            SimpleNamespace(item_type="image", x=84, y=y - 1, width=28, height=12, text=""),
            SimpleNamespace(item_type="text", x=116, y=y, width=70, height=10, text="，求位移。"),
        ])
    assert _has_multiple_inline_formula_images(items)
    for item in items:
        if item.item_type == "text":
            item.text = "图示" if item.x < 80 else "，说明现象。"
    assert not _has_multiple_inline_formula_images(items)
