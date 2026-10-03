"""PDF import orchestration with explicit dependencies and bounded paid calls."""

import os
import re
import tempfile
from pathlib import Path

from mathbank.document_import_context import DocumentImportDependencies
from mathbank.document_text import parse_page_range, process_ocr_illustrations, extract_title_from_latex
from mathbank.task_manager import TaskCancelled
from mathbank.ai_providers import OCRConfigurationError, OCRResponseTimeoutError, ParseConfigurationError
from mathbank.pdf_figures import PDF_STRATEGIES, apply_pdf_layout_reviews, enrich_pdf_with_figures, isolate_shared_pdf_figures
from mathbank.pdf_layout import inspect_pdf_page
from mathbank.pdf_inspector_helper import merge_pdf_page_texts
from mathbank.content_locks import lock_visible_math
from mathbank.paper_parse import finalize_source_answers
from mathbank.import_review import make_source_review_advisory


def run_pdf_parsing_task(
    task_id: str,
    file_bytes: bytes,
    filename: str,
    generate_answers: bool = False,
    page_range: str = None,
    pdf_strategy: str = "native_preferred",
    pdf_verify_suspicions: bool = False,
    *, dependencies: DocumentImportDependencies,
):
    """PDF parsing with bounded OCR concurrency and cooperative cancellation."""

    import concurrent.futures

    temp_assets: list[str] = []
    tmp_pdf_path = Path(dependencies.tmp_upload_dir) / f"{task_id}.pdf"
    diagnostics: dict = {}
    layout_result = None

    try:
        import pymupdf as fitz
    except ImportError:
        dependencies.tasks.fail(
            task_id,
            "本地 Python 环境未安装 PyMuPDF，请通过 pip install pymupdf 安装依赖！",
            document_type="pdf",
        )
        return

    try:
        dependencies.tasks.check_cancelled(task_id)
        if pdf_strategy not in PDF_STRATEGIES:
            raise ValueError("不支持的 PDF 解析策略。")
        tmp_pdf_path.write_bytes(file_bytes)
        dependencies.tasks.update(
            task_id,
            status="processing_images",
            progress=10,
            log="已接收文件，正在渲染 PDF 高清页面...",
            document_type="pdf",
            temp_assets=[],
        )

        page_images: list[str] = []
        page_urls: list[str] = []
        page_layout_infos: dict[int, dict] = {}
        joint_page_results: dict[int, dict] = {}
        with fitz.open(tmp_pdf_path) as document:
            total_pages = len(document)
            if total_pages == 0:
                raise ValueError("此 PDF 没有有效页面，或者格式已损坏！")
            target_page_indices = parse_page_range(page_range, total_pages)
            if len(target_page_indices) > dependencies.max_pdf_pages:
                raise ValueError(
                    f"单次最多解析 {dependencies.max_pdf_pages} 页，请填写较小的页码范围。"
                )

            for page_num in target_page_indices:
                dependencies.tasks.check_cancelled(task_id)
                page = document.load_page(page_num)
                if pdf_strategy == "layout_aware":
                    page_layout_infos[page_num] = inspect_pdf_page(page, page_num)
                estimated_pixels = int(
                    (page.rect.width / 72 * 150) * (page.rect.height / 72 * 150)
                )
                if estimated_pixels > 30_000_000:
                    raise ValueError(f"第 {page_num + 1} 页尺寸异常，已停止高清渲染。")
                pixmap = page.get_pixmap(dpi=150)
                image_filename = f"pdf_page_{task_id}_{page_num}.png"
                image_path = Path(dependencies.tmp_upload_dir) / image_filename
                pixmap.save(image_path)
                image_url = f"/{dependencies.upload_dir_rel}/tmp/{image_filename}"
                page_images.append(str(image_path))
                page_urls.append(image_url)
                temp_assets.append(image_url)
                dependencies.tasks.update(
                    task_id,
                    page_images=list(page_urls),
                    page_numbers=[number + 1 for number in target_page_indices[:len(page_urls)]],
                    temp_assets=list(temp_assets),
                )

        tmp_pdf_path.unlink(missing_ok=True)
        dependencies.tasks.check_cancelled(task_id)
        total_target_pages = len(target_page_indices)

        if pdf_strategy == "force_ocr":
            inspector_result = {"pages": [], "pdf_type": "scanned"}
            inspector_pages = {}
        else:
            inspector_result = dependencies.inspect_pdf(
                file_bytes,
                task_id,
                page_indices=target_page_indices,
            )
            inspector_pages = {
                int(page.get("page_index")): page
                for page in inspector_result.get("pages", [])
                if page.get("page_index") is not None
            }
            diagnostics["pdf_native_quality"] = [
                {"page_number": index + 1, "reasons": page["quality_reasons"]}
                for index, page in inspector_pages.items() if page.get("quality_reasons")
            ]
            diagnostics["pdf_native_repair"] = [
                {"page_number": index + 1, **page["native_repair"]}
                for index, page in inspector_pages.items() if page.get("native_repair")
            ]
        dependencies.tasks.check_cancelled(task_id)

        ocr_results = [None] * total_target_pages
        pages_requiring_ocr = []
        native_page_count = 0
        for local_idx, page_num in enumerate(target_page_indices):
            page_info = inspector_pages.get(page_num)
            native_text = str((page_info or {}).get("markdown") or "").strip()
            if page_info and not page_info.get("needs_ocr") and native_text:
                ocr_results[local_idx] = (
                    f"<!-- MATHBANK_PDF_PAGE:{page_num + 1} -->\n{native_text}"
                )
                native_page_count += 1
            else:
                pages_requiring_ocr.append(local_idx)

        # Work from physical PDF rows, never from a scrambled Markdown table.
        # Planning is local and conservative; only a validated plan changes the
        # paid request. A failed paid regional request is never retried as a page.
        regional_plans: dict[int, dict] = {}
        if pdf_strategy != "force_ocr" and pages_requiring_ocr:
            from mathbank.pdf_native_regions import plan_pdf_regions
            with fitz.open(stream=file_bytes, filetype="pdf") as document:
                for local_idx in pages_requiring_ocr:
                    dependencies.tasks.check_cancelled(task_id)
                    page_num = target_page_indices[local_idx]
                    info = page_layout_infos.get(page_num)
                    if info is None:
                        info = inspect_pdf_page(document[page_num], page_num)
                        page_layout_infos[page_num] = info
                    plan = plan_pdf_regions(document[page_num], info)
                    if plan is not None:
                        regional_plans[local_idx] = plan
        extraction_pages = []
        for local_idx, page_num in enumerate(target_page_indices):
            plan = regional_plans.get(local_idx)
            extraction_pages.append({
                "page_number": page_num + 1,
                "mode": ("regional" if plan else "full_vision") if local_idx in pages_requiring_ocr else "native",
                "structure_repaired": inspector_pages.get(page_num, {}).get("native_repair", {}).get("status") == "repaired",
                "native_characters": plan["native_characters"] if plan else 0,
                "region_count": len(plan["regions"]) if plan else 0,
                "image_area_ratio": plan["area_ratio"] if plan else (1 if local_idx in pages_requiring_ocr else 0),
            })
        diagnostics["pdf_extraction"] = {
            "native_pages": native_page_count,
            "repaired_pages": sum(
                inspector_pages.get(page_num, {}).get("native_repair", {}).get("status") == "repaired"
                and not inspector_pages.get(page_num, {}).get("needs_ocr")
                for page_num in target_page_indices
            ),
            "regional_pages": len(regional_plans),
            "full_vision_pages": len(pages_requiring_ocr) - len(regional_plans),
            "native_characters_reused": sum(plan["native_characters"] for plan in regional_plans.values()),
            "pages": extraction_pages,
        }
        dependencies.tasks.update(task_id, diagnostics=diagnostics)

        if native_page_count:
            print(
                f"[PDF Inspector Flow] 原生直提 {native_page_count} 页，"
                f"视觉 OCR {len(pages_requiring_ocr)} 页 "
                f"(Type: {inspector_result.get('pdf_type')})",
                flush=True,
            )

        if not pages_requiring_ocr:
            dependencies.tasks.update(
                task_id,
                status="ai_splitting",
                progress=60,
                log=(
                    f"pdf-inspector 已按所选范围可靠提取 {native_page_count} 页原生文本，"
                    "正在连续拆题..."
                ),
                page_images=list(page_urls),
                temp_assets=list(temp_assets),
            )
        else:
            if pdf_strategy == "force_ocr":
                extraction_log = f"按所选全页识图模式，正在识别 {total_target_pages} 页文字与公式..."
            elif regional_plans:
                extraction_log = (
                    f"所选 {total_target_pages} 页：原生直提 {native_page_count} 页，"
                    f"局部识别 {len(regional_plans)} 页，"
                    f"整页识别 {len(pages_requiring_ocr) - len(regional_plans)} 页；"
                    "局部页保留可靠原文，仅发送需要补全的区域..."
                )
            elif native_page_count == 0:
                extraction_log = (
                    f"已尝试原生提取，所选 {total_target_pages} 页的文字或公式未通过质量检查，"
                    "改用逐页视觉识别..."
                )
            else:
                extraction_log = (
                    f"所选 {total_target_pages} 页中，{native_page_count} 页采用原生文字，"
                    f"其余 {len(pages_requiring_ocr)} 页因提取质量问题改用视觉识别..."
                )
            dependencies.tasks.update(
                task_id,
                status="ocr_extraction",
                progress=30,
                log=extraction_log,
                page_images=list(page_urls),
                temp_assets=list(temp_assets),
            )

            def ocr_worker(local_idx, image_path):
                acquired = False
                try:
                    while not acquired:
                        dependencies.tasks.check_cancelled(task_id)
                        acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                    dependencies.tasks.check_cancelled(task_id)
                    real_page_num = target_page_indices[local_idx] + 1
                    joint = None
                    if local_idx in regional_plans:
                        from mathbank.pdf_region_vision import request_pdf_regions
                        joint = request_pdf_regions(
                            image_path, page_layout_infos[real_page_num - 1], regional_plans[local_idx],
                            include_figures=pdf_strategy == "layout_aware",
                            check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id),
                        )
                        raw_text = joint["markdown"]
                    elif pdf_strategy == "layout_aware":
                        from mathbank.pdf_page_vision import (
                            choose_pdf_page_vision_dpi, request_pdf_page,
                            DEFAULT_PAGE_VISION_DPI,
                        )
                        render_dpi = choose_pdf_page_vision_dpi(
                            inspector_pages.get(real_page_num - 1)
                        )
                        if render_dpi == DEFAULT_PAGE_VISION_DPI:
                            joint = request_pdf_page(
                                image_path, page_layout_infos[real_page_num - 1],
                                check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id),
                            )
                        else:
                            # Re-render from vectors instead of resampling the
                            # 150-DPI preview. The compact image is request-only.
                            with tempfile.TemporaryDirectory(prefix="physicsbank-vision-") as temp_dir:
                                compact_path = Path(temp_dir) / "page.png"
                                with fitz.open(stream=file_bytes, filetype="pdf") as source_pdf:
                                    source_pdf[real_page_num - 1].get_pixmap(
                                        dpi=render_dpi, alpha=False,
                                    ).save(compact_path)
                                dependencies.tasks.check_cancelled(task_id)
                                joint = request_pdf_page(
                                    str(compact_path), page_layout_infos[real_page_num - 1],
                                    check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id),
                                )
                        raw_text = joint["markdown"]
                    else:
                        raw_text = dependencies.ocr_page(image_path)
                    print(
                        f"[PDF OCR] 第 {real_page_num} 页识别完成 "
                        f"(characters={len(raw_text)})."
                    )
                    return local_idx, raw_text, None, joint
                except TaskCancelled:
                    raise
                except Exception as ocr_error:
                    return local_idx, "", ocr_error, None
                finally:
                    if acquired:
                        dependencies.ocr_semaphore.release()

            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=min(len(pages_requiring_ocr), 4),
                thread_name_prefix="mathbank-pdf-ocr",
            )
            futures = []
            try:
                for local_idx in pages_requiring_ocr:
                    dependencies.tasks.check_cancelled(task_id)
                    futures.append(
                        executor.submit(ocr_worker, local_idx, page_images[local_idx])
                    )

                completed = 0
                for future in concurrent.futures.as_completed(futures):
                    dependencies.tasks.check_cancelled(task_id)
                    local_idx, text, error, joint = future.result()
                    if error:
                        real_page_num = target_page_indices[local_idx] + 1
                        if isinstance(error, OCRConfigurationError):
                            raise OCRConfigurationError(f"第 {real_page_num} 页需要识图：{error}") from error
                        if isinstance(error, OCRResponseTimeoutError):
                            raise OCRResponseTimeoutError(f"第 {real_page_num} 页识图超时：{error}") from error
                        raise RuntimeError(f"解析第 {real_page_num} 页出错: {error}")
                    processed_text = process_ocr_illustrations(text)
                    real_page_num = target_page_indices[local_idx] + 1
                    if joint is not None:
                        joint_page_results[real_page_num - 1] = joint
                    ocr_results[local_idx] = (
                        f"<!-- MATHBANK_PDF_PAGE:{real_page_num} -->\n"
                        f"{processed_text.strip()}"
                    )
                    completed += 1
                    progress = 30 + int(
                        (completed / len(pages_requiring_ocr)) * 40
                    )
                    dependencies.tasks.update(
                        task_id,
                        progress=progress,
                        log=(
                            f"视觉转译进度: {completed} / "
                            f"{len(pages_requiring_ocr)} 页已完成..." +
                            (f"（局部识别 {len(regional_plans)} 页）" if regional_plans else "")
                        ),
                    )
            finally:
                cancelled = dependencies.tasks.is_cancelled(task_id)
                if cancelled:
                    for future in futures:
                        future.cancel()
                executor.shutdown(wait=not cancelled, cancel_futures=True)

        regional_results = [joint_page_results[target_page_indices[index]] for index in regional_plans]
        if regional_results:
            diagnostics["pdf_regional_usage"] = {
                key: sum(item["usage"][key] for item in regional_results)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if all(key in item.get("usage", {}) for item in regional_results)
            }
        dependencies.tasks.check_cancelled(task_id)
        if pdf_strategy == "layout_aware":
            def check_layout_cancelled():
                dependencies.tasks.check_cancelled(task_id)
                if not dependencies.tasks.exists(task_id):
                    raise TaskCancelled("PDF 任务已移除。")

            def register_figure_asset(path):
                temp_assets.append(path)
                if not dependencies.tasks.add_temp_asset(task_id, path):
                    raise TaskCancelled("PDF 任务已移除。")
                check_layout_cancelled()

            def report_layout_progress(local_index, message):
                check_layout_cancelled()
                dependencies.tasks.update(
                    task_id, status="layout_analysis",
                    progress=72 + int(7 * local_index / max(1, total_target_pages)),
                    log=message,
                )

            # Share the existing process-wide paid vision concurrency bound.
            acquired = False
            try:
                while not acquired:
                    check_layout_cancelled()
                    acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                layout_result = enrich_pdf_with_figures(
                    file_bytes, target_page_indices, page_images, page_urls,
                    ocr_results, {target_page_indices[index] for index in pages_requiring_ocr},
                    output_dir=Path(dependencies.tmp_upload_dir), url_prefix=f"/{dependencies.upload_dir_rel}/tmp",
                    task_id=task_id, check_cancelled=check_layout_cancelled,
                    register_asset=register_figure_asset, report_progress=report_layout_progress,
                    precomputed_layouts={index: item["layout"] for index, item in joint_page_results.items()},
                )
            finally:
                if acquired:
                    dependencies.ocr_semaphore.release()
            ocr_results = layout_result["page_texts"]
            diagnostics["pdf_layout"] = layout_result["diagnostics"]
            diagnostics["pdf_layout"]["regional_visual_calls"] = len(regional_results)
            diagnostics["pdf_joint_usage"] = {
                key: sum(item["usage"][key] for item in joint_page_results.values())
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if joint_page_results and all(key in item.get("usage", {}) for item in joint_page_results.values())
            }
            dependencies.tasks.update(task_id, pdf_layout={
                "schema": layout_result["schema"], "pages": layout_result["pages"],
            }, diagnostics=diagnostics)
        # Retain the exact first-pass transcription used for splitting. Later
        # source review can check its ranges without re-running page recognition.
        # Keep complete pages or no page cache; never certify truncated evidence.
        source_pages = None
        if sum(len(str(text or "")) for text in ocr_results) <= 500_000:
            source_pages = []
            for local_idx, page_num in enumerate(target_page_indices):
                page = next((item for item in (layout_result or {}).get("pages", [])
                             if item["page_index"] == page_num), {})
                origin = ("regional_vision" if local_idx in regional_plans else
                          "joint_vision" if page_num in joint_page_results else
                          "ocr" if local_idx in pages_requiring_ocr else
                          "native_repaired" if inspector_pages.get(page_num, {}).get("native_repair", {}).get("status") == "repaired"
                          else "native")
                source_pages.append({"page_number": page_num + 1, "origin": origin,
                                     "markdown": str(ocr_results[local_idx] or ""),
                                     "figures": page.get("figures", [])})
            dependencies.tasks.update(task_id, pdf_source_pages=source_pages)
        full_latex_content = merge_pdf_page_texts(ocr_results)
        if not full_latex_content.strip():
            raise ValueError("所选 PDF 页面未能提取出可解析的文字内容。")

        dependencies.tasks.update(
            task_id,
            status="ai_splitting",
            progress=80,
            log="文本与公式准备就绪！正在调用大模型拆解题目与标注属性...",
        )
        dependencies.tasks.check_cancelled(task_id)

        paper_title = os.path.splitext(filename)[0]
        auto_title = extract_title_from_latex(full_latex_content)
        if auto_title:
            paper_title = auto_title
        if layout_result is not None:
            # Page markers track provenance, never count as question text and
            # must not become an artificial break in a cross-page question.
            source_content = re.sub(r"<!-- MATHBANK_PDF_PAGE:\d+ -->", "", full_latex_content)
            locked_source, math_locks = lock_visible_math(source_content, task_id.replace("-", "")[:16])
            diagnostics["math_locks_created"] = len(math_locks)
            parsed_questions = dependencies.parse_text(
                locked_source, False, diagnostics=diagnostics, preserve_source_answers=True,
            )
            dependencies.tasks.check_cancelled(task_id)
            diagnostics.update(dependencies.reconcile_math(parsed_questions, math_locks, source_content))
            finalize_source_answers(parsed_questions, source_content)
            apply_pdf_layout_reviews(parsed_questions, layout_result, diagnostics)
            isolate_shared_pdf_figures(
                parsed_questions, layout_result, output_dir=Path(dependencies.tmp_upload_dir),
                url_prefix=f"/{dependencies.upload_dir_rel}/tmp", register_asset=register_figure_asset,
                check_cancelled=check_layout_cancelled,
            )
        else:
            parsed_questions = dependencies.parse_text(
                full_latex_content,
                False,  # Extract original answers only; the frontend solves missing answers.
                diagnostics=diagnostics,
            )
        dependencies.tasks.check_cancelled(task_id)
        final_questions = dependencies.postprocess(
            parsed_questions,
            paper_title,
            task_id,
            None if layout_result is not None else ocr_results,
        )
        if layout_result is not None:
            if pdf_verify_suspicions and diagnostics.get("source_review_count"):
                from mathbank.pdf_source_verify import verify_pdf_source_suspicions
                dependencies.tasks.update(
                    task_id, status="source_verification", progress=90,
                    log="正在对照原页核验剩余疑点，无法确定的题目仍保留人工核对...",
                    diagnostics=diagnostics,
                )
                acquired = False
                try:
                    while not acquired:
                        dependencies.tasks.check_cancelled(task_id)
                        acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                    diagnostics["pdf_source_verification"] = verify_pdf_source_suspicions(
                        final_questions, diagnostics, page_urls,
                        [number + 1 for number in target_page_indices],
                        source_pages=source_pages,
                        check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id),
                    )
                finally:
                    if acquired:
                        dependencies.ocr_semaphore.release()
            else:
                diagnostics["pdf_source_verification"] = {
                    "status": "no_candidates" if pdf_verify_suspicions else "disabled",
                    "calls": 0, "checked": 0, "confirmed": 0,
                    "pending": diagnostics.get("source_review_count", 0),
                    "skipped": 0, "usage": {},
                }
        make_source_review_advisory(final_questions, diagnostics)
        dependencies.tasks.check_cancelled(task_id)
        completed = dependencies.tasks.complete(
            task_id,
            log="拆分完成，可选择题目导入；原文和配图说明可按需展开查看。",
            data=final_questions,
            generate_answers=generate_answers,
            page_images=list(page_urls),
            page_numbers=[number + 1 for number in target_page_indices],
            temp_assets=list(temp_assets),
            document_type="pdf",
            diagnostics=diagnostics,
        )
        if not completed:
            dependencies.delete_temp_assets(temp_assets)
    except TaskCancelled:
        dependencies.delete_temp_assets(temp_assets)
    except Exception as ex:
        dependencies.delete_temp_assets(temp_assets)
        error_code = (
            "ocr_configuration_required" if isinstance(ex, OCRConfigurationError)
            else "parse_configuration_required" if isinstance(ex, ParseConfigurationError)
            else "ocr_response_timeout" if isinstance(ex, OCRResponseTimeoutError)
            else None
        )
        dependencies.tasks.fail(
            task_id,
            f"PDF 智能拆解解析失败: {str(ex)}",
            document_type="pdf",
            **({"error_code": error_code} if error_code else {}),
        )
    finally:
        tmp_pdf_path.unlink(missing_ok=True)
