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
    BackgroundTask: Any
    DATABASE_PATH: Any
    DATA_BACKUP_DIR: Any
    FileResponse: Any
    HTTPException: Any
    MAX_LIBRARY_ARCHIVE_BYTES: Any
    Path: Any
    SYSTEM_GENERATED_DIR: Any
    create_full_backup: Any
    datetime: Any
    export_library_zip: Any
    get_active_version_code: Any
    import_library_zip: Any
    inspect_library_zip: Any
    preview_library_questions: Any
    schedule_database_export: Any
    select_library_question_ids: Any
    shutil: Any
    state: RuntimeState
    tempfile: Any



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
        if dependencies.Path(file.filename or '').suffix.lower() != '.zip':
            raise dependencies.HTTPException(status_code=400, detail='请选择本题库导出功能生成的 ZIP 分享包。')
        transfer_root = dependencies.SYSTEM_GENERATED_DIR / 'library_transfer'
        transfer_root.mkdir(parents=True, exist_ok=True)
        workspace = dependencies.Path(dependencies.tempfile.mkdtemp(prefix='import-', dir=transfer_root))
        archive = workspace / 'library.zip'
        with archive.open('xb') as output:
            size = 0
            while (chunk := file.file.read(1024 * 1024)):
                size += len(chunk)
                if size > dependencies.MAX_LIBRARY_ARCHIVE_BYTES:
                    raise dependencies.HTTPException(status_code=413, detail='题库分享包不能超过 512 MiB，请按来源分批导出。')
                output.write(chunk)
        dependencies.inspect_library_zip(archive)
        with dependencies.state._METADATA_SAVE_LOCK:
            import_version = dependencies.get_active_version_code()
            try:
                backup_path = dependencies.create_full_backup(database_path=dependencies.Path(dependencies.DATABASE_PATH), uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), metadata_path=dependencies.DATA_BACKUP_DIR / 'custom_metadata.json', output_dir=dependencies.DATA_BACKUP_DIR / 'snapshots', retention=None)
            except Exception as exc:
                raise dependencies.HTTPException(status_code=500, detail='导入前的自动备份失败，尚未导入题目。请检查本地存储空间和现有图片。') from exc
            result = dependencies.import_library_zip(db, archive, uploads_dir=dependencies.Path(dependencies.state.UPLOAD_DIR), active_version=import_version)
        dependencies.schedule_database_export(background_tasks, operation='library_transfer')
        return {'status': 'success', 'imported_count': result['imported_count'], 'image_count': result['image_count'], 'backup_path': str(backup_path), 'active_version_code': import_version}
    except dependencies.HTTPException:
        raise
    except ValueError as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise dependencies.HTTPException(status_code=500, detail='题库导入失败，本次新增内容已回滚。请检查本地存储空间。') from exc
    finally:
        if workspace is not None:
            dependencies.shutil.rmtree(workspace, ignore_errors=True)
        try:
            file.file.close()
        except OSError:
            pass
