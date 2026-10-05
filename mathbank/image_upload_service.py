"""Image upload service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from typing import List
from fastapi import UploadFile, File


@dataclass(frozen=True)
class ImageUploadServiceDependencies:
    state: RuntimeState
    Image: Any
    InvalidImageError: Any
    JSONResponse: Any
    MAX_SINGLE_IMAGE_BYTES: Any
    MAX_TEX_BYTES: Any
    UploadTooLargeError: Any
    decode_and_prepare_tex: Any
    normalize_raster_image: Any
    os: Any
    read_stream_limited: Any
    tex_asset_basename: Any
    uuid: Any


def upload_image(file: UploadFile=File(...), *, dependencies: ImageUploadServiceDependencies):
    try:
        raw = dependencies.read_stream_limited(file.file, dependencies.MAX_SINGLE_IMAGE_BYTES)
        normalized = dependencies.normalize_raster_image(raw)

        # Never trust the client suffix.  The server-generated extension and
        # re-encoded bytes prevent HTML/SVG/polyglot files being served same-origin.
        filename = f"{dependencies.uuid.uuid4().hex}{normalized.extension}"
        filepath = dependencies.os.path.join(dependencies.state.UPLOAD_DIR, filename)

        with open(filepath, "wb") as f:
            f.write(normalized.data)

        relative_path = f"/{dependencies.state.UPLOAD_DIR_REL}/{filename}"
        return {
            "status": "success",
            "file_path": relative_path,
            "filename": file.filename
        }
    except dependencies.UploadTooLargeError:
        return dependencies.JSONResponse(
            content={"status": "error", "message": "图片过大，请上传 10MB 以内的文件。"},
            status_code=413,
        )
    except dependencies.InvalidImageError as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"图片上传失败: {str(e)}"},
            status_code=400,
        )
    except Exception as e:
        print(f"[Upload Error] {type(e).__name__}: {e}")
        return dependencies.JSONResponse(
            content={"status": "error", "message": "文件上传失败，请检查文件后重试。"},
            status_code=500
        )


def auto_crop_image(image, *, dependencies: ImageUploadServiceDependencies):
    try:
        from PIL import ImageOps, ImageStat
        # 估算灰度均值，判断主色调（暗色背景还是亮色背景）
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        mean_val = stat.mean[0]

        if mean_val < 100:  # 偏暗，可能含有大面积黑边背景
            bbox = image.getbbox()
            if bbox:
                # 留出 8 像素的边距以防文字贴边影响识别
                w, h = image.size
                left = max(0, bbox[0] - 8)
                upper = max(0, bbox[1] - 8)
                right = min(w, bbox[2] + 8)
                lower = min(h, bbox[3] + 8)
                return image.crop((left, upper, right, lower))
        elif mean_val > 220:  # 偏亮，可能含有大面积白边背景
            inverted = ImageOps.invert(image.convert("RGB"))
            bbox = inverted.getbbox()
            if bbox:
                w, h = image.size
                left = max(0, bbox[0] - 8)
                upper = max(0, bbox[1] - 8)
                right = min(w, bbox[2] + 8)
                lower = min(h, bbox[3] + 8)
                return image.crop((left, upper, right, lower))
    except Exception as e:
        print(f"[Auto Crop] 裁剪失败，返回原图. Error: {str(e)}")
    return image


def upload_tex_source(file: UploadFile=File(...), *, dependencies: ImageUploadServiceDependencies):
    """Decode and inspect a single TeX source file without executing it."""
    filename = file.filename or ""
    if not filename.lower().endswith(".tex"):
        return dependencies.JSONResponse(
            content={"status": "error", "message": "上传文件格式不正确，必须为 .tex 格式！"},
            status_code=400,
        )
    try:
        content = dependencies.read_stream_limited(file.file, dependencies.MAX_TEX_BYTES)
        result = dependencies.decode_and_prepare_tex(content)
        return {
            "status": "success",
            "source": result["source"],
            "title": result["title"],
            "diagnostics": result["diagnostics"],
        }
    except dependencies.UploadTooLargeError:
        return dependencies.JSONResponse(
            content={"status": "error", "message": "TeX 文件过大，请上传 5MB 以内的单文件试卷源码！"},
            status_code=413,
        )
    except ValueError as exc:
        return dependencies.JSONResponse(content={"status": "error", "message": str(exc)}, status_code=400)


def upload_batch_images(files: List[UploadFile]=File(...), *, dependencies: ImageUploadServiceDependencies):
    try:
        if not files or len(files) > 20:
            return dependencies.JSONResponse(
                content={"status": "error", "message": "配图数量必须为 1 至 20 张。"},
                status_code=400,
            )
        validated = []
        total_bytes = 0
        seen_names: set[str] = set()
        for file in files:
            original_name = dependencies.tex_asset_basename(file.filename or "image") or "image"
            normalized_name = original_name.casefold()
            if normalized_name in seen_names:
                raise ValueError(f"存在重名配图 {original_name}，请保留一张或先重命名。")
            seen_names.add(normalized_name)
            try:
                raw = dependencies.read_stream_limited(file.file, dependencies.MAX_SINGLE_IMAGE_BYTES)
            except dependencies.UploadTooLargeError as exc:
                raise ValueError(f"图片 {original_name} 超过 10MB。") from exc
            total_bytes += len(raw)
            if total_bytes > 50 * 1024 * 1024:
                raise ValueError("配图总大小不能超过 50MB。")
            try:
                normalized = dependencies.normalize_raster_image(raw)
            except dependencies.InvalidImageError as exc:
                raise ValueError(f"图片 {original_name} 不是安全的栅格图片。") from exc
            validated.append((original_name, normalized))

        mapping = {}
        for original_name, normalized in validated:
            filename = f"{dependencies.uuid.uuid4().hex}{normalized.extension}"
            filepath = dependencies.os.path.join(dependencies.state.UPLOAD_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(normalized.data)
            relative_path = f"/{dependencies.state.UPLOAD_DIR_REL}/{filename}"
            mapping[original_name] = relative_path

        return {
            "status": "success",
            "mapping": mapping
        }
    except (ValueError, OSError, dependencies.Image.DecompressionBombError) as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"批量图片上传失败: {str(e)}"},
            status_code=400
        )
