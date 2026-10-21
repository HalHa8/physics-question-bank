"""Document task service; all application dependencies are explicit."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from mathbank.application_state import RuntimeState
from mathbank.document_import_context import DocumentImportDependencies


@dataclass(frozen=True)
class DocumentTaskServiceDependencies:
    DocumentImportDependencies: Any
    DocumentProjectError: Any
    HTTPException: Any
    Image: Any
    JSONResponse: Any
    MAX_PDF_BYTES: Any
    PDF_STRATEGIES: Any
    Path: Any
    Response: Any
    TaskQueueFull: Any
    UploadTooLargeError: Any
    _delete_task_temp_assets: Any
    _dispatch_document_project: Any
    _document_curriculum_sha256: Any
    _document_project_service: Any
    _document_request_id: Any
    _document_status: Any
    _manual_crop_pdf_impl: Any
    _queue_document_upload: Any
    _read_document_source: Any
    _register_document_input: Any
    build_document_import_dependencies: Any
    copy: Any
    docx_import_service: Any
    extract_docx_markdown: Any
    find_source_page_by_overlap: Any
    get_current_curriculum: Any
    hashlib: Any
    inspect_and_extract_pdf: Any
    json: Any
    normalize_fillin_macro: Any
    ocr_pdf_page_image: Any
    parse_paper_text_internal: Any
    pdf_import_service: Any
    post_process_pdf_parsed_questions: Any
    post_process_questions: Any
    re: Any
    read_stream_limited: Any
    reconcile_visible_math: Any
    resolve_upload_asset: Any
    run_docx_parsing_task: Any
    run_pdf_parsing_task: Any
    state: RuntimeState
    uuid: Any
    DOCUMENT_AI_TIMEOUT_SECONDS: Any
    PAPER_SPLIT_CACHE_MAX_CHARACTERS: Any
    PAPER_SPLIT_TIMEOUT_SECONDS: Any
    SourceMetadataPermanentHTTPError: Any
    TaskCancelled: Any
    UPLOAD_DIR: Any
    apply_pdf_layout_reviews: Any
    collected_usage: Any
    enrich_pdf_with_figures: Any
    extract_title_from_latex: Any
    finalize_source_answers: Any
    finalize_word_extraction_reviews: Any
    inspect_pdf_page: Any
    isolate_shared_pdf_figures: Any
    iter_completed_futures: Any
    lock_visible_math: Any
    make_source_review_advisory: Any
    merge_pdf_page_texts: Any
    os: Any
    parse_page_range: Any
    post_chat_completion: Any
    prepare_word_extraction_reviews: Any
    prepare_word_source_metadata: Any
    process_ocr_illustrations: Any
    refresh_pdf_review_items: Any
    request_word_source_metadata: Any
    resolve_text_provider: Any
    separate_formula_notices: Any
    source_metadata_diagnostics: Any
    summarize_import_classifications: Any
    threading: Any


def build_document_import_dependencies(*, dependencies: DocumentTaskServiceDependencies) -> DocumentImportDependencies:
    return dependencies.DocumentImportDependencies(
        tasks=dependencies.state.DOCUMENT_TASKS,
        ocr_semaphore=dependencies.state.PDF_OCR_SEMAPHORE,
        tmp_upload_dir=dependencies.state.TMP_UPLOAD_DIR,
        upload_dir_rel=dependencies.state.UPLOAD_DIR_REL,
        max_pdf_pages=dependencies.state.MAX_PDF_TASK_PAGES,
        inspect_pdf=dependencies.inspect_and_extract_pdf,
        ocr_page=dependencies.ocr_pdf_page_image,
        parse_text=dependencies.parse_paper_text_internal,
        postprocess=dependencies.post_process_pdf_parsed_questions,
        delete_temp_assets=dependencies._delete_task_temp_assets,
        extract_docx=dependencies.extract_docx_markdown,
        reconcile_math=dependencies.reconcile_visible_math,
        state=dependencies.state,
        DOCUMENT_AI_TIMEOUT_SECONDS=dependencies.DOCUMENT_AI_TIMEOUT_SECONDS,
        PAPER_SPLIT_CACHE_MAX_CHARACTERS=dependencies.PAPER_SPLIT_CACHE_MAX_CHARACTERS,
        PAPER_SPLIT_TIMEOUT_SECONDS=dependencies.PAPER_SPLIT_TIMEOUT_SECONDS,
        PDF_STRATEGIES=dependencies.PDF_STRATEGIES,
        Path=dependencies.Path,
        SourceMetadataPermanentHTTPError=dependencies.SourceMetadataPermanentHTTPError,
        TaskCancelled=dependencies.TaskCancelled,
        UPLOAD_DIR=dependencies.UPLOAD_DIR,
        apply_pdf_layout_reviews=dependencies.apply_pdf_layout_reviews,
        collected_usage=dependencies.collected_usage,
        copy=dependencies.copy,
        enrich_pdf_with_figures=dependencies.enrich_pdf_with_figures,
        extract_title_from_latex=dependencies.extract_title_from_latex,
        finalize_source_answers=dependencies.finalize_source_answers,
        finalize_word_extraction_reviews=dependencies.finalize_word_extraction_reviews,
        get_current_curriculum=dependencies.get_current_curriculum,
        hashlib=dependencies.hashlib,
        inspect_pdf_page=dependencies.inspect_pdf_page,
        isolate_shared_pdf_figures=dependencies.isolate_shared_pdf_figures,
        iter_completed_futures=dependencies.iter_completed_futures,
        json=dependencies.json,
        lock_visible_math=dependencies.lock_visible_math,
        make_source_review_advisory=dependencies.make_source_review_advisory,
        merge_pdf_page_texts=dependencies.merge_pdf_page_texts,
        normalize_fillin_macro=dependencies.normalize_fillin_macro,
        os=dependencies.os,
        parse_page_range=dependencies.parse_page_range,
        post_chat_completion=dependencies.post_chat_completion,
        prepare_word_extraction_reviews=dependencies.prepare_word_extraction_reviews,
        prepare_word_source_metadata=dependencies.prepare_word_source_metadata,
        process_ocr_illustrations=dependencies.process_ocr_illustrations,
        re=dependencies.re,
        refresh_pdf_review_items=dependencies.refresh_pdf_review_items,
        request_word_source_metadata=dependencies.request_word_source_metadata,
        resolve_text_provider=dependencies.resolve_text_provider,
        resolve_upload_asset=dependencies.resolve_upload_asset,
        separate_formula_notices=dependencies.separate_formula_notices,
        source_metadata_diagnostics=dependencies.source_metadata_diagnostics,
        summarize_import_classifications=dependencies.summarize_import_classifications,
        threading=dependencies.threading,
    )


def manual_crop_pdf(payload: dict, *, dependencies: DocumentTaskServiceDependencies):
    """用户在前端手动拖拽框选后，后端根据坐标裁剪 PDF 页面的特定区域"""
    """Crop locally, including retained projects whose runtime task expired."""
    project_id = payload.get('project_id') if isinstance(payload, dict) else None
    if project_id:
        try:
            if not dependencies.state.DOCUMENT_PROJECTS:
                raise dependencies.DocumentProjectError('本地工程未启用。')
            with dependencies.state.DOCUMENT_PROJECTS.operation(project_id):
                dependencies.state.DOCUMENT_PROJECTS.touch(project_id)
                return dependencies._manual_crop_pdf_impl(payload, project_id)
        except dependencies.DocumentProjectError as exc:
            return dependencies.JSONResponse({'status': 'error', 'message': str(exc)}, status_code=409)
    return dependencies._manual_crop_pdf_impl(payload)


def post_process_pdf_parsed_questions(parsed_questions: list, paper_title: str, task_id: str=None, ocr_results: list=None, *, source_body_preserved: bool=False, preserved_indices=None, dependencies: DocumentTaskServiceDependencies) -> list:
    """Compatibility entry point; the result processor owns the implementation."""
    return dependencies.post_process_questions(
        parsed_questions, paper_title, task_id, ocr_results,
        tmp_upload_dir=dependencies.state.TMP_UPLOAD_DIR, upload_dir_rel=dependencies.state.UPLOAD_DIR_REL,
        normalize_fillin=dependencies.normalize_fillin_macro,
        source_body_preserved=source_body_preserved, preserved_indices=preserved_indices,
        find_source_page=dependencies.find_source_page_by_overlap,
    )


def run_pdf_parsing_task(task_id: str, file_bytes: bytes, filename: str, generate_answers: bool=False, page_range: str=None, pdf_strategy: str='native_preferred', pdf_verify_suspicions: bool=False, *, dependencies: DocumentTaskServiceDependencies):

    """Keep the historical callable while delegating to the import service."""
    return dependencies.pdf_import_service.run_pdf_parsing_task(
        task_id, file_bytes, filename, generate_answers, page_range,
        pdf_strategy, pdf_verify_suspicions,
        dependencies=dependencies.build_document_import_dependencies(),
    )


def upload_pdf_task(file: UploadFile=File(...), generate_answers: str=Form('false'), page_range: Optional[str]=Form(None), pdf_strategy: str=Form('native_preferred'), pdf_verify_suspicions: bool=Form(False), client_request_id: str=Form(''), paper_title: str=Form(''), *, dependencies: DocumentTaskServiceDependencies):
    try:
        client_request_id = dependencies._document_request_id(client_request_id)
        if pdf_strategy not in dependencies.PDF_STRATEGIES:
            return dependencies.JSONResponse(content={'status': 'error', 'message': '不支持的 PDF 解析策略。'}, status_code=400)
        generate_answers_bool = generate_answers.lower() in ('true', '1', 'yes')
        filename = file.filename or ''
        if not filename.lower().endswith('.pdf'):
            return dependencies.JSONResponse(content={'status': 'error', 'message': '上传文件格式不正确，必须为 .pdf 格式！'}, status_code=400)
        try:
            content = dependencies.read_stream_limited(file.file, dependencies.MAX_PDF_BYTES)
        except dependencies.UploadTooLargeError:
            return dependencies.JSONResponse(content={'status': 'error', 'message': 'PDF 文件过大，请上传 30MB 以内的试卷文件！'}, status_code=413)
        if not content.lstrip().startswith(b'%PDF-'):
            return dependencies.JSONResponse(content={'status': 'error', 'message': '文件内容不是有效的 PDF 文档！'}, status_code=400)
        options = dict(generate_answers=generate_answers_bool, page_range=page_range, pdf_strategy=pdf_strategy, pdf_verify_suspicions=bool(pdf_verify_suspicions) if pdf_strategy == 'layout_aware' else False, paper_title=paper_title.strip())
        return dependencies._queue_document_upload(content, filename, 'pdf', client_request_id, options, dependencies.run_pdf_parsing_task, (generate_answers_bool, page_range, pdf_strategy, options['pdf_verify_suspicions']))
    except dependencies.HTTPException:
        raise
    except Exception as e:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'创建 PDF 解析任务失败: {str(e)}'}, status_code=500)


def run_docx_parsing_task(task_id: str, file_bytes: bytes, filename: str, generate_answers: bool=False, docx_verify_suspicions: bool=False, *, resume_state=None, dependencies: DocumentTaskServiceDependencies):

    """Keep the historical callable while delegating to the import service."""
    return dependencies.docx_import_service.run_docx_parsing_task(
        task_id, file_bytes, filename, generate_answers, docx_verify_suspicions,
        resume_state=resume_state, dependencies=dependencies.build_document_import_dependencies(),
    )


def upload_docx_task(file: UploadFile=File(...), generate_answers: str=Form('false'), docx_verify_suspicions: str=Form('false'), client_request_id: str=Form(''), paper_title: str=Form(''), *, dependencies: DocumentTaskServiceDependencies):
    try:
        client_request_id = dependencies._document_request_id(client_request_id)
        generate_answers_bool = generate_answers.lower() in ('true', '1', 'yes')
        filename = file.filename or ''
        if not filename.lower().endswith('.docx'):
            return dependencies.JSONResponse(content={'status': 'error', 'message': '上传文件格式不正确，必须为 .docx 格式！'}, status_code=400)
        try:
            content = dependencies.read_stream_limited(file.file, dependencies.MAX_PDF_BYTES)
        except dependencies.UploadTooLargeError:
            return dependencies.JSONResponse(content={'status': 'error', 'message': 'Word 文件过大，请上传 30MB 以内的试卷文件！'}, status_code=413)
        if len(content) < 4 or content[:4] != b'PK\x03\x04':
            return dependencies.JSONResponse(content={'status': 'error', 'message': '文件内容不是有效的 Word DOCX 压缩包！'}, status_code=400)
        options = dict(generate_answers=generate_answers_bool, docx_verify_suspicions=docx_verify_suspicions.lower() in ('true', '1', 'yes'), paper_title=paper_title.strip())
        return dependencies._queue_document_upload(content, filename, 'docx', client_request_id, options, dependencies.run_docx_parsing_task, (generate_answers_bool, options['docx_verify_suspicions']))
    except dependencies.HTTPException:
        raise
    except Exception as e:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'创建 Word 解析任务失败: {str(e)}'}, status_code=500)


def get_pdf_task_status(task_id: str, *, dependencies: DocumentTaskServiceDependencies):
    task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
    if not task:
        return dependencies.JSONResponse(content={'status': 'error', 'message': '未找到对应的任务 ID！'}, status_code=404)
    return dependencies._document_status(task_id, task)


def cancel_pdf_task(task_id: str, *, dependencies: DocumentTaskServiceDependencies):
    current = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
    if current is None:
        return dependencies.JSONResponse(
            content={"status": "error", "message": "未找到对应的任务 ID！"},
            status_code=404
        )

    current_status = current.get("status")
    if current_status in {"completed", "error"}:
        # Never delete assets belonging to a task that already produced a
        # result.  The previous behavior reported success and could remove
        # completed PDF crop files after a late ESC/click.
        return dependencies.JSONResponse(
            content={
                "status": "error",
                "message": "任务已结束，无法再中止。",
                "task_status": current_status,
            },
            status_code=409,
        )
    if current_status == "cancelled":
        return {
            "status": "success",
            "message": "任务已中止。",
            "task_status": "cancelled",
        }

    task = dependencies.state.DOCUMENT_TASKS.cancel(task_id)
    if task is None:  # Defensive race guard; records are not normally removed here.
        return dependencies.JSONResponse(
            content={"status": "error", "message": "未找到对应的任务 ID！"},
            status_code=404,
        )
    if task.get("status") != "cancelled":
        # The worker may have completed between the snapshot above and the
        # atomic cancel call.  Never delete assets from that completed result.
        return dependencies.JSONResponse(
            content={
                "status": "error",
                "message": "任务已结束，无法再中止。",
                "task_status": task.get("status"),
            },
            status_code=409,
        )
    removed = dependencies._delete_task_temp_assets(list(task.get("temp_assets", [])))
    return {
        "status": "success",
        "message": f"任务已成功中止，已清理 {removed} 个临时资产",
        "task_status": "cancelled",
    }


def clear_temp_crops(payload: dict, *, dependencies: DocumentTaskServiceDependencies):
    """物理删除传递来的未入库临时裁剪图片路径"""
    try:
        paths = payload.get("paths", [])
        if not isinstance(paths, list):
            raise ValueError("paths 必须是数组。")
        removed_count = dependencies._delete_task_temp_assets(paths)
        return {"status": "success", "message": f"成功物理清除 {removed_count} 张废弃插图图片。"}
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"清理临时插图出错: {str(e)}"},
            status_code=500
        )


def _document_request_id(value, *, dependencies: DocumentTaskServiceDependencies):
    value = str(value or '').strip()
    if value and (not dependencies.re.fullmatch('[A-Za-z0-9_-]{8,100}', value)):
        raise dependencies.HTTPException(status_code=400, detail='文档请求标识格式无效。')
    return value


def _document_curriculum_sha256(*, dependencies: DocumentTaskServiceDependencies):
    return dependencies.hashlib.sha256(dependencies.json.dumps(dependencies.get_current_curriculum(), ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _register_document_input(task_id, content, document_type, filename, *, dependencies: DocumentTaskServiceDependencies, **options):
    persistent = dependencies.state.DOCUMENT_TASK_STORE is not None and (not (dependencies.state.PDF_CLOUD_ONLY and document_type == 'pdf'))
    source = dependencies.state.DOCUMENT_TASK_STORE.source(task_id, content) if persistent else {'sha256': dependencies.hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
    if not persistent:
        dependencies.state.DOCUMENT_TASK_INPUTS[task_id] = content
    return {**source, 'document_type': document_type, 'filename': filename, 'options': options, 'curriculum_sha256': dependencies._document_curriculum_sha256()}


def _document_status(task_id, task, *, dependencies: DocumentTaskServiceDependencies):
    result = {key: value for (key, value) in task.items() if key not in {'pdf_resume_state', 'docx_resume_state', 'document_input', 'retained_at'}}
    result['task_id'] = task_id
    project_id = task.get('project_id')
    if project_id and dependencies.state.DOCUMENT_PROJECTS and (not dependencies.state.PDF_CLOUD_ONLY):
        try:
            metadata = dependencies.state.DOCUMENT_PROJECTS.get(project_id)
            result.update(project_id=project_id, project_revision=metadata['revision'], expires_at=metadata['expires_at'], retention_days=7)
            revision_receipt = dependencies._document_project_service().validated_initial_revision_receipt(project_id)
            if revision_receipt is not None:
                result['project_revision_receipt'] = revision_receipt
            if result.get('data'):
                result['data'] = dependencies._document_project_service().question_ids(project_id, result['data'])
        except dependencies.DocumentProjectError:
            result['project_warning'] = '本地工程暂不可用，已有任务结果仍保留。'
    source_matches = (task.get('diagnostics') or {}).get('source_matches', [])
    occurrences = {}
    for (index, question) in enumerate(result.get('data') or []):
        scopes = sorted(((str(row.get('field', '')), row['source_start'], row['source_end']) for row in source_matches if row.get('question_index') == index and type(row.get('source_start')) is int and (type(row.get('source_end')) is int)))
        identity = dependencies.json.dumps(scopes or [question.get('content', ''), question.get('answer_markdown', '')], ensure_ascii=False)
        digest = dependencies.hashlib.sha256(identity.encode()).hexdigest()
        occurrence = occurrences.get(digest, 0)
        occurrences[digest] = occurrence + 1
        question['import_item_id'] = question.get('project_card_id') or f'{task_id}:{digest}:{occurrence}'
    result['source_available'] = bool(task.get('document_input')) and (dependencies.state.DOCUMENT_TASK_STORE.has_source(task_id) if dependencies.state.DOCUMENT_TASK_STORE and (not (dependencies.state.PDF_CLOUD_ONLY and task.get('document_type') == 'pdf')) else task_id in dependencies.state.DOCUMENT_TASK_INPUTS)
    result['can_resume'] = task.get('status') in {'error', 'interrupted'} and result['source_available'] and (not (dependencies.state.PDF_CLOUD_ONLY and task.get('document_type') == 'pdf'))
    if result['can_resume']:
        result['recovery_message'] = '已保留文档及成功阶段，可继续处理；不会重新识别已完成页面。'
    return result


def _manual_crop_pdf_impl(payload, project_id=None, *, dependencies: DocumentTaskServiceDependencies):
    try:
        import math
        if not isinstance(payload, dict):
            raise ValueError('裁剪参数格式不正确。')
        try:
            task_id = str(dependencies.uuid.UUID(str(payload.get('task_id', ''))))
        except (ValueError, AttributeError) as exc:
            raise ValueError('任务 ID 格式不正确。') from exc
        task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
        if project_id:
            metadata = dependencies.state.DOCUMENT_PROJECTS.get(project_id)
            task = dependencies.state.DOCUMENT_PROJECTS.load_task(project_id)
            task_id = metadata.get('task_id') or project_id
            task = {**task, 'document_type': 'pdf'}
        if not task or task.get('document_type') != 'pdf':
            return dependencies.JSONResponse(content={'status': 'error', 'message': '未找到对应的 PDF 任务！'}, status_code=404)
        if not project_id and task.get('status') in {'cancelled', 'error'}:
            raise ValueError('已取消或失败的 PDF 任务不能再裁剪。')
        page_index = int(payload.get('page_index', 0))
        selected_numbers = task.get('page_numbers')
        if page_index < 0 or (isinstance(selected_numbers, list) and page_index + 1 not in selected_numbers) or (selected_numbers is None and page_index >= dependencies.state.MAX_PDF_TASK_PAGES):
            raise ValueError('页码越界。')
        ymin = float(payload.get('ymin', 0))
        xmin = float(payload.get('xmin', 0))
        ymax = float(payload.get('ymax', 0))
        xmax = float(payload.get('xmax', 0))
        coordinates = (ymin, xmin, ymax, xmax)
        if not all((math.isfinite(value) for value in coordinates)):
            raise ValueError('裁剪坐标必须是有限数值。')
        if not (0 <= ymin < ymax <= 100 and 0 <= xmin < xmax <= 100):
            raise ValueError('裁剪坐标必须位于 0–100，且框选区域不能为空。')
        img_filename = f'pdf_page_{task_id}_{page_index}.png'
        img_filepath = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR) / img_filename
        if project_id and isinstance(selected_numbers, list) and (page_index + 1 in selected_numbers):
            page_images = task.get('page_images') or []
            local_index = selected_numbers.index(page_index + 1)
            if local_index < len(page_images):
                img_filepath = dependencies.resolve_upload_asset(page_images[local_index], uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
        if project_id and (not img_filepath.is_file()):
            import pymupdf as fitz
            with fitz.open(stream=dependencies.state.DOCUMENT_PROJECTS.load_source(project_id), filetype='pdf') as document:
                if page_index >= len(document):
                    raise ValueError('页码越界。')
                pixmap = document[page_index].get_pixmap(matrix=fitz.Matrix(2, 2))
                img_filepath = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR) / img_filename
                pixmap.save(str(img_filepath))
                dependencies.state.DOCUMENT_PROJECTS.register_assets(project_id, [f'/{dependencies.state.UPLOAD_DIR_REL}/tmp/{img_filename}'])
        if not img_filepath.is_file() or img_filepath.is_symlink():
            return dependencies.JSONResponse(content={'status': 'error', 'message': '未找到对应的 PDF 页面图片！'}, status_code=404)
        with dependencies.Image.open(img_filepath) as img:
            img.load()
            (w, h) = img.size
            left = max(0, min(xmin / 100.0 * w, w - 1))
            top = max(0, min(ymin / 100.0 * h, h - 1))
            right = max(left + 1, min(xmax / 100.0 * w, w))
            bottom = max(top + 1, min(ymax / 100.0 * h, h))
            cropped = img.crop((left, top, right, bottom))
        crop_filename = f'pdf_crop_{task_id}_{dependencies.uuid.uuid4().hex[:12]}.png'
        crop_filepath = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR) / crop_filename
        cropped.save(crop_filepath, format='PNG')
        img_url = f'/{dependencies.state.UPLOAD_DIR_REL}/tmp/{crop_filename}'
        if project_id:
            dependencies.state.DOCUMENT_PROJECTS.register_assets(project_id, [img_url])
            dependencies.state.DOCUMENT_TASKS.add_temp_asset(task_id, img_url)
        elif not dependencies.state.DOCUMENT_TASKS.add_temp_asset(task_id, img_url):
            crop_filepath.unlink(missing_ok=True)
            raise ValueError('任务记录已过期，无法登记裁剪图片。')
        return {'status': 'success', 'image_path': img_url}
    except ValueError as e:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'手动裁剪失败: {str(e)}'}, status_code=400)
    except Exception as e:
        return dependencies.JSONResponse(content={'status': 'error', 'message': f'手动裁剪失败: {str(e)}'}, status_code=500)


def _queue_document_upload(content, filename, document_type, client_request_id, options, function, call_args, *, dependencies: DocumentTaskServiceDependencies):
    """One request identity owns one immutable upload and one dispatch."""
    with dependencies.state.DOCUMENT_TASKS._request_lock:
        if client_request_id:
            with dependencies.state.DOCUMENT_TASKS._lock:
                previous_id = next((identifier for (identifier, record) in dependencies.state.DOCUMENT_TASKS._records.items() if record.state.get('client_request_id') == client_request_id), None)
            previous = dependencies.state.DOCUMENT_TASKS.snapshot(previous_id) if previous_id else None
            if previous is not None:
                source = previous.get('document_input') or {}
                if source.get('sha256') != dependencies.hashlib.sha256(content).hexdigest() or source.get('bytes') != len(content) or source.get('filename') != filename or (source.get('document_type') != document_type) or (source.get('options') != options):
                    raise dependencies.HTTPException(status_code=409, detail='本次上传标识已绑定其他文件或设置，请重新选择文件。')
                return {'status': 'success', 'task_id': previous_id, 'client_request_id': client_request_id, **({'project_id': previous['project_id']} if previous.get('project_id') else {})}
        project_id = None
        if document_type == 'pdf' and dependencies.state.DOCUMENT_PROJECTS and (not dependencies.state.PDF_CLOUD_ONLY):
            digest = dependencies.hashlib.sha256(content).hexdigest()
            existing = next((row for row in dependencies.state.DOCUMENT_PROJECTS.find_existing(digest) if row.get('options') == options), None)
            if existing:
                project_id = existing['project_id']
                dependencies.state.DOCUMENT_PROJECTS.touch(project_id)
                live = dependencies.state.DOCUMENT_TASKS.snapshot(existing.get('task_id')) if existing.get('task_id') else None
                if live:
                    return {'status': 'success', 'task_id': existing['task_id'], 'project_id': project_id, 'reused_project': True, 'client_request_id': client_request_id}
                return {**dependencies._dispatch_document_project(project_id), 'reused_project': True, 'client_request_id': client_request_id}
        task_id = str(dependencies.uuid.uuid4())
        if document_type == 'pdf' and dependencies.state.DOCUMENT_PROJECTS and (not dependencies.state.PDF_CLOUD_ONLY):
            try:
                project = dependencies.state.DOCUMENT_PROJECTS.create(content, filename, options, dependencies.copy.deepcopy(dependencies.get_current_curriculum()), task_id)
                project_id = project['project_id']
            except dependencies.DocumentProjectError as exc:
                raise dependencies.HTTPException(400, str(exc)) from exc
        source_input = dependencies._register_document_input(task_id, content, document_type, filename, **options)
        try:
            dependencies.state.DOCUMENT_TASKS.create(task_id, status='pending', document_type=document_type, temp_assets=[], log='任务已排队，正在准备提取题目与配图...', client_request_id=client_request_id, document_input=source_input, **{'project_id': project_id} if project_id else {})
            if dependencies.state.DOCUMENT_TASKS.request_cancelled(client_request_id):
                dependencies.state.DOCUMENT_TASKS.cancel(task_id)
            else:
                try:
                    dependencies.state.DOCUMENT_TASKS.submit(task_id, function, task_id, content, filename, *call_args)
                except ValueError:
                    if not dependencies.state.DOCUMENT_TASKS.is_cancelled(task_id):
                        raise
        except dependencies.TaskQueueFull as exc:
            dependencies.state.DOCUMENT_TASKS.remove(task_id)
            dependencies.state.DOCUMENT_TASK_INPUTS.pop(task_id, None)
            raise dependencies.HTTPException(status_code=429, detail=str(exc)) from exc
        return {'status': 'success', 'task_id': task_id, 'client_request_id': client_request_id, **({'project_id': project_id, 'project_revision': 0, 'expires_at': project['expires_at']} if project_id else {})}


def get_document_task_by_request(client_request_id: str, *, dependencies: DocumentTaskServiceDependencies):
    request_id = dependencies._document_request_id(client_request_id)
    if not request_id:
        raise dependencies.HTTPException(status_code=400, detail='缺少文档请求标识。')
    with dependencies.state.DOCUMENT_TASKS._lock:
        task_id = next((key for (key, record) in dependencies.state.DOCUMENT_TASKS._records.items() if record.state.get('client_request_id') == request_id), None)
    task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id) if task_id else None
    if task is not None:
        return dependencies._document_status(task_id, task)
    if dependencies.state.DOCUMENT_TASKS.request_cancelled(request_id):
        return {'status': 'cancelled', 'client_request_id': request_id, 'can_resume': False}
    raise dependencies.HTTPException(status_code=404, detail='尚未找到本次上传任务，请稍后重新连接。')


def cancel_document_task_by_request(payload: dict, *, dependencies: DocumentTaskServiceDependencies):
    request_id = dependencies._document_request_id(payload.get('client_request_id'))
    if not request_id:
        raise dependencies.HTTPException(status_code=400, detail='缺少文档请求标识。')
    records = dependencies.state.DOCUMENT_TASKS.cancel_by_request(request_id, document_type=payload.get('document_type'))
    if any((record and record.get('status') in {'completed', 'error'} for record in records)):
        return {'status': 'success', 'cancelled': False, 'task_status': records[0]['status'], 'task_id': records[0].get('task_id')}
    return {'status': 'success', 'cancelled': bool(records), 'cancellation_pending': not bool(records)}


def resume_document_task(task_id: str, *, dependencies: DocumentTaskServiceDependencies):
    task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
    if not task or not task.get('document_input'):
        raise dependencies.HTTPException(status_code=404, detail='没有可继续处理的原文档。')
    if task.get('status') not in {'error', 'interrupted'}:
        raise dependencies.HTTPException(status_code=409, detail='该任务当前不能继续处理。')
    if dependencies.state.PDF_CLOUD_ONLY and task.get('document_type') == 'pdf':
        raise dependencies.HTTPException(status_code=409, detail='PDF 已恢复原版处理流程，请重新上传试卷。')
    source = task['document_input']
    content = dependencies._read_document_source(task_id, task)
    if source.get('curriculum_sha256') != dependencies._document_curriculum_sha256():
        raise dependencies.HTTPException(status_code=409, detail='教材目录已变化，请保留原结果与原文件，重新上传后按当前教材分类。')
    options = source.get('options')
    option_names = {'generate_answers', 'page_range', 'pdf_strategy', 'pdf_verify_suspicions', 'paper_title'} if source.get('document_type') == 'pdf' else {'generate_answers', 'docx_verify_suspicions', 'paper_title'}
    if source.get('document_type') not in {'pdf', 'docx'} or not isinstance(options, dict) or set(options) != option_names or (not isinstance(source.get('filename'), str)):
        raise dependencies.HTTPException(status_code=409, detail='原文档解析设置不完整，请重新上传。')
    if type(options.get('generate_answers')) is not bool or not isinstance(options.get('paper_title'), str) or (source['document_type'] == 'pdf' and (type(options.get('pdf_verify_suspicions')) is not bool or options.get('pdf_strategy') not in dependencies.PDF_STRATEGIES or (options.get('page_range') is not None and (not isinstance(options['page_range'], str))))) or (source['document_type'] == 'docx' and type(options.get('docx_verify_suspicions')) is not bool):
        raise dependencies.HTTPException(status_code=409, detail='原文档解析设置无效，请重新上传。')
    options = dict(options)
    options.pop('paper_title', None)
    function = dependencies.run_pdf_parsing_task if source['document_type'] == 'pdf' else dependencies.run_docx_parsing_task
    checkpoint = task.get('pdf_resume_state') if source['document_type'] == 'pdf' else task.get('docx_resume_state') or task.get('docx_source_cache')
    try:
        dependencies.state.DOCUMENT_TASKS.restart(task_id)
        dependencies.state.DOCUMENT_TASKS.submit(task_id, function, task_id, content, source['filename'], **options, resume_state=checkpoint)
    except dependencies.TaskQueueFull as exc:
        dependencies.state.DOCUMENT_TASKS.fail(task_id, str(exc))
        raise dependencies.HTTPException(status_code=429, detail=str(exc))
    except ValueError as exc:
        raise dependencies.HTTPException(status_code=409, detail=str(exc))
    return {'status': 'success', 'task_id': task_id}


def _read_document_source(task_id, task, *, dependencies: DocumentTaskServiceDependencies):
    source = task.get('document_input')
    if not isinstance(source, dict) or type(source.get('bytes')) is not int or (not 0 <= source['bytes'] <= dependencies.MAX_PDF_BYTES) or (not isinstance(source.get('sha256'), str)):
        raise dependencies.HTTPException(status_code=409, detail='原文档恢复记录不完整，请重新上传。')
    try:
        content = dependencies.state.DOCUMENT_TASK_STORE.source(task_id) if dependencies.state.DOCUMENT_TASK_STORE and (not (dependencies.state.PDF_CLOUD_ONLY and source.get('document_type') == 'pdf')) else dependencies.state.DOCUMENT_TASK_INPUTS[task_id]
    except (OSError, KeyError, ValueError):
        raise dependencies.HTTPException(status_code=409, detail='恢复所需的原文档已不可用，请重新上传。')
    if len(content) != source['bytes'] or dependencies.hashlib.sha256(content).hexdigest() != source['sha256']:
        raise dependencies.HTTPException(status_code=409, detail='原文档已变化，未发送任何识别请求。')
    return content


def download_document_source(task_id: str, *, dependencies: DocumentTaskServiceDependencies):
    from urllib.parse import quote
    task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
    if not task or not task.get('document_input'):
        raise dependencies.HTTPException(status_code=404, detail='没有可下载的原文档。')
    content = dependencies._read_document_source(task_id, task)
    source = task['document_input']
    filename = str(source.get('filename') or ('原文档.pdf' if source.get('document_type') == 'pdf' else '原文档.docx'))
    filename = filename.replace('\\', '/').rsplit('/', 1)[-1]
    media_type = 'application/pdf' if source.get('document_type') == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return dependencies.Response(content=content, media_type=media_type, headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename, safe='')})


def retain_document_task(task_id: str, *, dependencies: DocumentTaskServiceDependencies):
    if dependencies.state.DOCUMENT_TASKS.retain(task_id):
        return {'status': 'success'}
    raise dependencies.HTTPException(status_code=404, detail='任务已过期或不可续期；已生成图片仍可通过原地址恢复。')
