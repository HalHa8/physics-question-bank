"""Question commands; all application dependencies are explicit."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from mathbank.application_state import RuntimeState
from mathbank.database import Question
from mathbank.knowledge_points import normalize_question_points, replace_question_points


@dataclass(frozen=True)
class QuestionCommandsDependencies:
    AssetSecurityError: Any
    FIGURE_ALIGN_VALUES: Any
    FIGURE_SIZE_VALUES: Any
    HTTPException: Any
    JSONResponse: Any
    Paper: Any
    PaperQuestion: Any
    Path: Any
    Question: Any
    QuestionCurriculum: Any
    QuestionDuplicateInput: Any
    StoredQuestionFingerprint: Any
    _prompt_visible_image_paths: Any
    build_prepared_question_fingerprint: Any
    build_question_fingerprint: Any
    build_tikz_signatures: Any
    build_visible_image_signatures: Any
    committed_question_response: Any
    delete_unreferenced_question_assets: Any
    duplicate_review_required_response: Any
    embedded_question_assets: Any
    exact_duplicate_ids: Any
    get_active_version_code: Any
    get_seq_mapping: Any
    json: Any
    normalize_answer_tikz_assets: Any
    normalize_content_tikz_assets: Any
    normalize_figure_size: Any
    normalize_fillin_macro: Any
    normalize_optional_upload_asset_reference: Any
    normalize_question_points: Any
    normalize_sub_knowledge: Any
    normalize_upload_asset_references: Any
    prepare_project_import: Any
    prepare_question_assets: Any
    promote_question_temp_assets: Any
    question_summary_load_options: Any
    re: Any
    record_project_import: Any
    reference_payloads: Any
    refresh_reference_targets_for_labels: Any
    replace_question_points: Any
    require_expected_curriculum_version: Any
    rewrite_image_layout_paths: Any
    rewrite_question_asset_paths: Any
    rewrite_structured_asset_paths: Any
    rollback_question_asset_promotions: Any
    schedule_database_export: Any
    schedule_question_fingerprint_retry: Any
    select_answer_images: Any
    select_visible_question_images: Any
    state: RuntimeState
    structured_question_assets: Any
    sync_question_references: Any
    sync_question_source_labels: Any
    upsert_question_fingerprint: Any
    uuid: Any


def committed_question_response(db: Session, db_question: Question, question_id: int, *, operation: str, dependencies: QuestionCommandsDependencies) -> dict:
    """Serialize a committed write without ever misreporting it as failed."""
    try:
        db.refresh(db_question)
        seq_map = dependencies.get_seq_mapping(db, [question_id])
        question = db_question.to_dict(dependencies.get_active_version_code())
        question['question_references'] = dependencies.reference_payloads(db, [db_question]).get(question_id, [])
        question['version_code'] = dependencies.get_active_version_code()
        question['active_version_code'] = dependencies.get_active_version_code()
        question['seq_num'] = seq_map.get(question_id)
        return {'status': 'success', 'question': question}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f'[Question Write] Post-commit {operation} response degraded (type={type(exc).__name__}).')
        return {'status': 'success', 'question': {'id': question_id}}


def prepare_question_assets(content: str, answer_markdown: str, image_paths: str, content_tikz_assets: Optional[str], tikz_reference_image_path: str, answer_tikz_assets: str, tikz_code: str='', *, review: str='', promotion_log: list[tuple[Path, Path]], path_map: dict[str, str] | None=None, dependencies: QuestionCommandsDependencies) -> tuple[str, str, list[str], str, str, list[dict[str, str]], list[dict[str, str]]]:
    """Promote and validate all visible and AI-only assets in one policy path."""
    parsed_img_paths = dependencies.json.loads(image_paths) if image_paths else []
    if not isinstance(parsed_img_paths, list):
        raise dependencies.AssetSecurityError('image_paths 必须是插图路径数组。')
    parsed_img_paths.extend(dependencies.embedded_question_assets(review))
    parsed_img_paths.extend(dependencies.structured_question_assets(content_tikz_assets, answer_tikz_assets, legacy_reference=tikz_reference_image_path))
    replacements: dict[str, str] = {}
    (content, answer_markdown, parsed_img_paths) = dependencies.promote_question_temp_assets(content, answer_markdown, parsed_img_paths, promotion_log=promotion_log, path_map=replacements)
    if path_map is not None:
        path_map.update(replacements)
    content_tikz_assets = dependencies.rewrite_structured_asset_paths(content_tikz_assets, replacements)
    answer_tikz_assets = dependencies.rewrite_structured_asset_paths(answer_tikz_assets, replacements)
    tikz_reference_image_path = replacements.get(tikz_reference_image_path, tikz_reference_image_path)
    parsed_img_paths = dependencies.normalize_upload_asset_references(parsed_img_paths, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL)
    parsed_answer_tikz_assets = dependencies.normalize_answer_tikz_assets(answer_tikz_assets, allowed_image_paths=parsed_img_paths, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL)
    if content_tikz_assets is None:
        parsed_content_tikz_assets: list[dict[str, str]] = []
        parsed_tikz_code = str(tikz_code or '').strip()
        parsed_tikz_reference_image_path = dependencies.normalize_optional_upload_asset_reference(tikz_reference_image_path, allowed_image_paths=parsed_img_paths, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL)
    else:
        parsed_content_tikz_assets = dependencies.normalize_content_tikz_assets(content_tikz_assets, allowed_image_paths=parsed_img_paths, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL)
        first_content_asset = parsed_content_tikz_assets[0] if parsed_content_tikz_assets else {}
        parsed_tikz_code = str(first_content_asset.get('tikz_code') or '')
        parsed_tikz_reference_image_path = str(first_content_asset.get('reference_image_path') or '')
    return (content, answer_markdown, parsed_img_paths, parsed_tikz_code, parsed_tikz_reference_image_path, parsed_content_tikz_assets, parsed_answer_tikz_assets)


def build_prepared_question_fingerprint(*, content: str, answer_markdown: str, question_type: str, image_paths: list[str], content_tikz_assets: list[dict[str, str]], answer_tikz_assets: list[dict[str, str]], tikz_code: str, tikz_reference_image_path: str, review: str='', dependencies: QuestionCommandsDependencies):
    hidden_references = {str(tikz_reference_image_path or '').strip()}
    for asset in [*content_tikz_assets, *answer_tikz_assets]:
        if isinstance(asset, dict):
            hidden_references.add(str(asset.get('reference_image_path') or '').strip())
    hidden_references.discard('')
    registered_visible_paths = [path for path in image_paths if path not in hidden_references]
    visible_paths = dependencies.select_visible_question_images(content, answer_markdown, registered_visible_paths, content_tikz_assets, review=review)
    return dependencies.build_question_fingerprint(dependencies.QuestionDuplicateInput(content=content, answer_markdown=answer_markdown, question_type=question_type, visible_image_signatures=dependencies.build_visible_image_signatures(visible_paths, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL), tikz_signatures=dependencies.build_tikz_signatures(content_tikz_assets, tikz_code), answer_asset_signatures=dependencies.build_visible_image_signatures(dependencies.select_answer_images(answer_markdown, image_paths, answer_tikz_assets), uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL) + dependencies.build_tikz_signatures(answer_tikz_assets)))


def duplicate_review_required_response(db: Session, *, fingerprint, question_ids: list[int], message: str, code: str='duplicate_review_required', dependencies: QuestionCommandsDependencies):
    questions = db.query(dependencies.Question).filter(dependencies.Question.id.in_(question_ids)).all()
    seq_map = dependencies.get_seq_mapping(db, question_ids)
    return dependencies.JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "code": code,
            "message": message,
            "snapshot_hash": fingerprint.content_revision_hash,
            "candidates": [
                {
                    "id": question.id,
                    "seq_num": seq_map.get(question.id),
                    "content": str(question.content or "")[:500],
                    "content_truncated": len(str(question.content or "")) > 500,
                    "source": question.source or "",
                    "question_type": question.question_type or "",
                    "image_paths": dependencies._prompt_visible_image_paths(question)[:4],
                }
                for question in questions
            ],
        },
    )


def create_question(background_tasks: BackgroundTasks, content: str=Form(...), question_type: str=Form(...), category_compulsory: str=Form(''), category_chapter: str=Form(''), category_knowledge: str=Form(''), sub_knowledge: str=Form('[]'), knowledge_points: Optional[str]=Form(None), expected_version_code: Optional[str]=Form(None), difficulty: str=Form(...), source: str=Form(''), answer_markdown: str=Form(''), review: str=Form(''), tikz_code: str=Form(''), content_tikz_assets: Optional[str]=Form(None), tikz_reference_image_path: str=Form(''), answer_tikz_assets: str=Form('[]'), figure_align: str=Form('right'), figure_align_custom: bool=Form(False), figure_size: str=Form('auto'), image_layouts: str=Form('{}'), tags: str=Form(''), related_question_id: str=Form(''), image_paths: str=Form('[]'), duplicate_snapshot_hash: str=Form(''), duplicate_override: str=Form(''), import_project_id: str=Form(''), import_card_id: str=Form(''), import_draft_revision: Optional[int]=Form(None), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    dependencies.require_expected_curriculum_version(expected_version_code)
    asset_promotions: list[tuple[dependencies.Path, dependencies.Path]] = []
    asset_path_map: dict[str, str] = {}
    duplicate_warning = ''
    project_digest = None
    try:
        (project_digest, existing_question_id) = dependencies.prepare_project_import(db, dependencies.state.DOCUMENT_PROJECTS, import_project_id, import_card_id, import_draft_revision, {'content': content, 'answer_markdown': answer_markdown, 'question_type': question_type, 'difficulty': difficulty, 'source': source, 'review': review, 'image_paths': image_paths, 'category_compulsory': category_compulsory, 'category_chapter': category_chapter, 'category_knowledge': category_knowledge, 'tikz_code': tikz_code, 'tikz_reference_image_path': tikz_reference_image_path, 'content_tikz_assets': content_tikz_assets, 'answer_tikz_assets': answer_tikz_assets, 'figure_align': figure_align, 'figure_size': figure_size, 'figure_align_custom': figure_align_custom, 'image_layouts': image_layouts, 'tags': tags, 'related_question_id': related_question_id, 'sub_knowledge': sub_knowledge, 'knowledge_points': knowledge_points})
        if existing_question_id is not None:
            return dependencies.committed_question_response(db, db.get(dependencies.Question, existing_question_id), existing_question_id, operation='project_import_replay')
        parsed_sub_knowledge = dependencies.normalize_sub_knowledge(sub_knowledge)
        parsed_knowledge_points = dependencies.normalize_question_points(dependencies.json.loads(knowledge_points) if knowledge_points is not None else [], db)
        duplicate_snapshot_hash = str(duplicate_snapshot_hash or '').strip()
        duplicate_override = str(duplicate_override or '').strip()
        if duplicate_override not in {'', 'independent'}:
            raise ValueError('无效的查重处理方式')
        if duplicate_override and (not duplicate_snapshot_hash):
            raise ValueError('独立保存确认缺少题目快照')
        if duplicate_snapshot_hash and (not dependencies.re.fullmatch('[0-9a-f]{64}', duplicate_snapshot_hash)):
            raise ValueError('查重题目快照格式无效')
        figure_size = str(figure_size or '').strip()
        if figure_size not in dependencies.FIGURE_SIZE_VALUES:
            raise ValueError('无效的插图尺寸')
        content = dependencies.normalize_fillin_macro(content)
        (content, answer_markdown, parsed_img_paths, parsed_tikz_code, parsed_tikz_reference_image_path, parsed_content_tikz_assets, parsed_answer_tikz_assets) = dependencies.prepare_question_assets(content, answer_markdown, image_paths, content_tikz_assets, tikz_reference_image_path, answer_tikz_assets, tikz_code, review=review, promotion_log=asset_promotions, path_map=asset_path_map)
        review = dependencies.rewrite_question_asset_paths(review, asset_path_map)
        db_question = dependencies.Question(content=content, question_type=question_type, category_compulsory=category_compulsory, category_chapter=category_chapter, category_knowledge=category_knowledge, difficulty=difficulty, source=source, answer_markdown=answer_markdown, review=review, tikz_code=parsed_tikz_code, tikz_reference_image_path=parsed_tikz_reference_image_path, figure_align=figure_align if figure_align in dependencies.FIGURE_ALIGN_VALUES else 'right', figure_align_custom=bool(figure_align_custom), figure_size=figure_size, tags=tags)
        db_question.image_layouts = dependencies.rewrite_image_layout_paths(image_layouts, asset_path_map)
        db_question.image_paths = parsed_img_paths
        db_question.content_tikz_assets = parsed_content_tikz_assets
        db_question.answer_tikz_assets = parsed_answer_tikz_assets
        related_id_int = int(related_question_id) if related_question_id and related_question_id.strip() else None
        if related_id_int:
            q_related = db.query(dependencies.Question).filter(dependencies.Question.id == related_id_int).first()
            if q_related:
                g2 = q_related.association_group_id
                if not g2:
                    new_grp = str(dependencies.uuid.uuid4())
                    q_related.association_group_id = new_grp
                    db_question.association_group_id = new_grp
                else:
                    db_question.association_group_id = g2
        db.add(db_question)
        db.flush()
        try:
            question_fingerprint = dependencies.build_prepared_question_fingerprint(content=content, answer_markdown=answer_markdown, question_type=question_type, image_paths=parsed_img_paths, content_tikz_assets=parsed_content_tikz_assets, answer_tikz_assets=parsed_answer_tikz_assets, tikz_code=parsed_tikz_code, tikz_reference_image_path=parsed_tikz_reference_image_path, review=review)
        except Exception as fingerprint_exc:
            question_fingerprint = None
            duplicate_warning = '题目已保存，但本次查重指纹未生成；后台将尝试补建，失败时下次启动继续。'
            print(f'[Duplicate Index] Create fingerprint failed open (type={type(fingerprint_exc).__name__}); background backfill will retry.')
        if duplicate_snapshot_hash and question_fingerprint is not None:
            if duplicate_snapshot_hash != question_fingerprint.content_revision_hash:
                response = dependencies.duplicate_review_required_response(db, fingerprint=question_fingerprint, question_ids=[], message='题目在查重后已发生变化，请重新查重后保存。', code='duplicate_snapshot_stale')
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
            exact_ids = dependencies.exact_duplicate_ids(db, question_fingerprint, exclude_id=db_question.id)
            if exact_ids and duplicate_override != 'independent':
                response = dependencies.duplicate_review_required_response(db, fingerprint=question_fingerprint, question_ids=exact_ids, message='入库前发现新的疑似已收录题，请核对后再决定。')
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
        if question_fingerprint is not None:
            dependencies.upsert_question_fingerprint(db, db_question, question_fingerprint)
        active_version = dependencies.get_active_version_code()
        curriculum_map = dependencies.QuestionCurriculum(question_id=db_question.id, version_code=active_version, compulsory=category_compulsory, chapter=category_chapter, knowledge=category_knowledge)
        curriculum_map.sub_knowledge = parsed_sub_knowledge
        db.add(curriculum_map)
        dependencies.replace_question_points(db_question, parsed_knowledge_points, db)
        dependencies.sync_question_source_labels(db, db_question)
        dependencies.sync_question_references(db, db_question)
        committed_question_id = db_question.id
        dependencies.record_project_import(db, project_id=import_project_id, card_id=import_card_id, revision=import_draft_revision, digest=project_digest, question_id=committed_question_id)
        db.commit()
    except dependencies.HTTPException:
        db.rollback()
        dependencies.rollback_question_asset_promotions(asset_promotions)
        raise
    except Exception as e:
        db.rollback()
        dependencies.rollback_question_asset_promotions(asset_promotions)
        raise dependencies.HTTPException(status_code=400, detail=f'保存题目失败: {str(e)}')
    dependencies.schedule_database_export(background_tasks, operation='create_question')
    if duplicate_warning:
        dependencies.schedule_question_fingerprint_retry(background_tasks, question_id=committed_question_id, operation='create_question')
    response = dependencies.committed_question_response(db, db_question, committed_question_id, operation='create_question')
    if duplicate_warning:
        response['warning'] = duplicate_warning
    if asset_path_map:
        response['asset_path_map'] = asset_path_map
    return response



def update_question(question_id: int, background_tasks: BackgroundTasks, content: str=Form(...), question_type: str=Form(...), category_compulsory: str=Form(''), category_chapter: str=Form(''), category_knowledge: str=Form(''), sub_knowledge: Optional[str]=Form(None), knowledge_points: Optional[str]=Form(None), expected_version_code: Optional[str]=Form(None), difficulty: str=Form(...), source: str=Form(''), answer_markdown: str=Form(''), review: str=Form(''), tikz_code: str=Form(''), content_tikz_assets: Optional[str]=Form(None), tikz_reference_image_path: str=Form(''), answer_tikz_assets: str=Form('[]'), figure_align: str=Form('right'), figure_align_custom: Optional[bool]=Form(None), figure_size: Optional[str]=Form(None), image_layouts: Optional[str]=Form(None), tags: str=Form(''), related_question_id: str=Form(''), image_paths: str=Form('[]'), duplicate_snapshot_hash: str=Form(''), duplicate_override: str=Form(''), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    dependencies.require_expected_curriculum_version(expected_version_code)
    db_question = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not db_question:
        raise dependencies.HTTPException(status_code=404, detail='未找到对应的题目')
    asset_promotions: list[tuple[dependencies.Path, dependencies.Path]] = []
    asset_path_map: dict[str, str] = {}
    duplicate_warning = ''
    old_images = list(db_question.image_paths)
    try:
        parsed_sub_knowledge = dependencies.normalize_sub_knowledge(sub_knowledge) if sub_knowledge is not None else None
        parsed_knowledge_points = dependencies.normalize_question_points(dependencies.json.loads(knowledge_points), db) if knowledge_points is not None else None
        duplicate_snapshot_hash = str(duplicate_snapshot_hash or '').strip()
        duplicate_override = str(duplicate_override or '').strip()
        if duplicate_override not in {'', 'independent'}:
            raise ValueError('无效的查重处理方式')
        if duplicate_override and (not duplicate_snapshot_hash):
            raise ValueError('独立保存确认缺少题目快照')
        if duplicate_snapshot_hash and (not dependencies.re.fullmatch('[0-9a-f]{64}', duplicate_snapshot_hash)):
            raise ValueError('查重题目快照格式无效')
        if figure_size is not None:
            figure_size = str(figure_size).strip()
            if figure_size not in dependencies.FIGURE_SIZE_VALUES:
                raise ValueError('无效的插图尺寸')
        content = dependencies.normalize_fillin_macro(content)
        (content, answer_markdown, parsed_img_paths, parsed_tikz_code, parsed_tikz_reference_image_path, parsed_content_tikz_assets, parsed_answer_tikz_assets) = dependencies.prepare_question_assets(content, answer_markdown, image_paths, content_tikz_assets, tikz_reference_image_path, answer_tikz_assets, tikz_code, review=review, promotion_log=asset_promotions, path_map=asset_path_map)
        review = dependencies.rewrite_question_asset_paths(review, asset_path_map)
        db_question.content = content
        db_question.question_type = question_type
        db_question.category_compulsory = category_compulsory
        db_question.category_chapter = category_chapter
        db_question.category_knowledge = category_knowledge
        db_question.difficulty = difficulty
        db_question.source = source
        db_question.answer_markdown = answer_markdown
        db_question.review = review
        db_question.tikz_code = parsed_tikz_code
        db_question.tikz_reference_image_path = parsed_tikz_reference_image_path
        if figure_align in dependencies.FIGURE_ALIGN_VALUES:
            db_question.figure_align = figure_align
        if figure_align_custom is not None:
            db_question.figure_align_custom = bool(figure_align_custom)
        if figure_size is not None:
            db_question.figure_size = figure_size
        db_question.tags = tags
        removed_images = set(old_images) - set(parsed_img_paths)
        db_question.image_layouts = dependencies.rewrite_image_layout_paths(image_layouts if image_layouts is not None else db_question.image_layouts, asset_path_map)
        db_question.image_paths = parsed_img_paths
        db_question.content_tikz_assets = parsed_content_tikz_assets
        db_question.answer_tikz_assets = parsed_answer_tikz_assets
        related_id_int = int(related_question_id) if related_question_id and related_question_id.strip() else None
        if related_id_int:
            q_related = db.query(dependencies.Question).filter(dependencies.Question.id == related_id_int).first()
            if q_related and q_related.id != db_question.id:
                g1 = db_question.association_group_id
                g2 = q_related.association_group_id
                if not g1 and (not g2):
                    new_grp = str(dependencies.uuid.uuid4())
                    db_question.association_group_id = new_grp
                    q_related.association_group_id = new_grp
                elif g1 and (not g2):
                    q_related.association_group_id = g1
                elif not g1 and g2:
                    db_question.association_group_id = g2
                elif g1 != g2:
                    db.query(dependencies.Question).filter(dependencies.Question.association_group_id == g1).update({dependencies.Question.association_group_id: g2}, synchronize_session=False)
                    db_question.association_group_id = g2
        active_version = dependencies.get_active_version_code()
        curriculum_map = db.query(dependencies.QuestionCurriculum).filter(dependencies.QuestionCurriculum.question_id == db_question.id, dependencies.QuestionCurriculum.version_code == active_version).first()
        if not curriculum_map:
            curriculum_map = dependencies.QuestionCurriculum(question_id=db_question.id, version_code=active_version)
            db.add(curriculum_map)
        curriculum_map.compulsory = category_compulsory
        curriculum_map.chapter = category_chapter
        curriculum_map.knowledge = category_knowledge
        if parsed_sub_knowledge is not None:
            curriculum_map.sub_knowledge = parsed_sub_knowledge
        if parsed_knowledge_points is not None:
            dependencies.replace_question_points(db_question, parsed_knowledge_points, db)
        db.flush()
        try:
            question_fingerprint = dependencies.build_prepared_question_fingerprint(content=content, answer_markdown=answer_markdown, question_type=question_type, image_paths=parsed_img_paths, content_tikz_assets=parsed_content_tikz_assets, answer_tikz_assets=parsed_answer_tikz_assets, tikz_code=parsed_tikz_code, tikz_reference_image_path=parsed_tikz_reference_image_path, review=review)
        except Exception as fingerprint_exc:
            question_fingerprint = None
            duplicate_warning = '题目已更新，但本次查重指纹未生成；后台将尝试补建，失败时下次启动继续。'
            db.query(dependencies.StoredQuestionFingerprint).filter(dependencies.StoredQuestionFingerprint.question_id == db_question.id).delete(synchronize_session=False)
            print(f'[Duplicate Index] Update fingerprint failed open (type={type(fingerprint_exc).__name__}); background backfill will retry.')
        if duplicate_snapshot_hash and question_fingerprint is not None:
            if duplicate_snapshot_hash != question_fingerprint.content_revision_hash:
                response = dependencies.duplicate_review_required_response(db, fingerprint=question_fingerprint, question_ids=[], message='题目在查重后已发生变化，请重新查重后保存。', code='duplicate_snapshot_stale')
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
            exact_ids = dependencies.exact_duplicate_ids(db, question_fingerprint, exclude_id=db_question.id)
            if exact_ids and duplicate_override != 'independent':
                response = dependencies.duplicate_review_required_response(db, fingerprint=question_fingerprint, question_ids=exact_ids, message='更新后的题目与题库已有题相同，请核对后再决定。')
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
        if question_fingerprint is not None:
            dependencies.upsert_question_fingerprint(db, db_question, question_fingerprint)
        dependencies.sync_question_source_labels(db, db_question)
        dependencies.sync_question_references(db, db_question)
        db.commit()
    except Exception as e:
        db.rollback()
        dependencies.rollback_question_asset_promotions(asset_promotions)
        raise dependencies.HTTPException(status_code=400, detail=f'更新题目失败: {str(e)}')
    try:
        dependencies.delete_unreferenced_question_assets(db, removed_images)
    except Exception as cleanup_exc:
        print(f'[Storage Cleanup] Post-commit update cleanup failed (type={type(cleanup_exc).__name__}); it will be retried by the startup orphan cleanup.')
    dependencies.schedule_database_export(background_tasks, operation='update_question')
    if duplicate_warning:
        dependencies.schedule_question_fingerprint_retry(background_tasks, question_id=question_id, operation='update_question')
    response = dependencies.committed_question_response(db, db_question, question_id, operation='update_question')
    if duplicate_warning:
        response['warning'] = duplicate_warning
    if asset_path_map:
        response['asset_path_map'] = asset_path_map
    return response



def update_question_figure_align(question_id: int, background_tasks: BackgroundTasks, figure_align: str=Form('right'), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    db_question = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not db_question:
        raise dependencies.HTTPException(status_code=404, detail="未找到对应的题目")
    if figure_align not in dependencies.FIGURE_ALIGN_VALUES:
        figure_align = "right"
    db_question.figure_align = figure_align
    db_question.figure_align_custom = True
    db.commit()
    db.refresh(db_question)
    dependencies.schedule_database_export(background_tasks, operation="update_figure_align")
    return {
        "status": "success",
        "question_id": question_id,
        "figure_align": figure_align,
        "figure_align_custom": True,
    }


def update_question_figure_layout(question_id: int, background_tasks: BackgroundTasks, figure_align: str=Form(...), figure_size: str=Form(...), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    db_question = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not db_question:
        raise dependencies.HTTPException(status_code=404, detail="未找到对应的题目")
    if figure_align not in dependencies.FIGURE_ALIGN_VALUES:
        raise dependencies.HTTPException(status_code=400, detail="无效的插图排版位置")
    figure_size = str(figure_size or "").strip()
    if figure_size not in dependencies.FIGURE_SIZE_VALUES:
        raise dependencies.HTTPException(status_code=400, detail="无效的插图尺寸")
    db_question.figure_align = figure_align
    db_question.figure_align_custom = True
    db_question.figure_size = figure_size
    db.commit()
    db.refresh(db_question)
    dependencies.schedule_database_export(background_tasks, operation="update_figure_layout")
    return {
        "status": "success",
        "question_id": question_id,
        "figure_align": db_question.figure_align,
        "figure_align_custom": True,
        "figure_size": dependencies.normalize_figure_size(db_question.figure_size),
    }


def get_associated_questions(question_id: int, db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    q = db.query(dependencies.Question.id, dependencies.Question.association_group_id).filter(dependencies.Question.id == question_id).first()
    if not q:
        raise dependencies.HTTPException(status_code=404, detail='未找到题目')
    grp = q.association_group_id
    if not grp or grp.strip() == '':
        return []
    associated = db.query(dependencies.Question).options(*dependencies.question_summary_load_options()).filter(dependencies.Question.association_group_id == grp, dependencies.Question.id != question_id).all()
    seq_map = dependencies.get_seq_mapping(db, [item.id for item in associated])
    refs_by_id = dependencies.reference_payloads(db, associated)
    return [{**item.to_summary_dict(dependencies.get_active_version_code(), compact_knowledge_points=True), 'question_references': refs_by_id.get(item.id, []), 'seq_num': seq_map.get(item.id)} for item in associated]


def associate_questions_endpoint(background_tasks: BackgroundTasks, question_id: int, target_id: int=Form(...), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    q1 = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    q2 = db.query(dependencies.Question).filter(dependencies.Question.id == target_id).first()
    if not q1 or not q2:
        raise dependencies.HTTPException(status_code=404, detail="未找到对应题目")

    if q1.id == q2.id:
        raise dependencies.HTTPException(status_code=400, detail="不能自己和自己关联")

    g1 = q1.association_group_id
    g2 = q2.association_group_id

    try:
        if not g1 and not g2:
            new_grp = str(dependencies.uuid.uuid4())
            q1.association_group_id = new_grp
            q2.association_group_id = new_grp
        elif g1 and not g2:
            q2.association_group_id = g1
        elif not g1 and g2:
            q1.association_group_id = g2
        else:
            if g1 != g2:
                db.query(dependencies.Question).filter(dependencies.Question.association_group_id == g1).update(
                    {dependencies.Question.association_group_id: g2}, synchronize_session=False
                )
                q1.association_group_id = g2

        db.commit()

        # Auto export database to files for Git synchronization and AI referencing (Async Background Task)
        dependencies.schedule_database_export(background_tasks, operation="associate_questions")

        return {"status": "success", "message": "关联成功"}
    except Exception as e:
        db.rollback()
        raise dependencies.HTTPException(status_code=400, detail=f"关联失败: {str(e)}")


def remove_association(question_id: int, background_tasks: BackgroundTasks, db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    """Remove a question from its association group (bidirectional)."""
    q = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not q:
        raise dependencies.HTTPException(status_code=404, detail="未找到题目")

    grp = q.association_group_id
    if not grp or grp.strip() == "":
        return {"status": "success", "message": "该题目无关联关系"}

    try:
        # Clear this question's group ID
        q.association_group_id = ""

        # If only one other question remains in the group, clear its group too (no point in a group of one)
        remaining = db.query(dependencies.Question).filter(
            dependencies.Question.association_group_id == grp,
            dependencies.Question.id != question_id
        ).all()

        if len(remaining) == 1:
            remaining[0].association_group_id = ""

        db.commit()

        # Auto export database to files for Git synchronization and AI referencing (Async Background Task)
        dependencies.schedule_database_export(background_tasks, operation="remove_association")

        return {"status": "success", "message": "已成功解除所有关联"}
    except Exception as e:
        db.rollback()
        raise dependencies.HTTPException(status_code=400, detail=f"解除关联失败: {str(e)}")


def delete_question(question_id: int, background_tasks: BackgroundTasks, db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    db_question = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not db_question:
        raise dependencies.HTTPException(status_code=404, detail='未找到对应的题目')
    image_paths_to_check = list(db_question.image_paths)
    try:
        from sqlalchemy import func
        from mathbank.database import QuestionSourceLabel
        affected_reference_labels = {(row.book_key, row.label_key) for row in db.query(QuestionSourceLabel).filter_by(question_id=question_id)}
        affected_paper_ids = [paper_id for (paper_id,) in db.query(dependencies.PaperQuestion.paper_id).filter(dependencies.PaperQuestion.question_id == question_id).distinct().all()]
        if affected_paper_ids:
            remaining_scores = dict(db.query(dependencies.PaperQuestion.paper_id, func.coalesce(func.sum(dependencies.PaperQuestion.score), 0)).filter(dependencies.PaperQuestion.paper_id.in_(affected_paper_ids), dependencies.PaperQuestion.question_id != question_id).group_by(dependencies.PaperQuestion.paper_id).all())
            for paper in db.query(dependencies.Paper).filter(dependencies.Paper.id.in_(affected_paper_ids)):
                paper.total_score = int(remaining_scores.get(paper.id, 0))
        db.delete(db_question)
        db.flush()
        dependencies.refresh_reference_targets_for_labels(db, affected_reference_labels)
        db.commit()
    except Exception as e:
        db.rollback()
        raise dependencies.HTTPException(status_code=400, detail=f'删除题目失败: {str(e)}')
    try:
        dependencies.delete_unreferenced_question_assets(db, image_paths_to_check)
    except Exception as cleanup_exc:
        print(f'[Storage Cleanup] Post-commit delete cleanup failed (type={type(cleanup_exc).__name__}); it will be retried by the startup orphan cleanup.')
    dependencies.schedule_database_export(background_tasks, operation='delete_question')
    return {'status': 'success', 'message': '题目删除成功'}
