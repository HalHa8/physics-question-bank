"""Question queries; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from typing import Optional
from fastapi import Depends
from sqlalchemy.orm import Session
from mathbank.database import Question, get_db
from mathbank.question_duplicates import QuestionDuplicateInput


@dataclass(frozen=True)
class QuestionQueriesDependencies:
    state: RuntimeState
    HTTPException: Any
    JSONResponse: Any
    Question: Any
    QuestionDuplicateInput: Any
    _duplicate_input_from_payload: Callable
    _duplicate_payload_list: Callable
    _prompt_visible_image_paths: Callable
    batch_local_matches: Any
    build_question_fingerprint: Any
    build_tikz_signatures: Any
    build_visible_image_signatures: Any
    datetime: Any
    duplicate_index_status: Any
    find_indexed_candidates: Any
    get_current_curriculum: Callable
    get_seq_mapping: Callable
    json: Any
    normalize_fillin_macro: Any
    select_answer_images: Any
    select_visible_question_images: Any


def get_seq_mapping(db: Session, question_ids=None, *, dependencies: QuestionQueriesDependencies):
    """Map physical ID order to the user-facing contiguous sequence number."""

    if question_ids is None:
        all_q = db.query(dependencies.Question.id).order_by(dependencies.Question.id.asc()).all()
        return {q_id: idx + 1 for idx, (q_id,) in enumerate(all_q)}

    normalized_ids = {int(question_id) for question_id in question_ids}
    if not normalized_ids:
        return {}
    from sqlalchemy import func

    ranked = db.query(
        dependencies.Question.id.label("question_id"),
        func.row_number().over(order_by=dependencies.Question.id.asc()).label("seq_num"),
    ).subquery()
    rows = db.query(ranked.c.question_id, ranked.c.seq_num).filter(
        ranked.c.question_id.in_(normalized_ids)
    ).all()
    return {question_id: int(seq_num) for question_id, seq_num in rows}


def list_questions(q: str=None, search: str=None, compulsory: str=None, category_compulsory: str=None, chapter: str=None, category_chapter: str=None, knowledge: str=None, category_knowledge: str=None, qtype: str=None, question_type: str=None, difficulty: str=None, source: str=None, page: Optional[int]=None, page_size: int=20, sort: str='desc', db: Session=Depends(get_db), *, dependencies: QuestionQueriesDependencies):
    search_q = q or search
    comp_val = compulsory or category_compulsory
    chap_val = chapter or category_chapter
    know_val = knowledge or category_knowledge
    type_val = qtype or question_type

    query = db.query(dependencies.Question)

    # Check if searching for a specific display sequence number
    target_id_by_seq = None
    if search_q:
        clean_q = search_q.strip()
        if clean_q.startswith("#"):
            clean_q = clean_q[1:]
        if clean_q.isdigit():
            seq_val = int(clean_q)
            if seq_val >= 1:
                row = (
                    db.query(dependencies.Question.id)
                    .order_by(dependencies.Question.id.asc())
                    .offset(seq_val - 1)
                    .limit(1)
                    .first()
                )
                if row:
                    target_id_by_seq = row[0]

    if search_q:
        if target_id_by_seq is not None:
            query = query.filter(
                (dependencies.Question.id == target_id_by_seq) |
                (dependencies.Question.content.like(f"%{search_q}%")) |
                (dependencies.Question.source.like(f"%{search_q}%")) |
                (dependencies.Question.answer_markdown.like(f"%{search_q}%")) |
                (dependencies.Question.review.like(f"%{search_q}%")) |
                (dependencies.Question.tags.like(f"%{search_q}%"))
            )
        else:
            query = query.filter(
                (dependencies.Question.content.like(f"%{search_q}%")) |
                (dependencies.Question.source.like(f"%{search_q}%")) |
                (dependencies.Question.answer_markdown.like(f"%{search_q}%")) |
                (dependencies.Question.review.like(f"%{search_q}%")) |
                (dependencies.Question.tags.like(f"%{search_q}%"))
            )
    if comp_val:
        query = query.filter(dependencies.Question.category_compulsory == comp_val)
    if chap_val:
        query = query.filter(dependencies.Question.category_chapter == chap_val)
    if know_val:
        query = query.filter(dependencies.Question.category_knowledge == know_val)
    if type_val:
        query = query.filter(dependencies.Question.question_type == type_val)
    if difficulty:
        query = query.filter(dependencies.Question.difficulty == difficulty)
    if source:
        query = query.filter(dependencies.Question.source.like(f"%{source}%"))

    order_columns = (
        (dependencies.Question.created_at.asc(), dependencies.Question.id.asc())
        if str(sort).lower() == "asc"
        else (dependencies.Question.created_at.desc(), dependencies.Question.id.desc())
    )
    if page is not None:
        safe_page_size = max(1, min(int(page_size), 100))
        total = query.count()
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        safe_page = max(1, min(int(page), total_pages))
        questions = (
            query.order_by(*order_columns)
            .offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        seq_map = dependencies.get_seq_mapping(db, [item.id for item in questions])
        return {
            "items": [
                {**item.to_summary_dict(), "seq_num": seq_map.get(item.id)}
                for item in questions
            ],
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
        }

    questions = query.order_by(*order_columns).all()
    seq_map = dependencies.get_seq_mapping(db, [item.id for item in questions])
    return [{**item.to_summary_dict(), "seq_num": seq_map.get(item.id)} for item in questions]


def _duplicate_payload_list(value, *, field_name: str, max_items: int=50, dependencies: QuestionQueriesDependencies):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = dependencies.json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 格式无效") from exc
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须是数组")
    if len(value) > max_items:
        raise ValueError(f"{field_name} 数量超过 {max_items} 项")
    return value


def _duplicate_input_from_payload(item: dict, *, dependencies: QuestionQueriesDependencies) -> QuestionDuplicateInput:
    content = dependencies.normalize_fillin_macro(str(item.get("content") or ""))
    if not content.strip():
        raise ValueError("题干内容不能为空")
    if len(content) > 200_000:
        raise ValueError("单题题干过长")
    answer_markdown = str(item.get("answer_markdown") or "")
    if len(answer_markdown) > 500_000:
        raise ValueError("单题解析过长")
    image_paths = [
        str(path or "").strip()
        for path in dependencies._duplicate_payload_list(
            item.get("image_paths"), field_name="image_paths"
        )
        if str(path or "").strip()
    ]
    content_assets = dependencies._duplicate_payload_list(
        item.get("content_tikz_assets"),
        field_name="content_tikz_assets",
    )
    answer_assets = dependencies._duplicate_payload_list(
        item.get("answer_tikz_assets"),
        field_name="answer_tikz_assets",
    )
    legacy_reference = str(item.get("tikz_reference_image_path") or "").strip()
    hidden_references = {legacy_reference}
    for asset in [*content_assets, *answer_assets]:
        if isinstance(asset, dict):
            hidden_references.add(str(asset.get("reference_image_path") or "").strip())
    hidden_references.discard("")
    evidence_image_paths = [
        path for path in image_paths if path not in hidden_references
    ]
    visible_paths = dependencies.select_visible_question_images(
        content,
        answer_markdown,
        evidence_image_paths,
        content_assets,
    )
    return dependencies.QuestionDuplicateInput(
        content=content,
        answer_markdown=answer_markdown,
        question_type=str(item.get("question_type") or ""),
        visible_image_signatures=dependencies.build_visible_image_signatures(
            visible_paths,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
        ),
        tikz_signatures=dependencies.build_tikz_signatures(
            content_assets,
            str(item.get("tikz_code") or ""),
        ),
        answer_asset_signatures=(
            dependencies.build_visible_image_signatures(
                dependencies.select_answer_images(
                    answer_markdown,
                    evidence_image_paths,
                    answer_assets,
                ),
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            )
            + dependencies.build_tikz_signatures(answer_assets)
        ),
    )


def _prompt_visible_image_paths(question: Question, *, dependencies: QuestionQueriesDependencies) -> list[str]:
    return dependencies.select_visible_question_images(
        question.content or "",
        question.answer_markdown or "",
        question.display_image_paths,
        question.content_tikz_assets,
    )


def check_question_duplicates(payload: dict, db: Session=Depends(get_db), *, dependencies: QuestionQueriesDependencies):
    """Check only when a teacher initiates a save/import; never during parsing."""

    if not isinstance(payload, dict):
        raise dependencies.HTTPException(status_code=400, detail="查重请求格式无效")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise dependencies.HTTPException(status_code=400, detail="items 必须是非空题目数组")
    if len(items) > 500:
        raise dependencies.HTTPException(status_code=400, detail="单次最多查重 500 道题")
    max_candidates = max(1, min(int(payload.get("max_candidates") or 5), 10))

    try:
        prepared = []
        total_content_size = 0
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                raise ValueError(f"第 {index + 1} 道题格式无效")
            duplicate_input = dependencies._duplicate_input_from_payload(raw_item)
            total_content_size += len(duplicate_input.content) + len(
                duplicate_input.answer_markdown
            )
            if total_content_size > 5_000_000:
                raise ValueError("本次查重内容总量过大")
            exclude_id = raw_item.get("exclude_id")
            if exclude_id not in (None, ""):
                exclude_id = int(exclude_id)
                if exclude_id <= 0:
                    raise ValueError("exclude_id 必须是正整数")
            else:
                exclude_id = None
            client_key = str(raw_item.get("client_key") or index)
            if len(client_key) > 128:
                raise ValueError("client_key 过长")
            prepared.append(
                {
                    "client_key": client_key,
                    "exclude_id": exclude_id,
                    "input": duplicate_input,
                    "fingerprint": dependencies.build_question_fingerprint(duplicate_input),
                }
            )
    except (TypeError, ValueError) as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        fingerprints = [item["fingerprint"] for item in prepared]
        batch_matches, batch_diagnostics = dependencies.batch_local_matches(fingerprints)
        candidate_cache = {}
        raw_results = []
        all_candidate_ids = set()
        truncated_recall_band_count = 0
        for index, item in enumerate(prepared):
            recall_diagnostics = {}
            candidates = dependencies.find_indexed_candidates(
                db,
                item["fingerprint"],
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
                exclude_id=item["exclude_id"],
                limit=max_candidates,
                fingerprint_cache=candidate_cache,
                diagnostics=recall_diagnostics,
            )
            truncated_recall_band_count += int(
                recall_diagnostics.get("truncated_band_count") or 0
            )
            all_candidate_ids.update(candidate.question.id for candidate in candidates)
            raw_results.append((index, item, candidates))
        seq_map = dependencies.get_seq_mapping(db, all_candidate_ids)
        rank = {"exact": 3, "probable": 2, "possible_variant": 1, "none": 0}
        response_items = []
        for index, item, candidates in raw_results:
            candidate_payloads = []
            levels = []
            needs_visual_review = False
            for candidate in candidates:
                comparison = candidate.comparison.to_dict()
                levels.append(comparison["level"])
                needs_visual_review = (
                    needs_visual_review or comparison["needs_visual_review"]
                )
                question = candidate.question
                content_preview = str(question.content or "")[:500]
                candidate_images = dependencies._prompt_visible_image_paths(question)
                candidate_payloads.append(
                    {
                        "id": question.id,
                        "seq_num": seq_map.get(question.id),
                        "content": content_preview,
                        "content_truncated": len(str(question.content or "")) > 500,
                        "source": question.source or "",
                        "question_type": question.question_type or "",
                        "has_answer": bool((question.answer_markdown or "").strip()),
                        "image_paths": candidate_images[:4],
                        "image_count": len(candidate_images),
                        "snapshot_hash": candidate.fingerprint.content_revision_hash,
                        **comparison,
                    }
                )
            local_payloads = []
            for local_match in batch_matches.get(index, []):
                other_index = int(local_match["other_index"])
                local_payload = {
                    **local_match,
                    "other_client_key": prepared[other_index]["client_key"],
                }
                local_payloads.append(local_payload)
                levels.append(str(local_match["level"]))
                needs_visual_review = (
                    needs_visual_review
                    or bool(local_match.get("needs_visual_review"))
                )
            level = max(levels, key=lambda value: rank.get(value, 0)) if levels else "none"
            response_items.append(
                {
                    "client_key": item["client_key"],
                    "snapshot_hash": item["fingerprint"].content_revision_hash,
                    "level": level,
                    "candidates": candidate_payloads,
                    "batch_matches": local_payloads,
                    "needs_visual_review": needs_visual_review,
                }
            )
        status = dependencies.duplicate_index_status(db)
        if truncated_recall_band_count:
            status = {
                **status,
                "ready": False,
                "warning": (
                    "近似候选分桶过宽，已为保持速度停止扩展；"
                    "本次结果可能不完整。"
                ),
            }
        if not batch_diagnostics.get("index_complete", True):
            status = {
                **status,
                "ready": False,
                "warning": "批内近似候选过多，结果可能不完整",
            }
        return {
            "status": "success",
            "index": status,
            "batch_diagnostics": batch_diagnostics,
            "items": response_items,
        }
    except Exception as exc:
        db.rollback()
        print(
            "[Duplicate Check] Failed "
            f"(type={type(exc).__name__}); saving remains available."
        )
        raise dependencies.HTTPException(status_code=503, detail="查重暂不可用，可选择继续保存") from exc


def get_question(question_id: int, db: Session=Depends(get_db), *, dependencies: QuestionQueriesDependencies):
    q = db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
    if not q:
        raise dependencies.HTTPException(status_code=404, detail="未找到对应的题目")
    seq_map = dependencies.get_seq_mapping(db, [q.id])
    q_dict = q.to_dict()
    q_dict["seq_num"] = seq_map.get(q.id)
    return q_dict


def get_db_stats(db: Session=Depends(get_db), *, dependencies: QuestionQueriesDependencies):
    try:
        total = db.query(dependencies.Question).count()
        normal = db.query(dependencies.Question).filter(dependencies.Question.difficulty == "normal").count()
        easy_error = db.query(dependencies.Question).filter(dependencies.Question.difficulty == "easy_error").count()
        challenge = db.query(dependencies.Question).filter(dependencies.Question.difficulty == "challenge").count()
        qiangji = db.query(dependencies.Question).filter(dependencies.Question.difficulty == "qiangji").count()

        # Cascaded Stage & Chapter Counts
        rows = db.query(
            dependencies.Question.category_compulsory,
            dependencies.Question.category_chapter
        ).all()

        comp_chap_stats = {}
        for comp, chap in rows:
            comp_val = comp or "未分类"
            chap_val = chap or "未分章节"
            if comp_val not in comp_chap_stats:
                comp_chap_stats[comp_val] = {}
            if chap_val not in comp_chap_stats[comp_val]:
                comp_chap_stats[comp_val][chap_val] = 0
            comp_chap_stats[comp_val][chap_val] += 1

        def compulsory_sort_key(comp_name: str):
            if not comp_name or comp_name == "未分类":
                return (99, 99, comp_name or "")
            num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6}
            is_comp = 0 if ("必修" in comp_name and "选" not in comp_name) else 1
            num = 99
            for k, v in num_map.items():
                if k in comp_name:
                    num = min(num, v)
            return (is_comp, num, comp_name)

        sorted_comp_chap_stats = {
            k: comp_chap_stats[k]
            for k in sorted(comp_chap_stats.keys(), key=compulsory_sort_key)
        }

        # Daily additions in local time (UTC+8)
        date_rows = db.query(dependencies.Question.created_at).all()
        daily_adds = {}
        for (created_at,) in date_rows:
            if created_at:
                # Convert UTC to UTC+8 local time
                local_time = created_at + dependencies.datetime.timedelta(hours=8)
                date_str = local_time.strftime("%Y-%m-%d")
                daily_adds[date_str] = daily_adds.get(date_str, 0) + 1

        return {
            "status": "success",
            "total_count": total,
            "normal_count": normal,
            "easy_error_count": easy_error,
            "challenge_count": challenge,
            "qiangji_count": qiangji,
            "compulsory_chapter_counts": sorted_comp_chap_stats,
            "daily_adds": daily_adds
        }
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"获取统计数据失败: {str(e)}"},
            status_code=500
        )


def list_categories(db: Session=Depends(get_db), *, dependencies: QuestionQueriesDependencies):
    # Initialize with predefined curriculum
    hierarchy = {}
    for comp, chapters in dependencies.get_current_curriculum().items():
        hierarchy[comp] = {}
        for chap, sections in chapters.items():
            hierarchy[comp][chap] = list(sections)

    # Also fetch any custom entries from DB
    results = db.query(
        dependencies.Question.category_compulsory,
        dependencies.Question.category_chapter,
        dependencies.Question.category_knowledge
    ).distinct().all()

    for comp, chap, know in results:
        if not comp:
            continue
        if comp not in hierarchy:
            hierarchy[comp] = {}
        if not chap:
            continue
        if chap not in hierarchy[comp]:
            hierarchy[comp][chap] = []
        if know and know not in hierarchy[comp][chap]:
            hierarchy[comp][chap].append(know)

    return hierarchy


def get_sources(db: Session=Depends(get_db), *, dependencies: QuestionQueriesDependencies):
    results = db.query(dependencies.Question.source).distinct().all()
    sources = []
    for r in results:
        val = r[0]
        if val and val.strip():
            sources.append(val.strip())

    # Sort alphabetically (case-insensitive)
    sources.sort(key=str.lower)
    return sources
