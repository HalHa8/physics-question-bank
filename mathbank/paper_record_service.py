"""Paper record service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Depends, BackgroundTasks
from sqlalchemy.orm import Session
from mathbank.database import get_db


@dataclass(frozen=True)
class PaperRecordServiceDependencies:
    state: RuntimeState
    JSONResponse: Any
    Paper: Any
    PaperQuestion: Any
    Question: Any
    get_seq_mapping: Callable
    json: Any
    normalize_section_order: Any
    schedule_database_export: Callable


def get_paper_questions(ids: str='', db: Session=Depends(get_db), *, dependencies: PaperRecordServiceDependencies):
    """获取指定 ID 列表的完整题目数据（组卷试题篮批量拉取）"""
    if not ids:
        return {"status": "success", "data": []}
    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
        if not id_list:
            return {"status": "success", "data": []}
        questions = db.query(dependencies.Question).filter(dependencies.Question.id.in_(id_list)).all()
        q_map = {q.id: q.to_dict() for q in questions}
        seq_map = dependencies.get_seq_mapping(db, id_list)
        result = [
            {**q_map[qid], "seq_num": seq_map.get(qid)}
            for qid in id_list
            if qid in q_map
        ]
        return {"status": "success", "data": result}
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


def save_paper(payload: dict, background_tasks: BackgroundTasks, db: Session=Depends(get_db), *, dependencies: PaperRecordServiceDependencies):
    """保存排版好的试卷，自增被选中题目的 usage_count"""
    try:
        if not isinstance(payload, dict):
            raise ValueError("试卷数据格式不正确。")
        title = str(payload.get("title", "未命名试卷")).strip()
        subtitle = str(payload.get("subtitle", "")).strip()
        paper_type = payload.get("paper_type", "exam")
        questions_payload = payload.get("questions", [])

        if not title or len(title) > 200 or len(subtitle) > 200:
            raise ValueError("试卷标题不能为空，且标题与副标题均不能超过 200 字。")
        if paper_type not in {"exam", "quiz", "exam_19"}:
            raise ValueError("不支持的试卷模板。")
        if not isinstance(questions_payload, list) or not questions_payload:
            raise ValueError("试卷中至少需要包含一道题目。")
        if len(questions_payload) > 200:
            raise ValueError("单份试卷不能超过 200 道题。")

        normalized_items = []
        seen_question_ids = set()
        for item in questions_payload:
            if not isinstance(item, dict):
                raise ValueError("试卷题目数据格式不正确。")
            question_id = int(item.get("id"))
            score = int(item.get("score", 5))
            if question_id <= 0 or score < 0 or score > 100:
                raise ValueError("题目 ID 或分值不在有效范围内。")
            if question_id in seen_question_ids:
                raise ValueError("同一道题不能在一份试卷中重复出现。")
            seen_question_ids.add(question_id)
            normalized_items.append((question_id, score))

        questions = db.query(dependencies.Question).filter(
            dependencies.Question.id.in_(seen_question_ids)
        ).all()
        question_map = {question.id: question for question in questions}
        missing_ids = sorted(seen_question_ids - set(question_map))
        if missing_ids:
            raise ValueError("试卷中包含已删除或不存在的题目。")

        total_score = sum(score for _question_id, score in normalized_items)

        meta = payload.get("metadata", {})
        if not isinstance(meta, dict):
            meta = {}
        meta["show_secret"] = payload.get("show_secret", True)
        meta["show_notice"] = payload.get("show_notice", True)
        meta["section_order"] = dependencies.normalize_section_order(payload.get("section_order", meta.get("section_order")))

        paper = dependencies.Paper(
            title=title,
            subtitle=subtitle,
            paper_type=paper_type,
            total_score=total_score,
            metadata_json=dependencies.json.dumps(meta)
        )
        db.add(paper)
        db.flush()

        for idx, (qid, score) in enumerate(normalized_items):
            pq = dependencies.PaperQuestion(
                paper_id=paper.id,
                question_id=qid,
                order_index=idx + 1,
                score=score
            )
            db.add(pq)
            question = question_map[qid]
            question.usage_count = (question.usage_count or 0) + 1

        db.commit()
        dependencies.schedule_database_export(background_tasks, operation="save_paper")
        return {"status": "success", "message": "试卷保存成功！", "paper_id": paper.id}
    except (TypeError, ValueError) as e:
        db.rollback()
        return dependencies.JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=400
        )
    except Exception as e:
        db.rollback()
        return dependencies.JSONResponse(content={"status": "error", "message": f"保存试卷失败: {str(e)}"}, status_code=500)


def list_papers(db: Session=Depends(get_db), *, dependencies: PaperRecordServiceDependencies):
    """获取所有历史试卷列表"""
    try:
        from sqlalchemy import func

        rows = (
            db.query(dependencies.Paper, func.count(dependencies.PaperQuestion.id))
            .outerjoin(dependencies.PaperQuestion, dependencies.PaperQuestion.paper_id == dependencies.Paper.id)
            .group_by(dependencies.Paper.id)
            .order_by(dependencies.Paper.created_at.desc())
            .all()
        )
        result = []
        for p, q_count in rows:
            d = p.to_dict()
            d["question_count"] = int(q_count)
            result.append(d)
        return {"status": "success", "data": result}
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


def get_paper_detail(paper_id: int, db: Session=Depends(get_db), *, dependencies: PaperRecordServiceDependencies):
    """获取单张试卷的详细信息及关联题目列表（用于一键载入）"""
    try:
        paper = db.query(dependencies.Paper).filter(dependencies.Paper.id == paper_id).first()
        if not paper:
            return dependencies.JSONResponse(content={"status": "error", "message": "试卷不存在"}, status_code=404)

        rows = (
            db.query(dependencies.PaperQuestion, dependencies.Question)
            .join(dependencies.Question, dependencies.Question.id == dependencies.PaperQuestion.question_id)
            .filter(dependencies.PaperQuestion.paper_id == paper_id)
            .order_by(dependencies.PaperQuestion.order_index.asc())
            .all()
        )

        questions_list = [
            {
                "id": question.id,
                "score": paper_question.score,
                "question": question.to_dict(),
            }
            for paper_question, question in rows
        ]

        result = paper.to_dict()
        result["questions"] = questions_list
        return {"status": "success", "data": result}
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


def delete_paper(paper_id: int, background_tasks: BackgroundTasks, db: Session=Depends(get_db), *, dependencies: PaperRecordServiceDependencies):
    """删除指定的历史试卷，并同步扣减关联题目的 usage_count"""
    try:
        paper = db.query(dependencies.Paper).filter(dependencies.Paper.id == paper_id).first()
        if not paper:
            return dependencies.JSONResponse(content={"status": "error", "message": "试卷不存在"}, status_code=404)

        pqs = db.query(dependencies.PaperQuestion).filter(dependencies.PaperQuestion.paper_id == paper_id).all()
        reference_counts = {}
        for paper_question in pqs:
            reference_counts[paper_question.question_id] = (
                reference_counts.get(paper_question.question_id, 0) + 1
            )
        questions = db.query(dependencies.Question).filter(
            dependencies.Question.id.in_(reference_counts)
        ).all()
        for question in questions:
            if question.usage_count:
                question.usage_count = max(
                    0,
                    question.usage_count - reference_counts.get(question.id, 0),
                )

        db.query(dependencies.PaperQuestion).filter(dependencies.PaperQuestion.paper_id == paper_id).delete()
        db.delete(paper)
        db.commit()
        dependencies.schedule_database_export(background_tasks, operation="delete_paper")
        return {"status": "success", "message": "试卷记录已成功删除"}
    except Exception as e:
        db.rollback()
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
