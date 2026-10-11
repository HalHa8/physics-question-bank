"""Startup label preservation (upstream 3252b72), including PhysicsBank P."""

import pytest

from mathbank.curriculums import load_curriculum
from mathbank.database import Question, QuestionCurriculum


def seed(session, compulsory, chapter, knowledge, version="P"):
    question = Question(
        content=r"物理原文 $\vec{F}=-2.00\,\mathrm{mN}$",
        question_type="experiment", category_compulsory=compulsory,
        category_chapter=chapter, category_knowledge=knowledge,
        answer_markdown="原解析", review="原点评",
    )
    session.add(question)
    session.flush()
    mirror = QuestionCurriculum(
        question_id=question.id, version_code=version, compulsory=compulsory,
        chapter=chapter, knowledge=knowledge,
    )
    session.add(mirror)
    session.commit()
    return question, mirror


def active_preset(monkeypatch, version):
    import main

    monkeypatch.setattr(main, "get_active_version_code", lambda: version)
    monkeypatch.setattr(main, "get_current_curriculum", lambda: load_curriculum(version))
    return main


@pytest.mark.parametrize("active_version", ["P", "A"])
@pytest.mark.parametrize("compulsory,chapter,knowledge", [
    ("必修第一册", "第一章 运动的描述", "第一章 运动的描述"),
    ("必修第一册", "第一章 运动的描述", "质点与参考系"),
    ("必修第一册", "第一章 运动的描述", "教研自定义：运动图像易错点"),
    ("历史自编教材", "自定义章名", "历史专题标签"),
    ("历史自编教材", "自定义章名", ""),
    ("历史自编教材", "自定义章名", None),
    ("必修二", "8. 立体几何初步", "8. 立体几何初步"),
    ("必修二", "8. 立体几何初步", "教研自定义：空间模型"),
])
def test_startup_preserves_stored_labels_and_physics_book_names(
    db_session, monkeypatch, active_version, compulsory, chapter, knowledge,
):
    main = active_preset(monkeypatch, active_version)
    # The main table follows the active preset; the independent P mirror must
    # remain physics even when an old mathematics preset is temporarily active.
    question, mirror = seed(db_session, compulsory, chapter, knowledge)
    original = (question.category_knowledge, mirror.knowledge)
    main.heal_database_curriculum_names()
    main.heal_database_curriculum_names()
    db_session.expire_all()
    expected_main_book = "必修一" if active_version == "A" and compulsory == "必修第一册" else compulsory
    assert (question.category_compulsory, question.category_chapter) == (expected_main_book, chapter)
    assert (mirror.compulsory, mirror.chapter, mirror.version_code) == (compulsory, chapter, "P")
    assert (question.category_knowledge, mirror.knowledge) == original
    assert question.content == r"物理原文 $\vec{F}=-2.00\,\mathrm{mN}$"
    assert question.question_type == "experiment"
    assert question.answer_markdown == "原解析" and question.review == "原点评"


@pytest.mark.parametrize("version", ["P", "A", "B", "S", "H"])
def test_legacy_startup_preserves_each_independent_curriculum(db_session, monkeypatch, version):
    main = active_preset(monkeypatch, "A")
    tree = load_curriculum(version)
    comp, chapter, knowledge = next(
        (comp, chapter, leaves[0]) for comp, chapters in tree.items()
        for chapter, leaves in chapters.items() if leaves
    )
    question, mirror = seed(db_session, comp, chapter, knowledge, version)
    main.heal_database_curriculum_names()
    db_session.expire_all()
    assert question.category_knowledge == mirror.knowledge == knowledge
    assert mirror.version_code == version
    if version == "P":
        assert mirror.compulsory == comp and mirror.chapter == chapter


def test_legacy_book_aliases_still_normalize_without_clearing_labels(db_session, monkeypatch):
    main = active_preset(monkeypatch, "A")
    question, mirror = seed(db_session, "必修第二册", "8. 立体几何初步", "历史章节标签", "A")
    main.heal_database_curriculum_names()
    db_session.expire_all()
    assert question.category_compulsory == mirror.compulsory == "必修二"
    assert question.category_knowledge == mirror.knowledge == "历史章节标签"


def test_legacy_alias_repair_does_not_rewrite_independent_physics_mirror(db_session, monkeypatch):
    main = active_preset(monkeypatch, "A")
    question, legacy = seed(db_session, "必修第二册", "8. 立体几何初步", "教师自定义", "A")
    physics = QuestionCurriculum(
        question_id=question.id, version_code="P", compulsory="必修第二册",
        chapter="第九章 静电场及其应用", knowledge="实验：探究电场力做功",
    )
    db_session.add(physics)
    db_session.commit()
    main.heal_database_curriculum_names()
    db_session.expire_all()
    assert question.category_compulsory == legacy.compulsory == "必修二"
    assert question.category_knowledge == legacy.knowledge == "教师自定义"
    assert (physics.compulsory, physics.chapter, physics.knowledge) == (
        "必修第二册", "第九章 静电场及其应用", "实验：探究电场力做功",
    )


@pytest.mark.parametrize("active_version", ["P", "A"])
def test_actual_post_startup_cleanup_preserves_custom_labels(db_session, monkeypatch, active_version):
    main = active_preset(monkeypatch, active_version)
    question, mirror = seed(db_session, "历史自编教材", "自定义章名", "物理实验：控制变量")
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(main, "create_full_backup_if_due", lambda: None)
    monkeypatch.setattr(main, "clean_orphaned_images", lambda: None)
    monkeypatch.setattr(main, "recalibrate_usage_counts", lambda: None)
    monkeypatch.setattr(main, "rebuild_all_missing_fingerprints", lambda *a, **kw: {"backfilled": 0})
    monkeypatch.setattr(main, "print_optional_tool_diagnostics", lambda: None)
    main.start_startup_cleanup()
    db_session.expire_all()
    assert question.category_knowledge == mirror.knowledge == "物理实验：控制变量"
