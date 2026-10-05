"""Classification service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Form


@dataclass(frozen=True)
class ClassificationServiceDependencies:
    state: RuntimeState
    JSONResponse: Any
    apply_model_thinking_policy: Any
    build_classification_system_prompt: Any
    detect_structured_question_form: Any
    get_current_curriculum: Callable
    json: Any
    normalize_ai_question_form: Any
    os: Any
    post_chat_completion: Any
    resolve_text_provider: Any


def ai_classify(content: str=Form(...), *, dependencies: ClassificationServiceDependencies):
    classify_model = (
        dependencies.os.getenv("PREFER_CLASSIFY_MODEL")
        or dependencies.os.getenv("DEEPSEEK_CLASSIFY_MODEL")
        or dependencies.os.getenv("PREFER_PARSE_MODEL")
        or "deepseek-flash"
    )

    provider = dependencies.resolve_text_provider(classify_model)
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.credential_label

    if not api_key:
        return dependencies.JSONResponse(
            content={
                "status": "error",
                "message": f"未配置对应的 API Key ({provider_name})，无法自动智能分类！请在工作台右上角设置面板进行配置。"
            },
            status_code=400
        )

    try:
        system_instructions = dependencies.build_classification_system_prompt(dependencies.get_current_curriculum())
        data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": f"题目内容:\n{content}"}
            ],
            "response_format": {
                "type": "json_object"
            },
            "temperature": 0.2,
            "max_tokens": 512
        }

        data = dependencies.apply_model_thinking_policy(
            data,
            provider=provider,
            task="classify",
        )

        response = dependencies.post_chat_completion(
            provider,
            data,
            timeout=30,
            provider_name=provider_name,
        )

        res_json = response.json()
        ai_message = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # Strip potential markdown formatting if returned
        if ai_message.startswith("```"):
            lines = ai_message.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            ai_message = "\n".join(lines).strip()

        result = dependencies.json.loads(ai_message)
        compulsory = result.get("compulsory", "")
        chapter = result.get("chapter", "")
        structured_question_form = dependencies.detect_structured_question_form(content)
        question_form = structured_question_form or dependencies.normalize_ai_question_form(
            result.get("question_form")
        )
        question_form_source = "structure" if structured_question_form else "ai"

        # Verification: make sure returned values exist in get_current_curriculum()
        curr = dependencies.get_current_curriculum()
        if compulsory in curr and chapter in curr[compulsory]:
            return {
                "status": "success",
                "compulsory": compulsory,
                "chapter": chapter,
                "question_form": question_form,
                "question_form_source": question_form_source,
            }
        else:
            # Fallback dynamically to the first available category book/chapter
            first_comp = list(curr.keys())[0] if curr else "必修一"
            first_chap = list(curr[first_comp].keys())[0] if curr and first_comp in curr and curr[first_comp] else "1. 集合与常用逻辑用语"
            return {
                "status": "success",
                "compulsory": first_comp,
                "chapter": first_chap,
                "question_form": question_form,
                "question_form_source": question_form_source,
                "is_fallback": True,
                "raw_recommendation": f"{compulsory} -> {chapter}"
            }

    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"AI 智能分类失败: {str(e)}"},
            status_code=500
        )
