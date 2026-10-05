"""Document task service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from typing import Optional
from fastapi import UploadFile, File, Form
from mathbank.document_import_context import DocumentImportDependencies


@dataclass(frozen=True)
class DocumentTaskServiceDependencies:
    state: RuntimeState
    DocumentImportDependencies: Any
    Image: Any
    JSONResponse: Any
    MAX_PDF_BYTES: Any
    PDF_STRATEGIES: Any
    Path: Any
    TaskQueueFull: Any
    UploadTooLargeError: Any
    _delete_task_temp_assets: Callable
    build_document_import_dependencies: Callable
    docx_import_service: Any
    extract_docx_markdown: Any
    find_source_page_by_overlap: Any
    inspect_and_extract_pdf: Any
    normalize_fillin_macro: Any
    ocr_pdf_page_image: Callable
    parse_paper_text_internal: Callable
    pdf_import_service: Any
    post_process_pdf_parsed_questions: Callable
    post_process_questions: Any
    read_stream_limited: Any
    reconcile_visible_math: Any
    run_docx_parsing_task: Callable
    run_pdf_parsing_task: Callable
    uuid: Any


def build_document_import_dependencies(*, dependencies: DocumentTaskServiceDependencies) -> DocumentImportDependencies:
    """Bind the existing runtime once per task; services never import main."""
    return dependencies.DocumentImportDependencies(
        tasks=dependencies.state.DOCUMENT_TASKS, ocr_semaphore=dependencies.state.PDF_OCR_SEMAPHORE,
        tmp_upload_dir=dependencies.state.TMP_UPLOAD_DIR, upload_dir_rel=dependencies.state.UPLOAD_DIR_REL,
        max_pdf_pages=dependencies.state.MAX_PDF_TASK_PAGES,
        inspect_pdf=dependencies.inspect_and_extract_pdf, ocr_page=dependencies.ocr_pdf_page_image,
        parse_text=dependencies.parse_paper_text_internal,
        postprocess=dependencies.post_process_pdf_parsed_questions,
        delete_temp_assets=dependencies._delete_task_temp_assets,
        extract_docx=dependencies.extract_docx_markdown, reconcile_math=dependencies.reconcile_visible_math,
    )


def manual_crop_pdf(payload: dict, *, dependencies: DocumentTaskServiceDependencies):
    """用户在前端手动拖拽框选后，后端根据坐标裁剪 PDF 页面的特定区域"""
    try:
        import math

        if not isinstance(payload, dict):
            raise ValueError("裁剪参数格式不正确。")
        try:
            task_id = str(dependencies.uuid.UUID(str(payload.get("task_id", ""))))
        except (ValueError, AttributeError) as exc:
            raise ValueError("任务 ID 格式不正确。") from exc
        task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
        if not task or task.get("document_type") != "pdf":
            return dependencies.JSONResponse(
                content={"status": "error", "message": "未找到对应的 PDF 任务！"},
                status_code=404,
            )
        if task.get("status") in {"cancelled", "error"}:
            raise ValueError("已取消或失败的 PDF 任务不能再裁剪。")
        page_index = int(payload.get("page_index", 0))
        selected_numbers = task.get("page_numbers")
        if page_index < 0 or (
            isinstance(selected_numbers, list) and page_index + 1 not in selected_numbers
        ) or (selected_numbers is None and page_index >= dependencies.state.MAX_PDF_TASK_PAGES):
            raise ValueError("页码越界。")
        ymin = float(payload.get("ymin", 0))
        xmin = float(payload.get("xmin", 0))
        ymax = float(payload.get("ymax", 0))
        xmax = float(payload.get("xmax", 0))
        coordinates = (ymin, xmin, ymax, xmax)
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("裁剪坐标必须是有限数值。")
        if not (
            0 <= ymin < ymax <= 100
            and 0 <= xmin < xmax <= 100
        ):
            raise ValueError("裁剪坐标必须位于 0–100，且框选区域不能为空。")

        img_filename = f"pdf_page_{task_id}_{page_index}.png"
        img_filepath = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR) / img_filename

        if not img_filepath.is_file() or img_filepath.is_symlink():
            return dependencies.JSONResponse(
                content={"status": "error", "message": "未找到对应的 PDF 页面图片！"},
                status_code=404
            )

        with dependencies.Image.open(img_filepath) as img:
            img.load()
            w, h = img.size

            # Convert percentage to pixels.
            left = max(0, min((xmin / 100.0) * w, w - 1))
            top = max(0, min((ymin / 100.0) * h, h - 1))
            right = max(left + 1, min((xmax / 100.0) * w, w))
            bottom = max(top + 1, min((ymax / 100.0) * h, h))
            cropped = img.crop((left, top, right, bottom))

        crop_filename = f"pdf_crop_{task_id}_{dependencies.uuid.uuid4().hex[:12]}.png"
        crop_filepath = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR) / crop_filename
        cropped.save(crop_filepath, format="PNG")

        img_url = f"/{dependencies.state.UPLOAD_DIR_REL}/tmp/{crop_filename}"
        if not dependencies.state.DOCUMENT_TASKS.add_temp_asset(task_id, img_url):
            crop_filepath.unlink(missing_ok=True)
            raise ValueError("任务记录已过期，无法登记裁剪图片。")
        return {"status": "success", "image_path": img_url}
    except ValueError as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"手动裁剪失败: {str(e)}"},
            status_code=400,
        )
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"手动裁剪失败: {str(e)}"},
            status_code=500
        )


def post_process_pdf_parsed_questions(parsed_questions: list, paper_title: str, task_id: str=None, ocr_results: list=None, *, dependencies: DocumentTaskServiceDependencies) -> list:
    """Compatibility entry point; the result processor owns the implementation."""
    return dependencies.post_process_questions(
        parsed_questions, paper_title, task_id, ocr_results,
        tmp_upload_dir=dependencies.state.TMP_UPLOAD_DIR, upload_dir_rel=dependencies.state.UPLOAD_DIR_REL,
        normalize_fillin=dependencies.normalize_fillin_macro,
        find_source_page=dependencies.find_source_page_by_overlap,
    )


def run_pdf_parsing_task(task_id: str, file_bytes: bytes, filename: str, generate_answers: bool=False, page_range: str=None, pdf_strategy: str='native_preferred', pdf_verify_suspicions: bool=False, *, dependencies: DocumentTaskServiceDependencies):

    """Keep the historical callable while delegating to the import service."""
    return dependencies.pdf_import_service.run_pdf_parsing_task(
        task_id, file_bytes, filename, generate_answers, page_range,
        pdf_strategy, pdf_verify_suspicions,
        dependencies=dependencies.build_document_import_dependencies(),
    )


def upload_pdf_task(file: UploadFile=File(...), generate_answers: str=Form('false'), page_range: Optional[str]=Form(None), pdf_strategy: str=Form('native_preferred'), pdf_verify_suspicions: bool=Form(False), *, dependencies: DocumentTaskServiceDependencies):
    try:
        if pdf_strategy not in dependencies.PDF_STRATEGIES:
            return dependencies.JSONResponse(content={"status": "error", "message": "不支持的 PDF 解析策略。"}, status_code=400)
        generate_answers_bool = generate_answers.lower() in ("true", "1", "yes")

        # 验证文件扩展名
        filename = file.filename or ""
        if not filename.lower().endswith(".pdf"):
            return dependencies.JSONResponse(
                content={"status": "error", "message": "上传文件格式不正确，必须为 .pdf 格式！"},
                status_code=400
            )

        # Incremental cap avoids loading an arbitrarily large multipart file.
        try:
            content = dependencies.read_stream_limited(file.file, dependencies.MAX_PDF_BYTES)
        except dependencies.UploadTooLargeError:
            return dependencies.JSONResponse(
                content={"status": "error", "message": "PDF 文件过大，请上传 30MB 以内的试卷文件！"},
                status_code=413
            )
        if not content.lstrip().startswith(b"%PDF-"):
            return dependencies.JSONResponse(
                content={"status": "error", "message": "文件内容不是有效的 PDF 文档！"},
                status_code=400,
            )

        task_id = str(dependencies.uuid.uuid4())

        dependencies.state.DOCUMENT_TASKS.create(
            task_id,
            status="pending",
            log="任务已排队，正在准备运行异步切片分析...",
            document_type="pdf",
            temp_assets=[],
        )
        try:
            dependencies.state.DOCUMENT_TASKS.submit(
                task_id,
                dependencies.run_pdf_parsing_task,
                task_id,
                content,
                filename,
                generate_answers_bool,
                page_range,
                pdf_strategy,
                bool(pdf_verify_suspicions) if pdf_strategy == "layout_aware" else False,
            )
        except dependencies.TaskQueueFull as exc:
            dependencies.state.DOCUMENT_TASKS.remove(task_id)
            return dependencies.JSONResponse(
                content={"status": "error", "message": str(exc)},
                status_code=429,
            )

        return {
            "status": "success",
            "task_id": task_id
        }
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"创建 PDF 解析任务失败: {str(e)}"},
            status_code=500
        )


def run_docx_parsing_task(task_id: str, file_bytes: bytes, filename: str, generate_answers: bool=False, docx_verify_suspicions: bool=False, *, dependencies: DocumentTaskServiceDependencies):

    """Keep the historical callable while delegating to the import service."""
    return dependencies.docx_import_service.run_docx_parsing_task(
        task_id, file_bytes, filename, generate_answers, docx_verify_suspicions,
        dependencies=dependencies.build_document_import_dependencies(),
    )


def upload_docx_task(file: UploadFile=File(...), generate_answers: str=Form('false'), docx_verify_suspicions: str=Form('false'), *, dependencies: DocumentTaskServiceDependencies):
    try:
        generate_answers_bool = generate_answers.lower() in ("true", "1", "yes")

        # 验证文件扩展名
        filename = file.filename or ""
        if not filename.lower().endswith(".docx"):
            return dependencies.JSONResponse(
                content={"status": "error", "message": "上传文件格式不正确，必须为 .docx 格式！"},
                status_code=400
            )

        try:
            content = dependencies.read_stream_limited(file.file, dependencies.MAX_PDF_BYTES)
        except dependencies.UploadTooLargeError:
            return dependencies.JSONResponse(
                content={"status": "error", "message": "Word 文件过大，请上传 30MB 以内的试卷文件！"},
                status_code=413
            )
        if len(content) < 4 or content[:4] != b"PK\x03\x04":
            return dependencies.JSONResponse(
                content={"status": "error", "message": "文件内容不是有效的 Word DOCX 压缩包！"},
                status_code=400,
            )

        task_id = str(dependencies.uuid.uuid4())

        dependencies.state.DOCUMENT_TASKS.create(
            task_id,
            status="pending",
            log="Word 任务已排队，正在准备安全提取公式与配图...",
            document_type="docx",
            temp_assets=[],
        )
        try:
            dependencies.state.DOCUMENT_TASKS.submit(
                task_id,
                dependencies.run_docx_parsing_task,
                task_id,
                content,
                filename,
                generate_answers_bool,
                docx_verify_suspicions.lower() in ("true", "1", "yes"),
            )
        except dependencies.TaskQueueFull as exc:
            dependencies.state.DOCUMENT_TASKS.remove(task_id)
            return dependencies.JSONResponse(
                content={"status": "error", "message": str(exc)},
                status_code=429,
            )

        return {
            "status": "success",
            "task_id": task_id
        }
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"创建 Word 解析任务失败: {str(e)}"},
            status_code=500
        )


def get_pdf_task_status(task_id: str, *, dependencies: DocumentTaskServiceDependencies):
    task = dependencies.state.DOCUMENT_TASKS.snapshot(task_id)
    if not task:
        return dependencies.JSONResponse(
            content={"status": "error", "message": "未找到对应的任务 ID！"},
            status_code=404
        )
    return task


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
