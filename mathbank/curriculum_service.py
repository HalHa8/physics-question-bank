"""Curriculum service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Depends, BackgroundTasks
from sqlalchemy.orm import Session
from mathbank.database import get_db


@dataclass(frozen=True)
class CurriculumServiceDependencies:
    state: RuntimeState
    HTTPException: Any
    Path: Any
    Question: Any
    QuestionCurriculum: Any
    build_default_metadata: Any
    get_active_version_code: Callable
    get_curriculum_preset: Any
    json: Any
    load_curriculum: Any
    os: Any
    route_chapter: Callable
    schedule_database_export: Callable
    write_private_text_atomic: Any


def get_current_curriculum(*, dependencies: CurriculumServiceDependencies):
    return dependencies.state.METADATA_CACHE.get("curriculum", dependencies.state.PHYSICS_CURRICULUM)


def load_or_init_metadata(*, dependencies: CurriculumServiceDependencies):
    pass  # State lives on the application instance.
    default_metadata = dependencies.build_default_metadata("P")

    # Ensure backup directory exists
    dependencies.os.makedirs(dependencies.os.path.dirname(dependencies.state.METADATA_FILE), exist_ok=True)

    if dependencies.os.path.exists(dependencies.state.METADATA_FILE):
        try:
            with open(dependencies.state.METADATA_FILE, "r", encoding="utf-8") as f:
                loaded = dependencies.json.load(f)
                # Verify schema
                if isinstance(loaded, dict) and "question_types" in loaded and "difficulties" in loaded and "curriculum" in loaded:
                    # Self-heal metadata file (e.g. add 常规题, update simplified book names)
                    modified = False
                    has_normal = any(d.get("value") == "normal" for d in loaded.get("difficulties", []))
                    if not has_normal:
                        loaded["difficulties"].insert(1, {"value": "normal", "label": "常规题", "color": "text-blue-600 bg-blue-50 border-blue-200"})
                        modified = True

                    curriculum = loaded.get("curriculum", {})
                    combined_loaded_chapters = " ".join(
                        " ".join(chapters.keys())
                        for chapters in curriculum.values()
                        if isinstance(chapters, dict)
                    )
                    is_physics_curriculum = any(
                        marker in combined_loaded_chapters
                        for marker in ("运动的描述", "静电场", "电磁感应", "原子核")
                    )
                    mappings = {} if is_physics_curriculum else {
                        "选择性必修一": "选修一",
                        "选择性必修二": "选修二",
                        "选择性必修三": "选修三",
                        "必修第一册": "必修一",
                        "必修第二册": "必修二",
                        "必修第三册": "必修三",
                        "必修第四册": "必修四",
                    }
                    new_curriculum = {}
                    for comp, chapters in curriculum.items():
                        mapped_comp = mappings.get(comp, comp)
                        if mapped_comp != comp:
                            modified = True
                        new_curriculum[mapped_comp] = chapters
                    if modified:
                        loaded["curriculum"] = new_curriculum
                        try:
                            dependencies.write_private_text_atomic(
                                dependencies.state.METADATA_FILE,
                                dependencies.json.dumps(loaded, ensure_ascii=False, indent=2),
                            )
                            print(f"[Metadata Self-Heal] Upgraded {dependencies.state.METADATA_FILE} with simplified book names and normal difficulty.")
                        except Exception as e:
                            print(f"[Metadata Self-Heal Error] Failed to write updated metadata: {e}")

                    dependencies.state.METADATA_CACHE = loaded
                    print(f"[Metadata] Loaded custom metadata from {dependencies.state.METADATA_FILE}")
                    return
        except Exception as e:
            print(f"[Metadata Warning] Error loading {dependencies.state.METADATA_FILE}: {e}. Overwriting with default.")

    # Self-heal / initialize
    try:
        dependencies.write_private_text_atomic(
            dependencies.state.METADATA_FILE,
            dependencies.json.dumps(default_metadata, ensure_ascii=False, indent=2),
        )
        print(f"[Metadata] Initialized default metadata at {dependencies.state.METADATA_FILE}")
    except Exception as e:
        print(f"[Metadata Error] Could not write default metadata: {e}")

    dependencies.state.METADATA_CACHE = default_metadata


def get_active_version_code(*, dependencies: CurriculumServiceDependencies) -> str:
    curriculum = dependencies.state.METADATA_CACHE.get("curriculum", {})
    combined_chapters = ""
    for book_content in curriculum.values():
        if isinstance(book_content, dict):
            combined_chapters += " ".join(book_content.keys())
    physics_markers = ("运动的描述", "运动和力的关系", "静电场", "电磁感应", "原子核")
    if any(marker in combined_chapters for marker in physics_markers):
        return "P"
    if "第一章" in combined_chapters:
        return "B"
    if "第 1 章 集合与逻辑" in combined_chapters or "数学建模活动案例" in combined_chapters or "第 2 章 等式与不等式" in combined_chapters or "第 3 章 幂、指数与对数" in combined_chapters:
        return "H"
    if "第1章" in combined_chapters:
        return "S"
    return "A"


def get_metadata_config(*, dependencies: CurriculumServiceDependencies):
    return dependencies.state.METADATA_CACHE


def get_curriculum_preset_config(version: str, *, dependencies: CurriculumServiceDependencies):
    try:
        return dependencies.get_curriculum_preset(version)
    except ValueError as exc:
        raise dependencies.HTTPException(status_code=404, detail=str(exc)) from exc


def route_chapter(comp: str, chap: str, know: str, target: str, *, dependencies: CurriculumServiceDependencies) -> tuple[str, str, str]:
    """跨大纲版本智能章节与小节路由翻译算法，返回 (new_compulsory, new_chapter, new_knowledge)"""
    combined = f"{comp} {chap} {know}"
    new_comp, new_chap = "", ""
    if target == "P":
        c_tree = dependencies.state.METADATA_CACHE.get("curriculum", dependencies.state.PHYSICS_CURRICULUM)
        if comp in c_tree and chap in c_tree.get(comp, {}):
            valid_knows = c_tree[comp][chap]
            return comp, chap, know if know in valid_knows else ""
        # A safe fallback for legacy/unclassified data. AI classification can
        # refine this later; do not pretend a mathematics chapter maps exactly.
        new_comp, new_chap = "必修第一册", "第一章 运动的描述"
    elif target == "A":
        if "集合" in combined: new_comp, new_chap = "必修一", "1. 集合与常用逻辑用语"
        elif "逻辑" in combined: new_comp, new_chap = "必修一", "1. 集合与常用逻辑用语"
        elif "等式" in combined or "不等式" in combined: new_comp, new_chap = "必修一", "2. 一元二次函数、方程和不等式"
        elif "指数" in combined or "对数" in combined: new_comp, new_chap = "必修一", "4. 指数函数与对数函数"
        elif "三角函数" in combined or "三角恒等" in combined: new_comp, new_chap = "必修一", "5. 三角函数"
        elif "函数" in combined: new_comp, new_chap = "必修一", "3. 函数的概念与性质"
        elif "解三角形" in combined or "正弦" in combined or "余弦" in combined: new_comp, new_chap = "必修二", "6. 平面向量及其应用"
        elif "数量积" in combined or "平面向量" in combined: new_comp, new_chap = "必修二", "6. 平面向量及其应用"
        elif "复数" in combined: new_comp, new_chap = "必修二", "7. 复数"
        elif "立体几何" in combined and "空间向量" not in combined: new_comp, new_chap = "必修二", "8. 立体几何初步"
        elif "空间向量" in combined: new_comp, new_chap = "选修一", "1. 空间向量与立体几何"
        elif "直线" in combined or "圆的方程" in combined: new_comp, new_chap = "选修一", "2. 直线和圆的方程"
        elif "圆" in combined and "圆锥曲线" not in combined: new_comp, new_chap = "选修一", "2. 直线和圆的方程"
        elif "圆锥曲线" in combined or "椭圆" in combined or "双曲线" in combined or "抛物线" in combined: new_comp, new_chap = "选修一", "3. 圆锥曲线的方程"
        elif "解析几何" in combined: new_comp, new_chap = "选修一", "2. 直线和圆的方程"
        elif "数列" in combined: new_comp, new_chap = "选修二", "4. 数列"
        elif "导数" in combined: new_comp, new_chap = "选修二", "5. 一元函数的导数及其应用"
        elif "计数" in combined or "排列" in combined or "组合" in combined or "二项式" in combined: new_comp, new_chap = "选修三", "6. 计数原理"
        elif "概率" in combined or "随机变量" in combined or "分布" in combined: new_comp, new_chap = "选修三", "7. 随机变量及其分布"
        elif "统计" in combined or "回归" in combined or "独立性" in combined or "成对" in combined: new_comp, new_chap = "选修三", "8. 成对数据的统计分析"
        else: new_comp, new_chap = "必修一", "1. 集合与常用逻辑用语"
    elif target == "B":
        if "集合" in combined: new_comp, new_chap = "必修一", "第一章 集合与常用逻辑用语"
        elif "逻辑" in combined: new_comp, new_chap = "必修一", "第一章 集合与常用逻辑用语"
        elif "等式" in combined or "不等式" in combined: new_comp, new_chap = "必修一", "第二章 等式与不等式"
        elif "指数" in combined or "对数" in combined: new_comp, new_chap = "必修二", "第四章 指数函数、对数函数与幂函数"
        elif "三角函数" in combined: new_comp, new_chap = "必修三", "第七章 三角函数"
        elif "函数" in combined: new_comp, new_chap = "必修一", "第三章 函数"
        elif "解三角形" in combined or "正弦" in combined or "余弦" in combined: new_comp, new_chap = "必修四", "第九章 解三角形"
        elif "数量积" in combined or "三角恒等" in combined: new_comp, new_chap = "必修三", "第八章 向量的数量积与三角恒等变换"
        elif "平面向量" in combined: new_comp, new_chap = "必修二", "第六章 平面向量初步"
        elif "复数" in combined: new_comp, new_chap = "必修四", "第十章 复数"
        elif "立体几何" in combined and "空间向量" not in combined: new_comp, new_chap = "必修四", "第十一章 立体几何初步"
        elif "空间向量" in combined: new_comp, new_chap = "选修一", "第一章 空间向量与立体几何"
        elif "直线" in combined or "圆" in combined or "圆锥曲线" in combined or "椭圆" in combined or "双曲线" in combined or "抛物线" in combined: new_comp, new_chap = "选修一", "第二章 平面解析几何"
        elif "解析几何" in combined: new_comp, new_chap = "选修一", "第二章 平面解析几何"
        elif "数列" in combined: new_comp, new_chap = "选修三", "第五章 数列"
        elif "导数" in combined: new_comp, new_chap = "选修三", "第六章 导数及其应用"
        elif "计数" in combined or "排列" in combined or "组合" in combined or "二项式" in combined: new_comp, new_chap = "选修二", "第三章 排列、组合与二项式定理"
        elif "随机变量" in combined or "条件概率" in combined or "回归" in combined or "独立性" in combined or "成对" in combined: new_comp, new_chap = "选修二", "第四章 概率与统计"
        elif "统计" in combined or "概率" in combined: new_comp, new_chap = "必修二", "第五章 统计与概率"
        else: new_comp, new_chap = "必修一", "第一章 集合与常用逻辑用语"
    elif target == "S":
        if "集合" in combined: new_comp, new_chap = "必修一", "第1章 集合"
        elif "逻辑" in combined: new_comp, new_chap = "必修一", "第2章 常用逻辑用语"
        elif "等式" in combined or "不等式" in combined: new_comp, new_chap = "必修一", "第3章 不等式"
        elif "指数" in combined or "对数" in combined: new_comp, new_chap = "必修一", "第4章 指数与对数"
        elif "三角函数" in combined: new_comp, new_chap = "必修一", "第7章 三角函数"
        elif "函数" in combined: new_comp, new_chap = "必修一", "第5章 函数概念与性质"
        elif "解三角形" in combined or "正弦" in combined or "余弦" in combined: new_comp, new_chap = "必修二", "第11章 解三角形"
        elif "数量积" in combined or "平面向量" in combined: new_comp, new_chap = "必修二", "第9章 平面向量"
        elif "三角恒等" in combined: new_comp, new_chap = "必修二", "第10章 三角恒等变换"
        elif "复数" in combined: new_comp, new_chap = "必修二", "第12章 复数"
        elif "立体几何" in combined and "空间向量" not in combined: new_comp, new_chap = "必修二", "第13章 立体几何初步"
        elif "空间向量" in combined: new_comp, new_chap = "选修二", "第6章 空间向量与立体几何"
        elif "直线" in combined: new_comp, new_chap = "选修一", "第1章 直线与方程"
        elif "圆" in combined and "圆锥曲线" not in combined: new_comp, new_chap = "选修一", "第2章 圆与方程"
        elif "圆锥曲线" in combined or "椭圆" in combined or "双曲线" in combined or "抛物线" in combined: new_comp, new_chap = "选修一", "第3章 圆锥曲线与方程"
        elif "解析几何" in combined: new_comp, new_chap = "选修一", "第1章 直线与方程"
        elif "数列" in combined: new_comp, new_chap = "选修一", "第4章 数列"
        elif "导数" in combined: new_comp, new_chap = "选修一", "第5章 导数及其应用"
        elif "计数" in combined or "排列" in combined or "组合" in combined or "二项式" in combined: new_comp, new_chap = "选修二", "第7章 计数原理"
        elif "随机变量" in combined or "条件概率" in combined: new_comp, new_chap = "选修二", "第8章 概率"
        elif "回归" in combined or "独立性" in combined or "成对" in combined: new_comp, new_chap = "选修二", "第9章 统计"
        elif "统计" in combined: new_comp, new_chap = "必修二", "第14章 统计"
        elif "概率" in combined: new_comp, new_chap = "必修二", "第15章 概率"
        else: new_comp, new_chap = "必修一", "第1章 集合"
    elif target == "H":
        if "集合与逻辑" in combined or ("集合" in combined and "选修" not in comp): new_comp, new_chap = "必修一", "第 1 章 集合与逻辑"
        elif "等式" in combined or "不等式" in combined: new_comp, new_chap = "必修一", "第 2 章 等式与不等式"
        elif "幂、指数" in combined or "指数与对数" in combined or ("指数" in combined and "函数" not in combined) or ("对数" in combined and "函数" not in combined): new_comp, new_chap = "必修一", "第 3 章 幂、指数与对数"
        elif "幂函数" in combined or "指数函数" in combined or "对数函数" in combined: new_comp, new_chap = "必修一", "第 4 章 幂函数、指数函数与对数函数"
        elif "反函数" in combined or "函数的概念" in combined or ("函数" in combined and "三角" not in combined and "导数" not in combined and "选修" not in comp and "必修二" not in comp and "必修三" not in comp): new_comp, new_chap = "必修一", "第 5 章 函数的概念、性质及应用"
        elif "解三角形" in combined or "正弦定理" in combined or "余弦定理" in combined or "常用三角公式" in combined or ("三角" in combined and "函数" not in combined): new_comp, new_chap = "必修二", "第 6 章 三角"
        elif "三角函数" in combined: new_comp, new_chap = "必修二", "第 7 章 三角函数"
        elif "平面向量" in combined or ("向量" in combined and "空间" not in combined): new_comp, new_chap = "必修二", "第 8 章 平面向量"
        elif "复数" in combined: new_comp, new_chap = "必修二", "第 9 章 复数"
        elif "空间直线" in combined or "空间点" in combined or ("立体几何" in combined and "空间向量" not in combined and "简单几何体" not in combined and "球" not in combined and "柱体" not in combined and "锥体" not in combined): new_comp, new_chap = "必修三", "第 10 章 空间直线与平面"
        elif "简单几何体" in combined or "柱体" in combined or "锥体" in combined or "多面体" in combined or "球" in combined: new_comp, new_chap = "必修三", "第 11 章 简单几何体"
        elif "古典概" in combined or "随机现象" in combined or ("概率" in combined and "条件概率" not in combined and "随机变量" not in combined and "分布" not in combined and "选修" not in comp): new_comp, new_chap = "必修三", "第 12 章 概率初步"
        elif "总体与样本" in combined or "抽样" in combined or "统计图表" in combined or ("统计" in combined and "成对" not in combined and "回归" not in combined and "列联表" not in combined and "选修" not in comp): new_comp, new_chap = "必修三", "第 13 章 统计"
        elif "红绿灯" in combined or "优惠券" in combined or "车辆转弯" in combined or "雨中行" in combined or "出租车" in combined or "家具" in combined or "登山" in combined or "包装彩带" in combined or "削菠萝" in combined or "高度测量" in combined or "外卖" in combined or "必修四" in comp: new_comp, new_chap = "必修四", "第 1 部分 数学建模活动案例"
        elif "平面直角坐标系中的直线" in combined or "直线与方程" in combined or ("直线" in combined and "空间" not in combined and "圆锥曲线" not in combined): new_comp, new_chap = "选修一", "第 1 章 平面直角坐标系中的直线"
        elif "圆锥曲线" in combined or "椭圆" in combined or "双曲线" in combined or "抛物线" in combined or ("圆" in combined and "圆锥曲线" in combined): new_comp, new_chap = "选修一", "第 2 章 圆锥曲线"
        elif "空间向量" in combined: new_comp, new_chap = "选修一", "第 3 章 空间向量及其应用"
        elif "数列" in combined or "等差数列" in combined or "等比数列" in combined or "数学归纳法" in combined: new_comp, new_chap = "选修一", "第 4 章 数列"
        elif "导数" in combined: new_comp, new_chap = "选修二", "第 5 章 导数及其应用"
        elif "计数原理" in combined or "排列" in combined or "组合" in combined or "二项式" in combined: new_comp, new_chap = "选修二", "第 6 章 计数原理"
        elif "条件概率" in combined or "随机变量" in combined or "常用分布" in combined or "二项分布" in combined or "正态分布" in combined: new_comp, new_chap = "选修二", "第 7 章 概率初步（续）"
        elif "成对数据" in combined or "线性回归" in combined or "列联表" in combined or "独立性检验" in combined or "回归" in combined: new_comp, new_chap = "选修二", "第 8 章 成对数据的统计分析"
        elif "刹车距离" in combined or "易拉罐" in combined or "珠穆朗玛峰" in combined or "水葫芦" in combined or "铅球" in combined or "电梯调度" in combined or "存款计划" in combined or "民生巨变" in combined or "教室里的照明" in combined or "选修三" in comp: new_comp, new_chap = "选修三", "第 1 部分 数学建模活动案例"
        else: new_comp, new_chap = "必修一", "第 1 章 集合与逻辑"

    active_v = dependencies.get_active_version_code()
    if target == active_v:
        c_tree = dependencies.state.METADATA_CACHE.get("curriculum", {})
    else:
        try:
            c_tree = dependencies.load_curriculum(target)
        except ValueError:
            c_tree = {}

    valid_knows = c_tree.get(new_comp, {}).get(new_chap, [])
    new_know = know if know in valid_knows else ""
    return new_comp, new_chap, new_know


def save_metadata_config(payload: dict, background_tasks: BackgroundTasks, db: Session=Depends(get_db), *, dependencies: CurriculumServiceDependencies):
    pass  # State lives on the application instance.
    # Validation
    if not isinstance(payload, dict):
        raise dependencies.HTTPException(status_code=400, detail="请求 Payload 格式错误")

    for field in ["question_types", "difficulties", "curriculum"]:
        if field not in payload:
            raise dependencies.HTTPException(status_code=400, detail=f"元数据配置缺少核心字段: '{field}'")

    # Simple validate question_types and difficulties lists
    if not isinstance(payload["question_types"], list) or not isinstance(payload["difficulties"], list):
        raise dependencies.HTTPException(status_code=400, detail="question_types 或 difficulties 必须是数组列表")

    if not isinstance(payload["curriculum"], dict):
        raise dependencies.HTTPException(status_code=400, detail="curriculum 必须是字典对象")

    old_metadata = dependencies.state.METADATA_CACHE
    metadata_path = dependencies.Path(dependencies.state.METADATA_FILE)
    old_file_contents = (
        metadata_path.read_text(encoding="utf-8") if metadata_path.exists() else None
    )
    file_replaced = False
    transaction_committed = False

    # Update the curriculum mirror and metadata as one compensated operation.
    try:
        source_version = dependencies.get_active_version_code()
        # Detect target version
        curriculum = payload.get("curriculum", {})
        combined_chapters = ""
        for book_content in curriculum.values():
            if isinstance(book_content, dict):
                combined_chapters += " ".join(book_content.keys())
        physics_markers = ("运动的描述", "运动和力的关系", "静电场", "电磁感应", "原子核")
        if any(marker in combined_chapters for marker in physics_markers):
            target_version = "P"
        elif "第一章" in combined_chapters:
            target_version = "B"
        elif "第 1 章 集合与逻辑" in combined_chapters or "数学建模活动案例" in combined_chapters or "第 2 章 等式与不等式" in combined_chapters or "第 3 章 幂、指数与对数" in combined_chapters:
            target_version = "H"
        elif "第1章" in combined_chapters:
            target_version = "S"
        else:
            target_version = "A"

        # Incremental migration if curriculum version shifts
        if source_version != target_version:
            # Check and run incremental migration for all questions that do not have classifications for target_version
            all_questions = db.query(dependencies.Question).all()
            for q in all_questions:
                target_map = db.query(dependencies.QuestionCurriculum).filter(
                    dependencies.QuestionCurriculum.question_id == q.id,
                    dependencies.QuestionCurriculum.version_code == target_version
                ).first()
                if not target_map or not target_map.compulsory:
                    source_map = db.query(dependencies.QuestionCurriculum).filter(
                        dependencies.QuestionCurriculum.question_id == q.id,
                        dependencies.QuestionCurriculum.version_code == source_version
                    ).first()
                    if source_map and source_map.compulsory:
                        new_comp, new_chap, new_know = dependencies.route_chapter(
                            source_map.compulsory, source_map.chapter, source_map.knowledge, target_version
                        )
                        if not target_map:
                            target_map = dependencies.QuestionCurriculum(
                                question_id=q.id,
                                version_code=target_version
                            )
                            db.add(target_map)
                        target_map.compulsory = new_comp
                        target_map.chapter = new_chap
                        target_map.knowledge = new_know
        # Batch update main questions table categories with target version values
        from sqlalchemy import text
        db.flush()
        db.execute(text("""
            UPDATE questions\x20
            SET category_compulsory = COALESCE((SELECT compulsory FROM question_curriculums WHERE question_id = questions.id AND version_code = :v), ''),
                category_chapter = COALESCE((SELECT chapter FROM question_curriculums WHERE question_id = questions.id AND version_code = :v), ''),
                category_knowledge = COALESCE((SELECT knowledge FROM question_curriculums WHERE question_id = questions.id AND version_code = :v), '')
        """), {"v": target_version})

        dependencies.write_private_text_atomic(
            metadata_path,
            dependencies.json.dumps(payload, ensure_ascii=False, indent=2),
        )
        file_replaced = True
        db.commit()
        transaction_committed = True
    except Exception as e:
        db.rollback()
        if not transaction_committed:
            dependencies.state.METADATA_CACHE = old_metadata
        if file_replaced and not transaction_committed:
            try:
                if old_file_contents is None:
                    metadata_path.unlink(missing_ok=True)
                else:
                    dependencies.write_private_text_atomic(metadata_path, old_file_contents)
            except OSError as restore_error:
                print(
                    "[Metadata] Failed to restore metadata after DB rollback "
                    f"(type={type(restore_error).__name__})."
                )
        raise dependencies.HTTPException(status_code=500, detail=f"保存元数据失败: {str(e)}")

    # Everything below is post-commit and must not change the successful save
    # into an error response or compensate already-durable database changes.
    dependencies.state.METADATA_CACHE = payload
    print(
        f"[Metadata] Saved new custom metadata to {dependencies.state.METADATA_FILE} "
        f"(Detected version: {target_version})"
    )
    dependencies.schedule_database_export(background_tasks, operation="save_metadata")
    return {"status": "success", "message": "元数据配置保存成功！"}
