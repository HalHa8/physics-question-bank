"""Explicit application boundary for adapted MathBank capabilities."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from mathbank.application_state import RuntimeState
from mathbank.ai_providers import MultimodalProviderConfig


@dataclass(frozen=True)
class DocumentProjectRuntimeDependencies:
    AssetSecurityError: Any
    DocumentProjectService: Any
    HTTPException: Any
    Path: Any
    TaskQueueFull: Any
    _delete_task_temp_assets: Any
    _document_project_service: Any
    _read_document_source: Any
    _referenced_question_assets: Any
    _register_document_input: Any
    _release_document_project_assets: Any
    _restore_document_project_asset: Any
    copy: Any
    resolve_upload_asset: Any
    run_pdf_parsing_task: Any
    state: RuntimeState
    uuid: Any



def _document_project_service(*, dependencies: DocumentProjectRuntimeDependencies):
    if dependencies.state.PDF_CLOUD_ONLY or dependencies.state.DOCUMENT_PROJECTS is None:
        return None
    return dependencies.DocumentProjectService(dependencies.state.DOCUMENT_PROJECTS, dependencies.state.DOCUMENT_TASKS, source_reader=lambda task_id, task: dependencies._read_document_source(task_id, task), asset_resolver=lambda url: dependencies.resolve_upload_asset(url, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False))


def _sync_document_project(task_id, snapshot, *, dependencies: DocumentProjectRuntimeDependencies):
    service = dependencies._document_project_service()
    if service:
        service.sync(task_id, snapshot)


def _restore_document_project_asset(url, *, dependencies: DocumentProjectRuntimeDependencies):
    """Old task TTL may have retired pixels before the project was adopted."""
    path = dependencies.resolve_upload_asset(url, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
    if not path.exists():
        from mathbank.asset_lifecycle import restore_asset
        restore_asset(path, uploads_dir=dependencies.state.UPLOAD_DIR)
    return path


def _dispatch_document_project(project_id, analyze=False, *, dependencies: DocumentProjectRuntimeDependencies):
    service = dependencies._document_project_service()
    if not service:
        raise dependencies.HTTPException(404, '本地工程服务未启用。')
    metadata = dependencies.state.DOCUMENT_PROJECTS.touch(project_id)
    previous = dependencies.state.DOCUMENT_PROJECTS.load_task(project_id)
    old_task_id = metadata.get('task_id')
    live = dependencies.state.DOCUMENT_TASKS.snapshot(old_task_id) if old_task_id else None
    if live and old_task_id in service.active_task_ids():
        raise dependencies.HTTPException(409, '该工程仍在处理中，请等待当前任务结束。')
    draft = dependencies.state.DOCUMENT_PROJECTS.get_draft(project_id).get('payload') or {}
    state = service.checkpoint(project_id, analyze=analyze)
    content = dependencies.state.DOCUMENT_PROJECTS.load_source(project_id)
    options = dict(metadata['options'])
    task_id = str(dependencies.uuid.uuid4())
    if state:
        from mathbank.pdf_task_resume import prepare_pdf_checkpoint, seal_pdf_checkpoint
        state = prepare_pdf_checkpoint(state, task_id=state['task_id'], document_sha256=metadata['source_sha256'], page_indices=state['page_indices'], strategy=state['strategy'], verify_suspicions=state['verify_suspicions'], resolve_asset=dependencies._restore_document_project_asset)
        old_namespace = state.get('source_namespace') or state['task_id'].replace('-', '')[:16]
        state['run'] -= 1
        state.update(task_id=task_id, source_namespace=old_namespace)
        if analyze:
            state.pop('accepted_split', None)
            state.pop('split_input', None)
            state['page_edits'] = dependencies.copy.deepcopy(draft.get('page_edits') or [])
            state['analyze_local_only'] = True
            state['force_structure'] = True
        state = seal_pdf_checkpoint(state, assets=[], resolve_asset=dependencies._restore_document_project_asset)
    source_input = dependencies._register_document_input(task_id, content, 'pdf', metadata['filename'], **options)
    dependencies.state.DOCUMENT_PROJECTS.bind_task(project_id, task_id)
    carried_assets = []
    for url in previous.get('temp_assets') or []:
        if state and url not in state.get('assets', {}):
            path = dependencies.resolve_upload_asset(url, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
            if path.name.startswith(('pdf_page_', 'pdf_detail_')) and (not path.is_file()):
                continue
        carried_assets.append(url)
    base = dict(project_id=project_id, document_type='pdf', document_input=source_input, temp_assets=carried_assets, diagnostics=dependencies.copy.deepcopy(previous.get('diagnostics') or {}), pdf_source_pages=dependencies.copy.deepcopy(previous.get('pdf_source_pages') or []))
    if state:
        base['pdf_resume_state'] = state
    pending_fragment_source = bool(state and state.get('transcription_protocol') == 'mathbank.pdf-page-fragments.v2' and any((str(index) not in state.get('pages', {}) for index in state['page_indices'] if index not in state.get('blank_page_indices', []))))
    if draft.get('questions') and (not analyze) and (not pending_fragment_source):
        restored_diagnostics = dependencies.copy.deepcopy(draft.get('diagnostics') or previous.get('diagnostics') or {})
        restored_diagnostics['pdf_draft_restore'] = {'working_copy': True}
        restored_partial = draft.get('partial')
        if type(restored_partial) is not bool:
            restored_partial = previous.get('partial')
        if type(restored_partial) is not bool:
            local_draft = restored_diagnostics.get('pdf_local_draft') or {}
            restored_partial = bool(restored_diagnostics.get('pdf_project_partial') or local_draft.get('status') in {'manual', 'partial'} or local_draft.get('unresolved_ranges') or local_draft.get('manual_reasons'))
        dependencies.state.DOCUMENT_TASKS.create(task_id, **base)
        dependencies.state.DOCUMENT_TASKS.complete(task_id, data=draft['questions'], log='已恢复本地校对稿，可继续编辑或入库。', partial=restored_partial, page_images=draft.get('pageImages') or previous.get('page_images') or [], page_numbers=draft.get('pageNumbers') or previous.get('page_numbers') or [], diagnostics=restored_diagnostics)
    else:
        dependencies.state.DOCUMENT_TASKS.create(task_id, status='pending', log='正在复用本地工程中的已完成阶段...', **base)
        try:
            dependencies.state.DOCUMENT_TASKS.submit(task_id, dependencies.run_pdf_parsing_task, task_id, content, metadata['filename'], generate_answers=options.get('generate_answers', False), page_range=options.get('page_range'), pdf_strategy=options.get('pdf_strategy', 'layout_aware'), pdf_verify_suspicions=options.get('pdf_verify_suspicions', True), resume_state=state)
        except dependencies.TaskQueueFull as exc:
            dependencies.state.DOCUMENT_TASKS.fail(task_id, '当前任务较多，工程已保留，请稍后继续。')
            raise dependencies.HTTPException(429, str(exc)) from exc
    return {'status': 'success', 'task_id': task_id, 'project_id': project_id, 'project_revision': metadata['revision'], 'expires_at': metadata['expires_at']}


def _release_document_project_assets(urls, *, dependencies: DocumentProjectRuntimeDependencies):
    """Purge only owned page/detail caches; question figures remain recoverable."""
    if not urls:
        return {'deleted': 0, 'retained_figures': 0}
    from mathbank.database import SessionLocal
    try:
        protected = dependencies.state.DOCUMENT_PROJECTS.referenced_assets() if dependencies.state.DOCUMENT_PROJECTS else set()
        with SessionLocal() as db:
            referenced = dependencies._referenced_question_assets(db)
        with dependencies.state.DOCUMENT_TASKS._lock:
            for record in dependencies.state.DOCUMENT_TASKS._records.values():
                if record.future is not None:
                    protected.update(record.state.get('temp_assets') or [])
    except Exception:
        return {'deleted': 0, 'retained': len(urls or []), 'cleanup_pending': True}
    deleted = 0
    figures = []
    for url in set(urls or []):
        if url in protected:
            continue
        try:
            path = dependencies.resolve_upload_asset(url, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
            if path.parent != dependencies.Path(dependencies.state.TMP_UPLOAD_DIR).resolve() or path in referenced:
                continue
            if path.name.startswith(('pdf_page_', 'pdf_detail_')) and path.is_file() and (not path.is_symlink()):
                path.unlink()
                deleted += 1
            else:
                figures.append(url)
        except (dependencies.AssetSecurityError, OSError):
            continue
    if figures:
        dependencies._delete_task_temp_assets(figures)
    return {'deleted': deleted, 'retained_figures': len(figures)}



def _maintain_document_projects(*, dependencies: DocumentProjectRuntimeDependencies):
    while not dependencies.state._DOCUMENT_PROJECT_STOP.is_set():
        try:
            service = dependencies._document_project_service()
            if service:
                result = dependencies.state.DOCUMENT_PROJECTS.cleanup(active_task_ids=service.active_task_ids())
                dependencies._release_document_project_assets(result.get('temp_assets') or [])
        except Exception as exc:
            print(f'[Document Projects] Cache cleanup deferred ({type(exc).__name__}).')
        dependencies.state._DOCUMENT_PROJECT_STOP.wait(60)
