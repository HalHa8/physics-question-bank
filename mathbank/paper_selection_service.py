"""Paper selection service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Depends
from sqlalchemy.orm import Session
from mathbank.database import get_db


@dataclass(frozen=True)
class PaperSelectionServiceDependencies:
    state: RuntimeState
    JSONResponse: Any
    Question: Any
    apply_model_thinking_policy: Any
    build_paper_selection_prompts: Any
    get_seq_mapping: Callable
    json: Any
    os: Any
    post_chat_completion: Any
    re: Any
    resolve_text_provider: Any


def ai_select_paper(payload: dict, db: Session=Depends(get_db), *, dependencies: PaperSelectionServiceDependencies):
    """AI 智能选题：结合用户指定的 PREFER_SOLVE_MODEL 大模型与 math-teaching 教研引擎组卷"""
    try:
        prompt = payload.get("prompt", "").strip()
        question_type = payload.get("question_type", "")
        difficulty = payload.get("difficulty", "")
        compulsory = payload.get("compulsory", "")
        chapter = payload.get("chapter", "")
        knowledge = payload.get("knowledge", "")
        limit = max(1, min(int(payload.get("limit", 5)), 20))

        # 0. 自然语言意图智能分析 (NL Intent Parser)
        extracted_topics = []
        is_review_intent = False
        if prompt:
            is_review_intent = any(k in prompt for k in ['做过', '考过', '已抽过', '已用过', '复习', '旧题', '重做', '错题', '以往', '历史'])
            num_match = dependencies.re.search(r'([一二三四五六七八九十1-9]+)\s*道', prompt)
            cn_to_num = {'一':1, '两':2, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10}
            if num_match:
                val = num_match.group(1)
                limit = cn_to_num.get(val, int(val) if val.isdigit() else limit)

            if not question_type:
                if '填空' in prompt: question_type = 'fill_in_blank'
                elif '单选' in prompt: question_type = 'single_choice'
                elif '多选' in prompt: question_type = 'multi_choice'
                elif '实验' in prompt: question_type = 'experiment'
                elif '简答' in prompt: question_type = 'short_answer'
                elif '计算' in prompt or '解答' in prompt: question_type = 'detailed_answer'

            known_topics = [
                '运动学', '匀变速直线运动', '牛顿运动定律', '曲线运动', '圆周运动',
                '万有引力', '机械能', '动量', '振动', '波', '光学', '静电场', '电路',
                '磁场', '电磁感应', '交变电流', '热学', '原子物理', '实验',
            ]
            extracted_topics = [t for t in known_topics if t in prompt]

        # 1. 结构化过滤基础题目池
        query = db.query(dependencies.Question)
        if question_type:
            query = query.filter(dependencies.Question.question_type == question_type)
        if difficulty:
            query = query.filter(dependencies.Question.difficulty == difficulty)
        if compulsory:
            query = query.filter(dependencies.Question.category_compulsory == compulsory)
        if chapter:
            query = query.filter(dependencies.Question.category_chapter == chapter)
        if knowledge:
            query = query.filter(dependencies.Question.category_knowledge == knowledge)

        if is_review_intent:
            # 复习/旧题模式：优先提取已使用频次高的题目
            review_query = query.filter(dependencies.Question.usage_count > 0).order_by(dependencies.Question.usage_count.desc(), dependencies.Question.id.desc())
            candidates = review_query.limit(35).all()
            if not candidates:
                candidates = query.order_by(dependencies.Question.id.desc()).limit(35).all()
        else:
            # 默认鲜活模式：优先提取从未被使用过的冷门题目
            candidates = query.order_by(dependencies.Question.usage_count.asc(), dependencies.Question.id.desc()).limit(35).all()
            if not candidates:
                candidates = db.query(dependencies.Question).order_by(dependencies.Question.usage_count.asc(), dependencies.Question.id.desc()).limit(35).all()

        # 2. 解题、拆卷、分类和组卷共用同一供应商解析规则。
        # 不会因为某家 Key 缺失而静默改用另一家。
        target_model = (
            dependencies.os.getenv("PREFER_SOLVE_MODEL")
            or dependencies.os.getenv("PREFER_PARSE_MODEL")
            or "deepseek-flash"
        )
        provider = dependencies.resolve_text_provider(target_model)
        api_key = provider.api_key
        api_base = provider.api_base
        model_name = provider.model_name
        provider_name = provider.provider_label

        api_error_detail = None
        if prompt and candidates:
            if not api_key or not api_base:
                api_error_detail = (
                    f"指定的 AI 解题模型 ({target_model}) 未配置有效的 "
                    f"API Key 或 Base URL（{provider.credential_label}）。"
                )
            else:
                candidate_items = []
                for q in candidates:
                    clean_stem = dependencies.re.sub(r'[\r\n]+', ' ', q.content[:80])
                    candidate_items.append({
                        "id": q.id,
                        "question_type": q.question_type,
                        "difficulty": q.difficulty,
                        "usage_count": q.usage_count or 0,
                        "knowledge": q.category_knowledge or q.category_chapter or "通用知识点",
                        "tags": q.tags or "",
                        "stem_excerpt": clean_stem
                    })

                system_prompt, user_content = dependencies.build_paper_selection_prompts(
                    teacher_prompt=prompt,
                    limit=limit,
                    candidates=candidate_items,
                    is_review_intent=is_review_intent,
                )

                try:
                    payload_data = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content}
                        ],
                        "temperature": 0.3
                    }
                    payload_data = dependencies.apply_model_thinking_policy(
                        payload_data,
                        provider=provider,
                        task="paper_selection",
                    )
                    response = dependencies.post_chat_completion(
                        provider,
                        payload_data,
                        timeout=20,
                        provider_name=provider_name,
                    )
                    res_json = response.json()
                    raw_content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if raw_content.startswith("```"):
                        raw_content = dependencies.re.sub(r"^```(?:json)?\s*", "", raw_content)
                        raw_content = dependencies.re.sub(r"\s*```$", "", raw_content)

                    parsed = dependencies.json.loads(raw_content)
                    raw_selected_ids = parsed.get("selected_ids", [])
                    ai_analysis = parsed.get("ai_analysis", "")

                    if raw_selected_ids and isinstance(raw_selected_ids, list):
                        # The model may only rank the candidate IDs that were
                        # actually supplied after local filters.  This prevents
                        # prompt output from bypassing chapter/type constraints
                        # or selecting arbitrary records from the database.
                        allowed_ids = {question.id for question in candidates}
                        selected_ids = []
                        seen_ids = set()
                        for raw_id in raw_selected_ids:
                            try:
                                selected_id = int(raw_id)
                            except (TypeError, ValueError):
                                continue
                            if (
                                selected_id in allowed_ids
                                and selected_id not in seen_ids
                            ):
                                selected_ids.append(selected_id)
                                seen_ids.add(selected_id)
                            if len(selected_ids) >= limit:
                                break
                        db_selected = db.query(dependencies.Question).filter(dependencies.Question.id.in_(selected_ids)).all()
                        id_map = {q.id: q for q in db_selected}
                        seq_map = dependencies.get_seq_mapping(db, selected_ids)
                        final_questions = [{**id_map[qid].to_dict(), "seq_num": seq_map.get(qid)} for qid in selected_ids if qid in id_map]

                        if final_questions:
                            return {
                                "status": "success",
                                "data": final_questions,
                                "count": len(final_questions),
                                "ai_analysis": ai_analysis,
                                "model_used": f"{provider_name} ({model_name})",
                                "fallback": False
                            }
                except Exception as llm_err:
                    api_error_detail = f"{provider_name} API 请求失败: {str(llm_err)}"

        # 3. 降级本地算法（带明确错误反馈）
        fallback_questions = []
        if extracted_topics:
            for topic in extracted_topics:
                sub_query = db.query(dependencies.Question)
                if question_type:
                    sub_query = sub_query.filter(dependencies.Question.question_type == question_type)
                sub_query = sub_query.filter(
                    (dependencies.Question.content.like(f"%{topic}%")) |
                    (dependencies.Question.category_chapter.like(f"%{topic}%")) |
                    (dependencies.Question.category_knowledge.like(f"%{topic}%")) |
                    (dependencies.Question.tags.like(f"%{topic}%"))
                )
                order_clause = dependencies.Question.usage_count.desc() if is_review_intent else dependencies.Question.usage_count.asc()
                for q in sub_query.order_by(order_clause, dependencies.Question.id.desc()).all():
                    if q not in fallback_questions:
                        fallback_questions.append(q)

        # 补足数量
        if len(fallback_questions) < limit:
            for q in candidates:
                if q not in fallback_questions:
                    fallback_questions.append(q)
                if len(fallback_questions) >= limit:
                    break

        selected_fallback = fallback_questions[:limit]
        seq_map = dependencies.get_seq_mapping(db, [q.id for q in selected_fallback])
        result = [{**q.to_dict(), "seq_num": seq_map.get(q.id)} for q in selected_fallback]

        topic_str = "、".join(extracted_topics) if extracted_topics else "通用知识点"
        err_banner = f"⚠️ 【AI 解题模型调用未成功】: {api_error_detail}\n系统已为您自动启动本地教研算法，根据意图（{topic_str}）在本地题库中筛选并组合了 {len(result)} 道精选题目。" if api_error_detail else f"【本地智能筛选分析】已为您自动识别意图（{topic_str}），从题库中精准挑选并组合了鲜活试题。"

        return {
            "status": "success",
            "data": result,
            "count": len(result),
            "ai_analysis": err_banner,
            "model_used": f"⚠️ 模型调用失败 ({target_model}) ➔ 退回本地算法" if api_error_detail else "本地算法",
            "fallback": True
        }
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": f"AI 智能选题失败: {str(e)}"}, status_code=500)
