"""Question commands; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from pathlib import Path
from typing import Optional
from fastapi import Depends, Form, BackgroundTasks
from sqlalchemy.orm import Session
from mathbank.database import Question, get_db


@dataclass(frozen=True)
class QuestionCommandsDependencies:
    state: RuntimeState
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
    _prompt_visible_image_paths: Callable
    build_prepared_question_fingerprint: Callable
    build_question_fingerprint: Any
    build_tikz_signatures: Any
    build_visible_image_signatures: Any
    committed_question_response: Callable
    delete_unreferenced_question_assets: Callable
    duplicate_review_required_response: Callable
    exact_duplicate_ids: Any
    get_active_version_code: Callable
    get_seq_mapping: Callable
    json: Any
    normalize_answer_tikz_assets: Any
    normalize_content_tikz_assets: Any
    normalize_figure_size: Any
    normalize_fillin_macro: Any
    normalize_optional_upload_asset_reference: Any
    normalize_upload_asset_references: Any
    prepare_question_assets: Callable
    promote_question_temp_assets: Callable
    re: Any
    rollback_question_asset_promotions: Callable
    schedule_database_export: Callable
    schedule_question_fingerprint_retry: Callable
    select_answer_images: Any
    select_visible_question_images: Any
    upsert_question_fingerprint: Any
    uuid: Any


def committed_question_response(db: Session, db_question: Question, question_id: int, *, operation: str, dependencies: QuestionCommandsDependencies) -> dict:
    """Serialize a committed write without ever misreporting it as failed."""

    try:
        db.refresh(db_question)
        seq_map = dependencies.get_seq_mapping(db, [question_id])
        question = db_question.to_dict()
        question["seq_num"] = seq_map.get(question_id)
        return {"status": "success", "question": question}
    except Exception as exc:
        # The durable transaction is already complete.  End any failed read
        # transaction and return enough identity for the client to continue;
        # a later list/detail refresh can obtain the full representation.
        try:
            db.rollback()
        except Exception:
            pass
        print(
            f"[Question Write] Post-commit {operation} response degraded "
            f"(type={type(exc).__name__})."
        )
        return {"status": "success", "question": {"id": question_id}}


def prepare_question_assets(content: str, answer_markdown: str, image_paths: str, content_tikz_assets: Optional[str], tikz_reference_image_path: str, answer_tikz_assets: str, tikz_code: str='', *, promotion_log: list[tuple[Path, Path]], dependencies: QuestionCommandsDependencies) -> tuple[
    str,
    str,
    list[str],
    str,
    str,
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Promote and validate all visible and AI-only assets in one policy path."""

    parsed_img_paths = dependencies.json.loads(image_paths) if image_paths else []
    content, answer_markdown, parsed_img_paths = dependencies.promote_question_temp_assets(
        content,
        answer_markdown,
        parsed_img_paths,
        promotion_log=promotion_log,
    )
    parsed_img_paths = dependencies.normalize_upload_asset_references(
        parsed_img_paths,
        uploads_dir=dependencies.state.UPLOAD_DIR,
        url_prefix=dependencies.state.UPLOAD_DIR_REL,
    )
    parsed_answer_tikz_assets = dependencies.normalize_answer_tikz_assets(
        answer_tikz_assets,
        allowed_image_paths=parsed_img_paths,
        uploads_dir=dependencies.state.UPLOAD_DIR,
        url_prefix=dependencies.state.UPLOAD_DIR_REL,
    )
    if content_tikz_assets is None:
        # Compatibility for clients and existing drafts created before v5.
        parsed_content_tikz_assets: list[dict[str, str]] = []
        parsed_tikz_code = str(tikz_code or "").strip()
        parsed_tikz_reference_image_path = dependencies.normalize_optional_upload_asset_reference(
            tikz_reference_image_path,
            allowed_image_paths=parsed_img_paths,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
        )
    else:
        parsed_content_tikz_assets = dependencies.normalize_content_tikz_assets(
            content_tikz_assets,
            allowed_image_paths=parsed_img_paths,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
        )
        first_content_asset = (
            parsed_content_tikz_assets[0] if parsed_content_tikz_assets else {}
        )
        parsed_tikz_code = str(first_content_asset.get("tikz_code") or "")
        parsed_tikz_reference_image_path = str(
            first_content_asset.get("reference_image_path") or ""
        )
    return (
        content,
        answer_markdown,
        parsed_img_paths,
        parsed_tikz_code,
        parsed_tikz_reference_image_path,
        parsed_content_tikz_assets,
        parsed_answer_tikz_assets,
    )


def build_prepared_question_fingerprint(*, content: str, answer_markdown: str, question_type: str, image_paths: list[str], content_tikz_assets: list[dict[str, str]], answer_tikz_assets: list[dict[str, str]], tikz_code: str, tikz_reference_image_path: str, dependencies: QuestionCommandsDependencies):
    hidden_references = {str(tikz_reference_image_path or "").strip()}
    for asset in [*content_tikz_assets, *answer_tikz_assets]:
        if isinstance(asset, dict):
            hidden_references.add(str(asset.get("reference_image_path") or "").strip())
    hidden_references.discard("")
    registered_visible_paths = [
        path for path in image_paths if path not in hidden_references
    ]
    visible_paths = dependencies.select_visible_question_images(
        content,
        answer_markdown,
        registered_visible_paths,
        content_tikz_assets,
    )
    return dependencies.build_question_fingerprint(
        dependencies.QuestionDuplicateInput(
            content=content,
            answer_markdown=answer_markdown,
            question_type=question_type,
            visible_image_signatures=dependencies.build_visible_image_signatures(
                visible_paths,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            ),
            tikz_signatures=dependencies.build_tikz_signatures(
                content_tikz_assets,
                tikz_code,
            ),
            answer_asset_signatures=(
                dependencies.build_visible_image_signatures(
                    dependencies.select_answer_images(
                        answer_markdown,
                        image_paths,
                        answer_tikz_assets,
                    ),
                    uploads_dir=dependencies.state.UPLOAD_DIR,
                    url_prefix=dependencies.state.UPLOAD_DIR_REL,
                )
                + dependencies.build_tikz_signatures(answer_tikz_assets)
            ),
        )
    )


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


def create_question(background_tasks: BackgroundTasks, content: str=Form(...), question_type: str=Form(...), category_compulsory: str=Form(''), category_chapter: str=Form(''), category_knowledge: str=Form(''), difficulty: str=Form(...), source: str=Form(''), answer_markdown: str=Form(''), review: str=Form(''), tikz_code: str=Form(''), content_tikz_assets: Optional[str]=Form(None), tikz_reference_image_path: str=Form(''), answer_tikz_assets: str=Form('[]'), figure_align: str=Form('right'), figure_align_custom: bool=Form(False), figure_size: str=Form('auto'), image_layouts: str=Form('{}'), tags: str=Form(''), related_question_id: str=Form(''), image_paths: str=Form('[]'), duplicate_snapshot_hash: str=Form(''), duplicate_override: str=Form(''), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    asset_promotions: list[tuple[dependencies.Path, dependencies.Path]] = []
    duplicate_warning = ""
    try:
        duplicate_snapshot_hash = str(duplicate_snapshot_hash or "").strip()
        duplicate_override = str(duplicate_override or "").strip()
        if duplicate_override not in {"", "independent"}:
            raise ValueError("无效的查重处理方式")
        if duplicate_override and not duplicate_snapshot_hash:
            raise ValueError("独立保存确认缺少题目快照")
        if duplicate_snapshot_hash and not dependencies.re.fullmatch(
            r"[0-9a-f]{64}", duplicate_snapshot_hash
        ):
            raise ValueError("查重题目快照格式无效")
        figure_size = str(figure_size or "").strip()
        if figure_size not in dependencies.FIGURE_SIZE_VALUES:
            raise ValueError("无效的插图尺寸")
        # 规范化填空题下划线为 \fillin 宏
        content = dependencies.normalize_fillin_macro(content)

        (
            content,
            answer_markdown,
            parsed_img_paths,
            parsed_tikz_code,
            parsed_tikz_reference_image_path,
            parsed_content_tikz_assets,
            parsed_answer_tikz_assets,
        ) = dependencies.prepare_question_assets(
            content,
            answer_markdown,
            image_paths,
            content_tikz_assets,
            tikz_reference_image_path,
            answer_tikz_assets,
            tikz_code,
            promotion_log=asset_promotions,
        )

        # 1. Fallback if third level is empty, default to chapter
        if not category_knowledge and category_chapter:
            category_knowledge = category_chapter

        db_question = dependencies.Question(
            content=content,
            question_type=question_type,
            category_compulsory=category_compulsory,
            category_chapter=category_chapter,
            category_knowledge=category_knowledge,
            difficulty=difficulty,
            source=source,
            answer_markdown=answer_markdown,
            review=review,
            tikz_code=parsed_tikz_code,
            tikz_reference_image_path=parsed_tikz_reference_image_path,
            figure_align=figure_align if figure_align in dependencies.FIGURE_ALIGN_VALUES else "right",
            figure_align_custom=bool(figure_align_custom),
            figure_size=figure_size,
            tags=tags
        )
        db_question.image_layouts = image_layouts
        db_question.image_paths = parsed_img_paths
        db_question.content_tikz_assets = parsed_content_tikz_assets
        db_question.answer_tikz_assets = parsed_answer_tikz_assets

        # Handle related question association (transitive relation)
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
            question_fingerprint = dependencies.build_prepared_question_fingerprint(
                content=content,
                answer_markdown=answer_markdown,
                question_type=question_type,
                image_paths=parsed_img_paths,
                content_tikz_assets=parsed_content_tikz_assets,
                answer_tikz_assets=parsed_answer_tikz_assets,
                tikz_code=parsed_tikz_code,
                tikz_reference_image_path=parsed_tikz_reference_image_path,
            )
        except Exception as fingerprint_exc:
            question_fingerprint = None
            duplicate_warning = "题目已保存，但本次查重指纹未生成；后台将尝试补建，失败时下次启动继续。"
            print(
                "[Duplicate Index] Create fingerprint failed open "
                f"(type={type(fingerprint_exc).__name__}); background backfill will retry."
            )
        if duplicate_snapshot_hash and question_fingerprint is not None:
            if duplicate_snapshot_hash != question_fingerprint.content_revision_hash:
                response = dependencies.duplicate_review_required_response(
                    db,
                    fingerprint=question_fingerprint,
                    question_ids=[],
                    message="题目在查重后已发生变化，请重新查重后保存。",
                    code="duplicate_snapshot_stale",
                )
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
            exact_ids = dependencies.exact_duplicate_ids(
                db,
                question_fingerprint,
                exclude_id=db_question.id,
            )
            if exact_ids and duplicate_override != "independent":
                response = dependencies.duplicate_review_required_response(
                    db,
                    fingerprint=question_fingerprint,
                    question_ids=exact_ids,
                    message="入库前发现新的疑似已收录题，请核对后再决定。",
                )
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
        if question_fingerprint is not None:
            dependencies.upsert_question_fingerprint(db, db_question, question_fingerprint)

        # Save the question and its active curriculum mirror atomically.
        active_version = dependencies.get_active_version_code()
        curriculum_map = dependencies.QuestionCurriculum(
            question_id=db_question.id,
            version_code=active_version,
            compulsory=category_compulsory,
            chapter=category_chapter,
            knowledge=category_knowledge
        )
        db.add(curriculum_map)
        committed_question_id = db_question.id
        db.commit()
    except Exception as e:
        db.rollback()
        dependencies.rollback_question_asset_promotions(asset_promotions)
        raise dependencies.HTTPException(status_code=400, detail=f"保存题目失败: {str(e)}")

    # Everything below is compensating or response work after the durable
    # success boundary; none of it may turn the write into a misleading 400.
    dependencies.schedule_database_export(background_tasks, operation="create_question")
    if duplicate_warning:
        dependencies.schedule_question_fingerprint_retry(
            background_tasks,
            question_id=committed_question_id,
            operation="create_question",
        )
    response = dependencies.committed_question_response(
        db,
        db_question,
        committed_question_id,
        operation="create_question",
    )
    if duplicate_warning:
        response["warning"] = duplicate_warning
    return response


def update_question(question_id: int, background_tasks: BackgroundTasks, content: str=Form(...), question_type: str=Form(...), category_compulsory: str=Form(''), category_chapter: str=Form(''), category_knowledge: str=Form(''), difficulty: str=Form(...), source: str=Form(''), answer_markdown: str=Form(''), review: str=Form(''), tikz_code: str=Form(''), content_tikz_assets: Optional[str]=Form(None), tikz_reference_image_path: str=Form(''), answer_tikz_assets: str=Form('[]'), figure_align: str=Form('right'), figure_align_custom: Optional[bool]=Form(None), figure_size: Optional[str]=Form(None), image_layouts: Optional[str]=Form(None), tags: str=Form(''), related_question_id: str=Form(''), image_paths: str=Form('[]'), duplicate_snapshot_hash: str=Form(''), duplicate_override: str=Form(''), db: Session=Depends(get_db), *, dependencies: QuestionCommandsDependencies):
    db_question = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not db_question:
        raise dependencies.HTTPException(status_code=404, detail="未找到对应的题目")

    asset_promotions: list[tuple[dependencies.Path, dependencies.Path]] = []
    duplicate_warning = ""
    old_images = list(db_question.image_paths)
    try:
        duplicate_snapshot_hash = str(duplicate_snapshot_hash or "").strip()
        duplicate_override = str(duplicate_override or "").strip()
        if duplicate_override not in {"", "independent"}:
            raise ValueError("无效的查重处理方式")
        if duplicate_override and not duplicate_snapshot_hash:
            raise ValueError("独立保存确认缺少题目快照")
        if duplicate_snapshot_hash and not dependencies.re.fullmatch(
            r"[0-9a-f]{64}", duplicate_snapshot_hash
        ):
            raise ValueError("查重题目快照格式无效")
        if figure_size is not None:
            figure_size = str(figure_size).strip()
            if figure_size not in dependencies.FIGURE_SIZE_VALUES:
                raise ValueError("无效的插图尺寸")
        # 规范化填空题下划线为 \fillin 宏
        content = dependencies.normalize_fillin_macro(content)

        (
            content,
            answer_markdown,
            parsed_img_paths,
            parsed_tikz_code,
            parsed_tikz_reference_image_path,
            parsed_content_tikz_assets,
            parsed_answer_tikz_assets,
        ) = dependencies.prepare_question_assets(
            content,
            answer_markdown,
            image_paths,
            content_tikz_assets,
            tikz_reference_image_path,
            answer_tikz_assets,
            tikz_code,
            promotion_log=asset_promotions,
        )

        # 1. Fallback if third level is empty, default to chapter
        if not category_knowledge and category_chapter:
            category_knowledge = category_chapter

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
        # Physical cleanup happens only after the database commit succeeds.
        removed_images = set(old_images) - set(parsed_img_paths)

        db_question.image_layouts = image_layouts if image_layouts is not None else db_question.image_layouts
        db_question.image_paths = parsed_img_paths
        db_question.content_tikz_assets = parsed_content_tikz_assets
        db_question.answer_tikz_assets = parsed_answer_tikz_assets

        # Handle related question association updates (transitive relation)
        related_id_int = int(related_question_id) if related_question_id and related_question_id.strip() else None
        if related_id_int:
            q_related = db.query(dependencies.Question).filter(dependencies.Question.id == related_id_int).first()
            if q_related and q_related.id != db_question.id:
                g1 = db_question.association_group_id
                g2 = q_related.association_group_id

                if not g1 and not g2:
                    new_grp = str(dependencies.uuid.uuid4())
                    db_question.association_group_id = new_grp
                    q_related.association_group_id = new_grp
                elif g1 and not g2:
                    q_related.association_group_id = g1
                elif not g1 and g2:
                    db_question.association_group_id = g2
                else:
                    if g1 != g2:
                        db.query(dependencies.Question).filter(dependencies.Question.association_group_id == g1).update(
                            {dependencies.Question.association_group_id: g2}, synchronize_session=False
                        )
                        db_question.association_group_id = g2

        # Update or create active QuestionCurriculum mapping
        active_version = dependencies.get_active_version_code()
        curriculum_map = db.query(dependencies.QuestionCurriculum).filter(
            dependencies.QuestionCurriculum.question_id == db_question.id,
            dependencies.QuestionCurriculum.version_code == active_version
        ).first()
        if not curriculum_map:
            curriculum_map = dependencies.QuestionCurriculum(
                question_id=db_question.id,
                version_code=active_version
            )
            db.add(curriculum_map)
        curriculum_map.compulsory = category_compulsory
        curriculum_map.chapter = category_chapter
        curriculum_map.knowledge = category_knowledge

        db.flush()
        try:
            question_fingerprint = dependencies.build_prepared_question_fingerprint(
                content=content,
                answer_markdown=answer_markdown,
                question_type=question_type,
                image_paths=parsed_img_paths,
                content_tikz_assets=parsed_content_tikz_assets,
                answer_tikz_assets=parsed_answer_tikz_assets,
                tikz_code=parsed_tikz_code,
                tikz_reference_image_path=parsed_tikz_reference_image_path,
            )
        except Exception as fingerprint_exc:
            question_fingerprint = None
            duplicate_warning = "题目已更新，但本次查重指纹未生成；后台将尝试补建，失败时下次启动继续。"
            db.query(dependencies.StoredQuestionFingerprint).filter(
                dependencies.StoredQuestionFingerprint.question_id == db_question.id
            ).delete(synchronize_session=False)
            print(
                "[Duplicate Index] Update fingerprint failed open "
                f"(type={type(fingerprint_exc).__name__}); background backfill will retry."
            )
        if duplicate_snapshot_hash and question_fingerprint is not None:
            if duplicate_snapshot_hash != question_fingerprint.content_revision_hash:
                response = dependencies.duplicate_review_required_response(
                    db,
                    fingerprint=question_fingerprint,
                    question_ids=[],
                    message="题目在查重后已发生变化，请重新查重后保存。",
                    code="duplicate_snapshot_stale",
                )
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
            exact_ids = dependencies.exact_duplicate_ids(
                db,
                question_fingerprint,
                exclude_id=db_question.id,
            )
            if exact_ids and duplicate_override != "independent":
                response = dependencies.duplicate_review_required_response(
                    db,
                    fingerprint=question_fingerprint,
                    question_ids=exact_ids,
                    message="更新后的题目与题库已有题相同，请核对后再决定。",
                )
                db.rollback()
                dependencies.rollback_question_asset_promotions(asset_promotions)
                return response
        if question_fingerprint is not None:
            dependencies.upsert_question_fingerprint(db, db_question, question_fingerprint)

        db.commit()
    except Exception as e:
        db.rollback()
        dependencies.rollback_question_asset_promotions(asset_promotions)
        raise dependencies.HTTPException(status_code=400, detail=f"更新题目失败: {str(e)}")

    # The question is already durably updated at this point.  Best-effort
    # cleanup and response assembly must not turn success into a false failure.
    try:
        dependencies.delete_unreferenced_question_assets(db, removed_images)
    except Exception as cleanup_exc:
        print(
            "[Storage Cleanup] Post-commit update cleanup failed "
            f"(type={type(cleanup_exc).__name__}); it will be retried by "
            "the startup orphan cleanup."
        )
    dependencies.schedule_database_export(background_tasks, operation="update_question")
    if duplicate_warning:
        dependencies.schedule_question_fingerprint_retry(
            background_tasks,
            question_id=question_id,
            operation="update_question",
        )
    response = dependencies.committed_question_response(
        db,
        db_question,
        question_id,
        operation="update_question",
    )
    if duplicate_warning:
        response["warning"] = duplicate_warning
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
    q = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not q:
        raise dependencies.HTTPException(status_code=404, detail="未找到题目")

    grp = q.association_group_id
    if not grp or grp.strip() == "":
        return []

    associated = db.query(dependencies.Question).filter(
        dependencies.Question.association_group_id == grp,
        dependencies.Question.id != question_id
    ).all()

    seq_map = dependencies.get_seq_mapping(db, [item.id for item in associated])
    return [{**item.to_dict(), "seq_num": seq_map.get(item.id)} for item in associated]


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
        raise dependencies.HTTPException(status_code=404, detail="未找到对应的题目")

    image_paths_to_check = list(db_question.image_paths)
    try:
        from sqlalchemy import func

        affected_paper_ids = [
            paper_id
            for (paper_id,) in db.query(dependencies.PaperQuestion.paper_id)
            .filter(dependencies.PaperQuestion.question_id == question_id)
            .distinct()
            .all()
        ]
        if affected_paper_ids:
            remaining_scores = dict(
                db.query(
                    dependencies.PaperQuestion.paper_id,
                    func.coalesce(func.sum(dependencies.PaperQuestion.score), 0),
                )
                .filter(
                    dependencies.PaperQuestion.paper_id.in_(affected_paper_ids),
                    dependencies.PaperQuestion.question_id != question_id,
                )
                .group_by(dependencies.PaperQuestion.paper_id)
                .all()
            )
            for paper in db.query(dependencies.Paper).filter(
                dependencies.Paper.id.in_(affected_paper_ids)
            ):
                paper.total_score = int(remaining_scores.get(paper.id, 0))
        db.delete(db_question)
        db.commit()
    except Exception as e:
        db.rollback()
        raise dependencies.HTTPException(status_code=400, detail=f"删除题目失败: {str(e)}")

    # The database delete is complete.  Image cleanup is intentionally
    # best-effort so a locked/missing file cannot make the client believe the
    # question still exists and submit a duplicate delete.
    try:
        dependencies.delete_unreferenced_question_assets(db, image_paths_to_check)
    except Exception as cleanup_exc:
        print(
            "[Storage Cleanup] Post-commit delete cleanup failed "
            f"(type={type(cleanup_exc).__name__}); it will be retried by "
            "the startup orphan cleanup."
        )

    # Auto export database to files for Git synchronization and AI referencing (Async Background Task)
    dependencies.schedule_database_export(background_tasks, operation="delete_question")

    return {"status": "success", "message": "题目删除成功"}
