"""Ordered image pages reuse the existing bounded PDF import task."""

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, List

from fastapi import File, Form, UploadFile, HTTPException
import pymupdf
from PIL import Image
from mathbank.application_state import RuntimeState

from mathbank.asset_security import (
    MAX_PDF_BYTES, MAX_SINGLE_IMAGE_BYTES, UploadTooLargeError,
    normalize_raster_image, read_stream_limited,
)


@dataclass(frozen=True)
class ImageImportServiceDependencies:
    state: RuntimeState
    upload_pdf_task: Callable
    JSONResponse: Any


def image_pages_to_pdf(files: List[UploadFile], *, max_batch_bytes=50 * 1024 * 1024) -> bytes:
    """Keep multipart order, original pixels and EXIF orientation; no AI or disk IO."""
    if not files or len(files) > 20:
        raise ValueError("请选择 1 至 20 张题目图片。")
    total = 0
    with pymupdf.open() as document:
        for index, uploaded in enumerate(files, 1):
            try:
                raw = read_stream_limited(uploaded.file, MAX_SINGLE_IMAGE_BYTES)
                total += len(raw)
                if total > max_batch_bytes:
                    raise UploadTooLargeError("图片总大小不能超过 50MB。")
                image = normalize_raster_image(raw)
            except UploadTooLargeError as exc:
                raise UploadTooLargeError(f"第 {index} 张图片超出大小限制（单张 10MB，总计 50MB）。") from exc
            except ValueError as exc:
                raise ValueError(f"第 {index} 张图片无法读取：{exc}") from exc
            # 150 DPI assigns page coordinates only; insert_image does not resize
            # the pixels. Bound PDF coordinates for exceptionally tall screenshots.
            with Image.open(BytesIO(image.data)) as decoded:
                width, height = decoded.size
            scale = min(72 / 150, 14400 / max(width, height))
            page = document.new_page(width=max(1, width * scale), height=max(1, height * scale))
            page.insert_image(page.rect, stream=image.data)
        # Re-uploading the same ordered pages with the same request id must
        # reuse its task, not conflict because of a random PDF trailer id.
        result = document.tobytes(garbage=3, deflate=True, no_new_id=True)
    if len(result) > MAX_PDF_BYTES:
        raise UploadTooLargeError("图片生成的试卷超过 30MB，请减少图片后分批导入。")
    return result


def upload_image_task(
    files: List[UploadFile] = File(...),
    generate_answers: str = Form("false"),
    paper_title: str = Form(""),
    client_request_id: str = Form(""),
    *, dependencies: ImageImportServiceDependencies,
):
    """Local conversion precedes the same queue, cancellation, OCR and review flow."""
    try:
        content = image_pages_to_pdf(files)
    except (ValueError, OSError, pymupdf.FileDataError) as exc:
        return dependencies.JSONResponse(
            content={"status": "error", "message": str(exc)},
            status_code=413 if isinstance(exc, UploadTooLargeError) else 400,
        )
    with BytesIO(content) as buffer:
        title = paper_title.replace("\r", " ").replace("\n", " ").strip()[:180] or "图片试卷"
        try:
            return dependencies.upload_pdf_task(
                file=UploadFile(filename=title + ".pdf", file=buffer),
                generate_answers=generate_answers, page_range=None,
                pdf_strategy="layout_aware", pdf_verify_suspicions=False,
                client_request_id=client_request_id if isinstance(client_request_id, str) else "",
                paper_title=title,
            )
        except HTTPException as exc:
            # Keep the image endpoint's existing error envelope while the
            # shared document handler now raises typed HTTP errors.
            return dependencies.JSONResponse(status_code=exc.status_code,
                content={"status": "error", "message": exc.detail, "detail": exc.detail},
                headers=exc.headers)
