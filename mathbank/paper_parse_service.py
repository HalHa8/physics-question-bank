"""Paper parse service; all application dependencies are explicit."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from mathbank.application_state import RuntimeState


@dataclass(frozen=True)
class PaperParseServiceDependencies:
    JSONResponse: Any
    PAPER_SPLIT_TIMEOUT_SECONDS: Any
    ParseConfigurationError: Any
    annotate_ai_knowledge_points: Any
    apply_model_thinking_policy: Any
    build_import_parse_system_prompt: Any
    build_pdf_parse_system_prompt: Any
    copy: Any
    finalize_source_answers: Any
    get_current_curriculum: Any
    json: Any
    load_ai_knowledge_catalog: Any
    lock_visible_math: Any
    make_source_review_advisory: Any
    map_markdown_question_images: Any
    markdown_image_references: Any
    markdown_literal_ranges: Any
    normalize_import_classifications: Any
    normalize_question_math_markdown: Any
    os: Any
    parse_paper_completion: Any
    post_chat_completion: Any
    prepare_markdown_question_for_storage: Any
    prepare_markdown_source: Any
    prepare_tex_source: Any
    re: Any
    reconcile_visible_math: Any
    request_pdf_paper_completion: Any
    resolve_text_provider: Any
    separate_formula_notices: Any
    state: RuntimeState
    tex_asset_references_match: Any
    uuid: Any
    validate_import_knowledge: Any


def parse_paper_text_internal(latex_content: str, generate_answers_bool: bool, *, diagnostics: dict | None=None, preserve_source_answers: bool=False, pdf_retry: bool=False, check_cancelled=lambda : None, report_attempt=lambda _event: None, connection_retry: bool=False, dependencies: PaperParseServiceDependencies) -> list:
    """内部通用函数：调用选定的 LLM 接口，将 LaTeX 试卷内容解析拆分为结构化 JSON 卡片"""
    check_cancelled()
    parse_model = dependencies.os.getenv('PREFER_PARSE_MODEL') or dependencies.os.getenv('DEEPSEEK_PARSE_MODEL', 'deepseek-flash')
    provider = dependencies.resolve_text_provider(parse_model)
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.provider_label
    if not api_key:
        raise dependencies.ParseConfigurationError(f'未配置对应的 API Key ({provider.credential_label})，无法智能拆解试卷！请在工作台右上角设置面板进行配置。')
    curriculum = dependencies.copy.deepcopy(dependencies.get_current_curriculum())
    system_instructions = dependencies.build_pdf_parse_system_prompt(curriculum, generate_answers_bool, dependencies.load_ai_knowledge_catalog())
    max_output_tokens = 65536
    data = {'model': model_name, 'messages': [{'role': 'system', 'content': system_instructions}, {'role': 'user', 'content': latex_content}], 'response_format': {'type': 'json_object'}, 'temperature': 0.2, 'max_tokens': max_output_tokens}
    data = dependencies.apply_model_thinking_policy(data, provider=provider, task='parse')
    if pdf_retry:
        parsed_questions = dependencies.request_pdf_paper_completion(provider, data, post=dependencies.post_chat_completion, raw_markdown='' if preserve_source_answers else latex_content, diagnostics=diagnostics, check_cancelled=check_cancelled, report_attempt=report_attempt)
    else:
        check_cancelled()
        transport_kwargs = {'retry_connection': False, 'allow_redirects': False} if not connection_retry else {}
        response = dependencies.post_chat_completion(provider, data, timeout=dependencies.PAPER_SPLIT_TIMEOUT_SECONDS, provider_name=provider_name, **transport_kwargs)
        check_cancelled()
        parsed_questions = dependencies.parse_paper_completion(response.json(), raw_markdown='' if preserve_source_answers else latex_content, diagnostics=diagnostics)
    if preserve_source_answers:
        dependencies.validate_import_knowledge(parsed_questions, curriculum, diagnostics=diagnostics)
        return parsed_questions
    dependencies.validate_import_knowledge(parsed_questions, curriculum, diagnostics=diagnostics)
    for q in parsed_questions:
        ans = q.get('answer_markdown', '')
        if not ans:
            q['answer_markdown'] = ''
        elif not generate_answers_bool:
            if '[EXTRACTED_ORIGINAL]' in ans:
                q['answer_markdown'] = ans.replace('[EXTRACTED_ORIGINAL]', '').strip()
            else:
                q['answer_markdown'] = ''
        else:
            q['answer_markdown'] = ans.replace('[EXTRACTED_ORIGINAL]', '').strip()
        for field in ('content', 'answer_markdown'):
            value = q.get(field, '')
            if isinstance(value, str) and value:
                q[field] = dependencies.normalize_question_math_markdown(value)
    return parsed_questions


def ai_parse_paper(latex_content: str=Form(...), paper_title: str=Form(''), image_mapping_json: str=Form('{}'), generate_answers: str=Form('false'), source_format: str=Form('tex'), *, dependencies: PaperParseServiceDependencies):
    if source_format not in ('tex', 'markdown'):
        return dependencies.JSONResponse(content={'status': 'error', 'message': '源码格式仅支持 tex 或 markdown。'}, status_code=400)
    generate_answers_bool = generate_answers.lower() in ('true', '1', 'yes')
    parse_model = dependencies.os.getenv('PREFER_PARSE_MODEL') or dependencies.os.getenv('DEEPSEEK_PARSE_MODEL', 'deepseek-flash')
    provider = dependencies.resolve_text_provider(parse_model)
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.provider_label
    if not api_key:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'未配置对应的 API Key ({provider.credential_label})，无法智能拆解试卷！请在工作台右上角设置面板进行配置。'}, status_code=400)
    try:
        image_mapping = dependencies.json.loads(image_mapping_json)
        if not isinstance(image_mapping, dict):
            image_mapping = {}
    except Exception:
        image_mapping = {}
    try:
        tex_result = dependencies.prepare_markdown_source(latex_content) if source_format == 'markdown' else dependencies.prepare_tex_source(latex_content)
        tex_diagnostics = tex_result['diagnostics']
        (model_source, math_locks) = dependencies.lock_visible_math(tex_result['model_source'], ('MD_' if source_format == 'markdown' else 'TEX_') + dependencies.uuid.uuid4().hex[:16], literal_ranges=dependencies.markdown_literal_ranges(tex_result['model_source']) if source_format == 'markdown' else ())
        tex_diagnostics['math_locks_created'] = len(math_locks)
        if not paper_title.strip() and tex_result['title']:
            paper_title = tex_result['title']
        curriculum = dependencies.copy.deepcopy(dependencies.get_current_curriculum())
        knowledge_catalog = dependencies.load_ai_knowledge_catalog()
        system_instructions = dependencies.build_import_parse_system_prompt(curriculum, source_format, knowledge_catalog)
        max_output_tokens = 65536
        data = {'model': model_name, 'messages': [{'role': 'system', 'content': system_instructions}, {'role': 'user', 'content': model_source}], 'response_format': {'type': 'json_object'}, 'temperature': 0.2, 'max_tokens': max_output_tokens}
        data = dependencies.apply_model_thinking_policy(data, provider=provider, task='parse')
        response = dependencies.post_chat_completion(provider, data, timeout=dependencies.PAPER_SPLIT_TIMEOUT_SECONDS, provider_name=provider_name)
        parsed_questions = dependencies.parse_paper_completion(response.json(), diagnostics=tex_diagnostics)
        dependencies.validate_import_knowledge(parsed_questions, curriculum, diagnostics=tex_diagnostics)
        lock_report = dependencies.reconcile_visible_math(parsed_questions, math_locks, tex_result['model_source'], tex_comments=source_format != 'markdown')
        previous_warnings = list(tex_diagnostics.get('warnings', []))
        tex_diagnostics.update(lock_report)
        tex_diagnostics['warnings'] = previous_warnings + lock_report.get('warnings', [])
        dependencies.finalize_source_answers(parsed_questions, tex_result['model_source'])
        tex_diagnostics['source_review_count'] = sum((bool(q.get('source_review', {}).get('required')) for q in parsed_questions))
        tex_diagnostics['question_count_actual'] = len(parsed_questions)
        estimated_count = tex_diagnostics.get('question_count_estimate', 0)
        if estimated_count and estimated_count != len(parsed_questions):
            tex_diagnostics.setdefault('warnings', []).append(f'源码约识别到 {estimated_count} 道题，但模型返回 {len(parsed_questions)} 道，请重点核对是否漏题或误拆。')
        for graphic_ref in tex_diagnostics.get('referenced_graphics', []):
            graphic_ref = str(graphic_ref)
            candidates = []
            for question in parsed_questions:
                content_graphics = dependencies.markdown_image_references(question.get('content', '') + '\n' + question.get('answer_markdown', '')) if source_format == 'markdown' else dependencies.re.findall('\\\\includegraphics(?:\\s*\\[[^\\]]*\\])?\\s*\\{([^}]+)\\}', question.get('content', ''))
                question_refs = content_graphics + [str(value) for value in question.get('referenced_images', [])]
                if any((dependencies.tex_asset_references_match(graphic_ref, value) for value in question_refs)):
                    candidates.append(question)
            if len(candidates) == 1 and (not any((dependencies.tex_asset_references_match(graphic_ref, existing) for existing in candidates[0]['referenced_images']))):
                candidates[0]['referenced_images'].append(graphic_ref)
            elif not candidates:
                tex_diagnostics.setdefault('unassigned_source_images', []).append(graphic_ref)
        for q in parsed_questions:
            extracted_source = q.get('source')
            content_str = q.get('content', '')
            prefix_match = dependencies.re.match('^(\\s*(?:\\d+[\\.、\\s]*)?)([\\(（])([^\\(（\\)）\\s]{4,})([\\)）])', content_str)
            if prefix_match:
                if not extracted_source:
                    extracted_source = prefix_match.group(3).strip()
                to_remove = prefix_match.group(1) + prefix_match.group(2) + prefix_match.group(3) + prefix_match.group(4)
                content_str = content_str.replace(to_remove, '', 1).strip()
                content_str = dependencies.re.sub('^[\\s、\\.．]+', '', content_str)
                q['content'] = content_str
            q['source'] = (extracted_source or paper_title).strip()
            for field in ['content', 'answer_markdown']:
                if field in q and isinstance(q[field], str):
                    text = q[field]
                    if source_format == 'tex':
                        text = dependencies.re.sub('\\\\n(?![a-zA-Z])', '\n', text)
                    q[field] = text
            if source_format == 'markdown':
                dependencies.map_markdown_question_images(q, image_mapping, tex_diagnostics)
                dependencies.prepare_markdown_question_for_storage(q, tex_diagnostics)
                continue
            mapped_images = []
            ref_imgs = q.get('referenced_images', [])
            for ref_name in ref_imgs:
                ref_name = str(ref_name)
                found_path = None
                for (orig_name, serv_path) in image_mapping.items():
                    if dependencies.tex_asset_references_match(ref_name, orig_name):
                        found_path = serv_path
                        break
                if found_path:
                    if found_path not in mapped_images:
                        mapped_images.append(found_path)
                    include_pattern = dependencies.re.compile('\\\\includegraphics(?:\\s*\\[[^\\]]*\\])?\\s*\\{\\s*([^}]+?)\\s*\\}')
                    q['content'] = include_pattern.sub(lambda match: f'![插图]({found_path})' if dependencies.tex_asset_references_match(ref_name, match.group(1)) else match.group(0), q['content'])
                else:
                    tex_diagnostics.setdefault('unmapped_images', []).append(str(ref_name))
            q['image_paths'] = mapped_images
            for img_path in mapped_images:
                if img_path not in q['content']:
                    q['content'] += f'\n\n![插图]({img_path})\n\n'
        unmapped_images = sorted(set(tex_diagnostics.get('unmapped_images', [])))
        unassigned_images = sorted(set(tex_diagnostics.get('unassigned_source_images', [])))
        tex_diagnostics['unmapped_images'] = unmapped_images
        tex_diagnostics['unassigned_source_images'] = unassigned_images
        if unmapped_images:
            tex_diagnostics.setdefault('warnings', []).append(f"以下 {('Markdown' if source_format == 'markdown' else 'TeX')} 配图未找到同名上传文件：" + '、'.join(unmapped_images[:8]))
        if unassigned_images:
            tex_diagnostics.setdefault('warnings', []).append('以下配图未能确定所属题目：' + '、'.join(unassigned_images[:8]))
        for question in parsed_questions:
            dependencies.annotate_ai_knowledge_points(question, knowledge_catalog)
        dependencies.separate_formula_notices(parsed_questions, preserve_missing=True)
        dependencies.make_source_review_advisory(parsed_questions, tex_diagnostics)
        return {'status': 'success', 'questions': parsed_questions, 'tex_diagnostics': tex_diagnostics, 'source_format': source_format}
    except Exception as e:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'试卷解析失败: {str(e)}', 'tex_diagnostics': locals().get('tex_diagnostics', {})}, status_code=500)


def validate_import_knowledge(questions: list[dict], curriculum: dict, *, diagnostics=None, dependencies: PaperParseServiceDependencies) -> None:
    """Preserve imported source bodies while flagging uncertain placement."""
    dependencies.normalize_import_classifications(questions, curriculum, diagnostics)
