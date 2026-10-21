"""Classification service; all application dependencies are explicit."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from mathbank.application_state import RuntimeState


@dataclass(frozen=True)
class ClassificationServiceDependencies:
    JSONResponse: Any
    annotate_ai_knowledge_points: Any
    apply_model_thinking_policy: Any
    build_classification_system_prompt: Any
    copy: Any
    detect_structured_question_form: Any
    get_active_version_code: Any
    get_current_curriculum: Any
    json: Any
    load_ai_knowledge_catalog: Any
    normalize_ai_question_form: Any
    normalize_import_classifications: Any
    os: Any
    post_chat_completion: Any
    resolve_text_provider: Any
    state: RuntimeState


def ai_classify(content: str=Form(...), answer_markdown: str=Form(''), review_markdown: str=Form(''), db: Session=Depends(get_db), expected_version_code: Optional[str]=Form(None), *, dependencies: ClassificationServiceDependencies):
    classify_model = dependencies.os.getenv('PREFER_CLASSIFY_MODEL') or dependencies.os.getenv('DEEPSEEK_CLASSIFY_MODEL') or dependencies.os.getenv('PREFER_PARSE_MODEL') or 'deepseek-flash'
    provider = dependencies.resolve_text_provider(classify_model)
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.credential_label
    if not api_key:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'未配置对应的 API Key ({provider_name})，无法自动智能分类！请在工作台右上角设置面板进行配置。'}, status_code=400)
    try:
        version_code = dependencies.get_active_version_code()
        if isinstance(expected_version_code, str) and expected_version_code != version_code:
            return dependencies.JSONResponse(content={'status': 'error', 'message': '当前教材版本已变化，请刷新后重新分类。'}, status_code=409)
        curriculum = dependencies.copy.deepcopy(dependencies.get_current_curriculum())
        knowledge_catalog = dependencies.load_ai_knowledge_catalog(db)
        system_instructions = dependencies.build_classification_system_prompt(curriculum, knowledge_catalog)
        question_input = {'content': content, 'answer_markdown': answer_markdown if isinstance(answer_markdown, str) else '', 'review_markdown': review_markdown if isinstance(review_markdown, str) else ''}
        data = {'model': model_name, 'messages': [{'role': 'system', 'content': system_instructions}, {'role': 'user', 'content': dependencies.json.dumps(question_input, ensure_ascii=False)}], 'response_format': {'type': 'json_object'}, 'temperature': 0.2, 'max_tokens': 4096}
        data = dependencies.apply_model_thinking_policy(data, provider=provider, task='classify')
        response = dependencies.post_chat_completion(provider, data, timeout=30, provider_name=provider_name)
        res_json = response.json()
        ai_message = res_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if ai_message.startswith('```'):
            lines = ai_message.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines[-1].strip() == '```':
                lines = lines[:-1]
            ai_message = '\n'.join(lines).strip()
        result = dependencies.json.loads(ai_message)
        dependencies.annotate_ai_knowledge_points(question_input, knowledge_catalog, raw=result.get('knowledge_points', []))
        placement = {'category_compulsory': result.get('compulsory', ''), 'category_chapter': result.get('chapter', ''), 'category_knowledge': result.get('knowledge', '')}
        dependencies.normalize_import_classifications([placement], curriculum)
        compulsory = placement['category_compulsory']
        chapter = placement['category_chapter']
        knowledge = placement['category_knowledge']
        structured_question_form = dependencies.detect_structured_question_form(content)
        model_question_form = dependencies.normalize_ai_question_form(result.get('question_form'))
        # Physics experiment worksheets often contain fill-in blanks; these do
        # not turn an entire experiment into a standalone fill-in question.
        if structured_question_form == 'fill_in_blank' and model_question_form == 'experiment':
            structured_question_form = None
        question_form = structured_question_form or model_question_form
        question_form_source = 'structure' if structured_question_form else 'ai'
        if dependencies.get_active_version_code() != version_code:
            return dependencies.JSONResponse(content={'status': 'error', 'message': '分类期间教材版本已变化，请保留当前编辑并重新分类。'}, status_code=409)
        curr = curriculum
        if compulsory in curr and chapter in curr[compulsory] and isinstance(knowledge, str) and (not knowledge or knowledge in curr[compulsory][chapter]):
            return {'status': 'success', 'compulsory': compulsory, 'chapter': chapter, 'knowledge': knowledge, 'question_form': question_form, 'question_form_source': question_form_source, 'knowledge_points': question_input['knowledge_points'], 'knowledge_point_warnings': question_input['knowledge_point_warnings'], 'version_code': version_code, **({'classification_review': placement['classification_review']} if 'classification_review' in placement else {})}
        else:
            raise ValueError('AI 返回的学段、章节或小节不在当前教材大纲中，请保留原分类并人工核对。')
    except Exception as e:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'AI 智能分类失败: {str(e)}'}, status_code=500)
