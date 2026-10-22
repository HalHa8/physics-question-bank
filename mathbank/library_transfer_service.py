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
class LibraryTransferServiceDependencies:
    ASSET_LIFECYCLE_LOCK: Any
    BackgroundTask: Any
    DATABASE_PATH: Any
    DATA_BACKUP_DIR: Any
    FileResponse: Any
    HTTPException: Any
    JSONResponse: Any
    LibraryTransferTasks: Any
    MAX_LIBRARY_ARCHIVE_BYTES: Any
    MAX_LIBRARY_QUESTIONS: Any
    Path: Any
    SYSTEM_GENERATED_DIR: Any
    TransferTaskConflict: Any
    TransferTaskError: Any
    TransferTaskQueueFull: Any
    _check_library_import_storage: Any
    _library_transfer_tasks: Any
    _receive_library_archive: Any
    _run_library_export_task: Any
    _run_library_import_task: Any
    _sharing_backup: Any
    _sharing_post_commit_export: Any
    _transfer_task_http_error: Any
    check_database_write_access: Any
    check_directory_access: Any
    create_full_backup: Any
    datetime: Any
    export_database_to_files: Any
    export_library_zip: Any
    get_active_version_code: Any
    harden_private_path: Any
    hashlib: Any
    import_library_zip: Any
    inspect_library_zip: Any
    log_transfer_error: Any
    normalize_transfer_task_id: Any
    os: Any
    prepare_library_import: Any
    preview_library_questions: Any
    schedule_database_export: Any
    select_library_question_ids: Any
    shutil: Any
    state: RuntimeState
    tempfile: Any
    transfer_error: Any



def preview_library_transfer(payload: dict, db: Session=Depends(get_db), *, dependencies: LibraryTransferServiceDependencies):
    """Read one compact page for the sharing selector, without full answers."""
    if set(payload) - {'filters', 'question_ids', 'page', 'page_size'}:
        raise dependencies.HTTPException(status_code=400, detail='题目预览参数无效')
    if 'question_ids' in payload and (not isinstance(payload['question_ids'], list)):
        raise dependencies.HTTPException(status_code=400, detail='勾选题目须为 ID 列表')
    try:
        return dependencies.preview_library_questions(db, filters=payload.get('filters'), question_ids=payload.get('question_ids'), page=payload.get('page', 1), page_size=payload.get('page_size', 10), active_version=dependencies.get_active_version_code())
    except (ValueError, TypeError) as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc


def select_library_transfer_ids(payload: dict, db: Session=Depends(get_db), *, dependencies: LibraryTransferServiceDependencies):
    """Read only stable IDs when selecting all results across pages."""
    if set(payload) - {'filters'}:
        raise dependencies.HTTPException(status_code=400, detail='全选筛选结果参数无效')
    try:
        ids = dependencies.select_library_question_ids(db, filters=payload.get('filters'), active_version=dependencies.get_active_version_code())
        return {'ids': ids, 'total': len(ids)}
    except (ValueError, TypeError) as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc


def export_library_transfer(payload: dict, db: Session=Depends(get_db), *, dependencies: LibraryTransferServiceDependencies):
    """Download a self-contained sharing archive from one database snapshot."""
    if set(payload) - {'source_keywords', 'question_ids'}:
        raise dependencies.HTTPException(status_code=400, detail='题库分享导出参数无效')
    if 'question_ids' in payload and (not isinstance(payload['question_ids'], list)):
        raise dependencies.HTTPException(status_code=400, detail='勾选题目须为 ID 列表')
    workspace = None
    try:
        transfer_root = dependencies.SYSTEM_GENERATED_DIR / 'library_transfer'
        transfer_root.mkdir(parents=True, exist_ok=True)
        workspace = dependencies.Path(dependencies.tempfile.mkdtemp(prefix='export-', dir=transfer_root))
        archive = workspace / 'library.zip'
        summary = dependencies.export_library_zip(db, archive, uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), source_keywords=payload.get('source_keywords', []), question_ids=payload.get('question_ids'), active_version=dependencies.get_active_version_code())
        timestamp = dependencies.datetime.datetime.now(dependencies.datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        return dependencies.FileResponse(archive, media_type='application/zip', filename=f"PhysicsBank-{summary['question_count']}questions-{timestamp}.zip", headers={'Cache-Control': 'no-store'}, background=dependencies.BackgroundTask(dependencies.shutil.rmtree, workspace, ignore_errors=True))
    except Exception as exc:
        if workspace is not None:
            dependencies.shutil.rmtree(workspace, ignore_errors=True)
        if isinstance(exc, ValueError):
            raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc
        raise dependencies.HTTPException(status_code=500, detail='题库分享包生成失败，请检查图片文件和本地存储空间。') from exc



def import_library_transfer(background_tasks: BackgroundTasks, file: UploadFile=File(...), db: Session=Depends(get_db), *, dependencies: LibraryTransferServiceDependencies):
    """Validate, back up and append; importing the same archive appends again."""
    workspace = None
    try:
        transfer_root = dependencies.SYSTEM_GENERATED_DIR / 'library_transfer'
        transfer_root.mkdir(parents=True, exist_ok=True)
        workspace = dependencies.Path(dependencies.tempfile.mkdtemp(prefix='import-', dir=transfer_root))
        archive = workspace / 'library.zip'
        dependencies._receive_library_archive(file, archive)
        with dependencies.prepare_library_import(archive, workspace_dir=workspace) as prepared:
            with dependencies.ASSET_LIFECYCLE_LOCK, dependencies.state._METADATA_SAVE_LOCK:
                dependencies._check_library_import_storage(prepared)
                import_version = dependencies.get_active_version_code()
                backup_path = dependencies._sharing_backup()
                result = dependencies.import_library_zip(db, archive, uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), active_version=import_version, prepared=prepared)
        dependencies.schedule_database_export(background_tasks, operation='library_transfer')
        return {'status': 'success', 'imported_count': result['imported_count'], 'image_count': result['image_count'], 'backup_path': str(backup_path), 'active_version_code': import_version}
    except dependencies.HTTPException:
        raise
    except ValueError as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        dependencies.log_transfer_error('synchronous', 'import', 'importing', exc)
        error = dependencies.transfer_error(exc)
        raise dependencies.HTTPException(status_code=500, detail=error['message']) from exc
    finally:
        if workspace is not None:
            dependencies.shutil.rmtree(workspace, ignore_errors=True)
        try:
            file.file.close()
        except OSError:
            pass


def _sharing_backup(*, dependencies: LibraryTransferServiceDependencies):
    try:
        return dependencies.create_full_backup(database_path=dependencies.Path(dependencies.DATABASE_PATH), uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), metadata_path=dependencies.DATA_BACKUP_DIR / 'custom_metadata.json', output_dir=dependencies.DATA_BACKUP_DIR / 'snapshots', retention=None)
    except Exception as exc:
        raise dependencies.TransferTaskError('backup', '导入前自动备份失败，尚未导入题目。请检查备份目录、存储空间和现有图片。') from exc


def _sharing_post_commit_export(*, dependencies: LibraryTransferServiceDependencies):
    try:
        if dependencies.state.IS_TESTING:
            dependencies.export_database_to_files()
        else:
            dependencies.state.DATABASE_EXPORT_QUEUE.request(operation='library_transfer')
    except Exception as exc:
        dependencies.log_transfer_error('post-commit', 'import', 'database_export', exc)


def _check_library_import_storage(prepared, *, dependencies: LibraryTransferServiceDependencies):
    dependencies.check_database_write_access(dependencies.Path(dependencies.DATABASE_PATH))
    if prepared.summary['image_count']:
        dependencies.check_directory_access(dependencies.Path(dependencies.state.UPLOAD_DIR), label='题目图片目录（static/uploads）')


def _run_library_import_task(directory, progress, *, dependencies: LibraryTransferServiceDependencies):
    from mathbank.database import SessionLocal
    archive = directory / 'input.zip'
    with dependencies.prepare_library_import(archive, workspace_dir=directory / 'prepared', progress=progress) as prepared:
        progress('waiting')
        with dependencies.ASSET_LIFECYCLE_LOCK, dependencies.state._METADATA_SAVE_LOCK:
            dependencies._check_library_import_storage(prepared)
            import_version = dependencies.get_active_version_code()
            progress('backup')
            backup_path = dependencies._sharing_backup()
            progress('backup', current=1, total=1, result={'backup_path': str(backup_path), 'active_version_code': import_version})
            with SessionLocal() as db:
                result = dependencies.import_library_zip(db, archive, uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), active_version=import_version, prepared=prepared, progress=progress)
    dependencies._sharing_post_commit_export()
    return {'imported_count': result['imported_count'], 'image_count': result['image_count'], 'backup_path': str(backup_path), 'active_version_code': import_version}


def _run_library_export_task(directory, payload, progress, *, dependencies: LibraryTransferServiceDependencies):
    from mathbank.database import SessionLocal
    progress('waiting')
    with dependencies.ASSET_LIFECYCLE_LOCK, dependencies.state._METADATA_SAVE_LOCK, SessionLocal() as db:
        result = dependencies.export_library_zip(db, directory / 'library.zip', uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), source_keywords=payload.get('source_keywords', []), question_ids=payload.get('question_ids'), active_version=dependencies.get_active_version_code(), progress=progress)
    return {'question_count': result['question_count'], 'image_count': result['image_count'], 'download_url': f'/api/library-transfer/tasks/{directory.name}/download'}


def _library_transfer_tasks(*, dependencies: LibraryTransferServiceDependencies):
    root = dependencies.SYSTEM_GENERATED_DIR / 'library_transfer_tasks'
    with dependencies.state._LIBRARY_TRANSFER_TASKS_LOCK:
        if dependencies.state._LIBRARY_TRANSFER_TASKS is not None and dependencies.state._LIBRARY_TRANSFER_TASKS.root != root:
            dependencies.state._LIBRARY_TRANSFER_TASKS.close()
            dependencies.state._LIBRARY_TRANSFER_TASKS = None
        if dependencies.state._LIBRARY_TRANSFER_TASKS is None:
            dependencies.state._LIBRARY_TRANSFER_TASKS = dependencies.LibraryTransferTasks(root, run_import=dependencies._run_library_import_task, run_export=dependencies._run_library_export_task)
        return dependencies.state._LIBRARY_TRANSFER_TASKS


def _receive_library_archive(file, archive, *, dependencies: LibraryTransferServiceDependencies):
    if dependencies.Path(file.filename or '').suffix.lower() != '.zip':
        raise dependencies.HTTPException(status_code=400, detail='请选择本题库导出功能生成的 ZIP 分享包。')
    (digest, size) = (dependencies.hashlib.sha256(), 0)
    with archive.open('xb') as output:
        dependencies.harden_private_path(archive)
        while (chunk := file.file.read(1024 * 1024)):
            size += len(chunk)
            if size > dependencies.MAX_LIBRARY_ARCHIVE_BYTES:
                raise dependencies.HTTPException(status_code=413, detail='题库分享包不能超过 512 MiB，请按来源分批导出。')
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        dependencies.os.fsync(output.fileno())
    return digest.hexdigest()


def _transfer_task_http_error(exc, *, dependencies: LibraryTransferServiceDependencies):
    if isinstance(exc, dependencies.TransferTaskConflict):
        return dependencies.HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, dependencies.TransferTaskQueueFull):
        return dependencies.HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '2'})
    if isinstance(exc, ValueError):
        return dependencies.HTTPException(status_code=400, detail=str(exc))
    dependencies.log_transfer_error('request', 'sharing', 'submission', exc)
    error = dependencies.transfer_error(exc)
    return dependencies.HTTPException(status_code=500, detail=error['message'])


def start_library_import_task(file: UploadFile=File(...), client_request_id: str=Form(...), *, dependencies: LibraryTransferServiceDependencies):
    try:
        task_id = dependencies.normalize_transfer_task_id(client_request_id)
        tasks = dependencies._library_transfer_tasks()
        with tasks.upload_workspace() as workspace:
            archive = workspace / 'upload.zip'
            digest = dependencies._receive_library_archive(file, archive)
            (result, created) = tasks.submit_import(task_id, archive, digest)
        return dependencies.JSONResponse(result, status_code=202 if created else 200, headers={'Cache-Control': 'no-store'})
    except dependencies.HTTPException:
        raise
    except dependencies.TransferTaskConflict as exc:
        if exc.active_task_id:
            return dependencies.JSONResponse({'detail': str(exc), 'active_task_id': exc.active_task_id, 'code': 'active_import'}, status_code=409, headers={'Cache-Control': 'no-store'})
        raise dependencies._transfer_task_http_error(exc) from exc
    except Exception as exc:
        raise dependencies._transfer_task_http_error(exc) from exc
    finally:
        try:
            file.file.close()
        except OSError:
            pass


def start_library_export_task(payload: dict, *, dependencies: LibraryTransferServiceDependencies):
    try:
        if set(payload) - {'client_request_id', 'source_keywords', 'question_ids'}:
            raise ValueError('题库分享导出参数无效')
        task_id = dependencies.normalize_transfer_task_id(payload.get('client_request_id'))
        options = {key: value for (key, value) in payload.items() if key != 'client_request_id'}
        if 'question_ids' in options:
            ids = options['question_ids']
            if not isinstance(ids, list) or not 0 < len(ids) <= dependencies.MAX_LIBRARY_QUESTIONS or any((type(value) is not int or not 1 <= value <= 2 ** 63 - 1 for value in ids)) or (len(set(ids)) != len(ids)):
                raise ValueError('勾选题目须为不重复的正整数 ID 列表')
        keywords = options.get('source_keywords', [])
        if not isinstance(keywords, list) or len(keywords) > 50 or any((not isinstance(value, str) or not value.strip() or len(value) > 200 for value in keywords)):
            raise ValueError('来源筛选最多支持 50 个非空关键词')
        (result, created) = dependencies._library_transfer_tasks().submit_export(task_id, options)
        return dependencies.JSONResponse(result, status_code=202 if created else 200, headers={'Cache-Control': 'no-store'})
    except Exception as exc:
        raise dependencies._transfer_task_http_error(exc) from exc


def get_library_transfer_task(task_id: str, *, dependencies: LibraryTransferServiceDependencies):
    try:
        result = dependencies._library_transfer_tasks().get(task_id)
    except Exception as exc:
        raise dependencies._transfer_task_http_error(exc) from exc
    if result is None:
        raise dependencies.HTTPException(status_code=404, detail='未找到题库分享任务')
    return dependencies.JSONResponse(result, headers={'Cache-Control': 'no-store'})


def download_library_transfer_task(task_id: str, *, dependencies: LibraryTransferServiceDependencies):
    try:
        (archive, summary) = dependencies._library_transfer_tasks().download(task_id)
    except KeyError as exc:
        raise dependencies.HTTPException(status_code=404, detail='未找到题库分享任务') from exc
    except FileNotFoundError as exc:
        raise dependencies.HTTPException(status_code=410, detail='导出文件已不存在，请重新导出') from exc
    except Exception as exc:
        raise dependencies._transfer_task_http_error(exc) from exc
    return dependencies.FileResponse(archive, media_type='application/zip', filename=f"PhysicsBank-{summary.get('question_count', 0)}questions-{task_id}.zip", headers={'Cache-Control': 'no-store'})
