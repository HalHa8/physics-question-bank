"""Curriculum service; all application dependencies are explicit."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from mathbank.application_state import RuntimeState


@dataclass(frozen=True)
class CurriculumServiceDependencies:
    HTTPException: Any
    KnowledgePointCurriculum: Any
    Path: Any
    Question: Any
    QuestionCurriculum: Any
    QuestionKnowledgePoint: Any
    QuestionSubKnowledge: Any
    _save_metadata_config: Any
    and_: Any
    build_curriculum_routing_index: Any
    build_default_metadata: Any
    curriculum_filter_expression: Any
    detect_curriculum_version: Any
    get_active_version_code: Any
    get_current_curriculum: Any
    get_curriculum_preset: Any
    json: Any
    load_curriculum: Any
    normalize_sub_knowledge: Any
    os: Any
    route_chapter: Any
    route_curriculum_location: Any
    schedule_database_export: Any
    state: RuntimeState
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
    return dependencies.detect_curriculum_version(dependencies.state.METADATA_CACHE)


def get_metadata_config(*, dependencies: CurriculumServiceDependencies):
    return dependencies.state.METADATA_CACHE


def get_curriculum_preset_config(version: str, *, dependencies: CurriculumServiceDependencies):
    try:
        return dependencies.get_curriculum_preset(version)
    except ValueError as exc:
        raise dependencies.HTTPException(status_code=404, detail=str(exc)) from exc


def route_chapter(comp: str, chap: str, know: str, target: str, *, target_curriculum=None, routing_index=None, point_codes=(), dependencies: CurriculumServiceDependencies) -> tuple[str, str, str]:
    """Route only through exact directories and verified shared point paths."""
    if routing_index is None:
        if target_curriculum is None:
            if target == dependencies.get_active_version_code():
                target_curriculum = dependencies.state.METADATA_CACHE.get('curriculum', {})
            else:
                try:
                    target_curriculum = dependencies.load_curriculum(target)
                except ValueError:
                    return ('', '', '')
        routing_index = dependencies.build_curriculum_routing_index([], dependencies.get_active_version_code(), target, target_curriculum)
    return dependencies.route_curriculum_location(comp, chap, know, routing_index, point_codes=point_codes)


def save_metadata_config(payload: dict, background_tasks: BackgroundTasks, db: Session=Depends(get_db), *, dependencies: CurriculumServiceDependencies):
    with dependencies.state._METADATA_SAVE_LOCK:
        return dependencies._save_metadata_config(payload, background_tasks, db)


def curriculum_filter_expression(compulsory=None, chapter=None, knowledge=None, *, include_sub_knowledge=False, version_code=None, dependencies: CurriculumServiceDependencies):
    """Filter only the stored single-value classification, preserving relations."""
    if include_sub_knowledge:
        raise dependencies.HTTPException(status_code=400, detail='细分关系仅作为历史证据保留，请使用原单值小节筛选')
    fields = {'compulsory': compulsory, 'chapter': chapter, 'knowledge': knowledge}
    fields = {field: value for (field, value) in fields.items() if value}
    if not fields:
        return None
    return dependencies.and_(*(getattr(dependencies.Question, f'category_{field}') == value for (field, value) in fields.items()))


def apply_curriculum_filters(query, compulsory=None, chapter=None, knowledge=None, *, include_sub_knowledge=False, sub_knowledge=None, sub_knowledge_mode='any', version_code=None, dependencies: CurriculumServiceDependencies):
    expression = dependencies.curriculum_filter_expression(compulsory, chapter, knowledge, include_sub_knowledge=include_sub_knowledge, version_code=version_code)
    if expression is not None:
        query = query.filter(expression)
    if sub_knowledge_mode not in {'any', 'all'}:
        raise dependencies.HTTPException(status_code=400, detail='细分知识点筛选模式必须是 any 或 all')
    paths = dependencies.normalize_sub_knowledge(sub_knowledge if sub_knowledge is not None else [])
    if paths:
        raise dependencies.HTTPException(status_code=400, detail='细分关系仅作为历史证据保留，请使用原单值小节筛选')
    return query


def require_expected_curriculum_version(expected_version_code, *, dependencies: CurriculumServiceDependencies):
    if expected_version_code is not None:
        expected = str(expected_version_code).strip().upper()
        if expected != dependencies.get_active_version_code():
            raise dependencies.HTTPException(status_code=409, detail='教材版本已切换，请重新载入分类后保存')


def get_sub_knowledge_config(compulsory: str=None, chapter: str=None, knowledge: str=None, db: Session=Depends(get_db), *, dependencies: CurriculumServiceDependencies):
    version = dependencies.get_active_version_code()
    filters = {'compulsory': compulsory, 'chapter': chapter, 'knowledge': knowledge}
    paths = set()
    for (comp, chapters) in dependencies.get_current_curriculum().items():
        if not isinstance(chapters, dict):
            continue
        for (chap, leaves) in chapters.items():
            if not isinstance(leaves, list):
                continue
            for leaf in leaves:
                if isinstance(leaf, str) and leaf.strip():
                    paths.add((comp, chap, leaf))
    existing = set(db.query(dependencies.QuestionSubKnowledge.compulsory, dependencies.QuestionSubKnowledge.chapter, dependencies.QuestionSubKnowledge.knowledge).join(dependencies.QuestionCurriculum).filter(dependencies.QuestionCurriculum.version_code == version).all())
    paths.update(existing)

    def matching(path):
        return all((not value or path[index] == value for (index, value) in enumerate(filters.values())))

    def as_dict(path):
        return dict(zip(('compulsory', 'chapter', 'knowledge'), path))
    return {'version_code': version, 'sub_knowledge': [as_dict(path) for path in sorted(paths) if matching(path)], 'existing_sub_knowledge': [as_dict(path) for path in sorted(existing) if matching(path)]}


def _save_metadata_config(payload: dict, background_tasks: BackgroundTasks, db: Session, *, dependencies: CurriculumServiceDependencies):
    if not isinstance(payload, dict):
        raise dependencies.HTTPException(status_code=400, detail='请求 Payload 格式错误')
    for field in ['question_types', 'difficulties', 'curriculum']:
        if field not in payload:
            raise dependencies.HTTPException(status_code=400, detail=f"元数据配置缺少核心字段: '{field}'")
    if not isinstance(payload['question_types'], list) or not isinstance(payload['difficulties'], list):
        raise dependencies.HTTPException(status_code=400, detail='question_types 或 difficulties 必须是数组列表')
    if not isinstance(payload['curriculum'], dict):
        raise dependencies.HTTPException(status_code=400, detail='curriculum 必须是字典对象')
    try:
        target_version = dependencies.detect_curriculum_version(payload)
    except ValueError as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {**payload, 'curriculum_version': target_version}
    old_metadata = dependencies.state.METADATA_CACHE
    metadata_path = dependencies.Path(dependencies.state.METADATA_FILE)
    old_file_contents = metadata_path.read_text(encoding='utf-8') if metadata_path.exists() else None
    file_replaced = False
    transaction_committed = False
    switch_summary = None
    try:
        source_version = dependencies.get_active_version_code()
        if source_version != target_version:
            locations = db.query(dependencies.Question.id, dependencies.Question.category_compulsory, dependencies.Question.category_chapter, dependencies.Question.category_knowledge).all()
            mirrors = {(row.question_id, row.version_code): row for row in db.query(dependencies.QuestionCurriculum).filter(dependencies.QuestionCurriculum.version_code.in_((source_version, target_version))).all()}
            missing_ids = {row.id for row in locations if (row.id, target_version) not in mirrors}
            codes_by_question = {}
            if missing_ids:
                for (question_id, point_code) in db.query(dependencies.QuestionKnowledgePoint.question_id, dependencies.QuestionKnowledgePoint.point_code).filter(dependencies.QuestionKnowledgePoint.role == 'main').all():
                    if question_id in missing_ids:
                        codes_by_question.setdefault(question_id, []).append(point_code)
                catalog_paths = [{'point_code': row.point_code, **row.to_dict()} for row in db.query(dependencies.KnowledgePointCurriculum).filter(dependencies.KnowledgePointCurriculum.version_code.in_((source_version, target_version))).all()]
                from mathbank.knowledge_points import get_curriculum_ancestors
                routing_index = dependencies.build_curriculum_routing_index(catalog_paths, source_version, target_version, payload['curriculum'], target_ancestors=get_curriculum_ancestors(target_version))
            switch_summary = {'source_version': source_version, 'target_version': target_version, 'restored_existing': len(locations) - len(missing_ids), 'created': 0, 'section': 0, 'chapter': 0, 'unclassified': 0, 'preserved_source_mirrors': 0}
            source_snapshots = []
            for question in locations:
                source_map = mirrors.get((question.id, source_version))
                if source_map is None:
                    source_location = (question.category_compulsory, question.category_chapter, question.category_knowledge)
                    source_snapshots.append({'question_id': question.id, 'version_code': source_version, **dict(zip(('compulsory', 'chapter', 'knowledge'), source_location))})
                    switch_summary['preserved_source_mirrors'] += 1
                else:
                    source_location = (source_map.compulsory, source_map.chapter, source_map.knowledge)
                if question.id not in missing_ids:
                    continue
                (new_comp, new_chap, new_know) = dependencies.route_chapter(*source_location, target_version, routing_index=routing_index, point_codes=codes_by_question.get(question.id, ()))
                db.add(dependencies.QuestionCurriculum(question_id=question.id, version_code=target_version, compulsory=new_comp, chapter=new_chap, knowledge=new_know))
                switch_summary['created'] += 1
                switch_summary['section' if new_know else 'chapter' if new_chap else 'unclassified'] += 1
            if source_snapshots:
                db.execute(dependencies.QuestionCurriculum.__table__.insert(), source_snapshots)
        from sqlalchemy import text
        db.flush()
        db.execute(text('\n            UPDATE questions \n            SET category_compulsory = (SELECT compulsory FROM question_curriculums WHERE question_id = questions.id AND version_code = :v),\n                category_chapter = (SELECT chapter FROM question_curriculums WHERE question_id = questions.id AND version_code = :v),\n                category_knowledge = (SELECT knowledge FROM question_curriculums WHERE question_id = questions.id AND version_code = :v)\n            WHERE EXISTS (SELECT 1 FROM question_curriculums WHERE question_id = questions.id AND version_code = :v)\n        '), {'v': target_version})
        dependencies.write_private_text_atomic(metadata_path, dependencies.json.dumps(payload, ensure_ascii=False, indent=2))
        file_replaced = True
        db.commit()
        transaction_committed = True
    except Exception as e:
        db.rollback()
        if not transaction_committed:
            dependencies.state.METADATA_CACHE = old_metadata
        if file_replaced and (not transaction_committed):
            try:
                if old_file_contents is None:
                    metadata_path.unlink(missing_ok=True)
                else:
                    dependencies.write_private_text_atomic(metadata_path, old_file_contents)
            except OSError as restore_error:
                print(f'[Metadata] Failed to restore metadata after DB rollback (type={type(restore_error).__name__}).')
        raise dependencies.HTTPException(status_code=500, detail=f'保存元数据失败: {str(e)}')
    dependencies.state.METADATA_CACHE = payload
    print(f'[Metadata] Saved new custom metadata to {dependencies.state.METADATA_FILE} (Detected version: {target_version})')
    dependencies.schedule_database_export(background_tasks, operation='save_metadata')
    return {'status': 'success', 'message': '元数据配置保存成功！', 'curriculum_version': target_version, 'classification_switch': switch_summary}
