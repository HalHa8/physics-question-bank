"""Document import orchestration with explicit task-scoped dependencies."""

from mathbank.document_import_context import DocumentImportDependencies
from mathbank.document_text import parse_page_range, process_ocr_illustrations, extract_title_from_latex, normalize_fillin_macro
from mathbank.content_locks import lock_visible_math, reconcile_visible_math
from mathbank.import_review import (
    make_source_review_advisory, prepare_word_extraction_reviews, finalize_word_extraction_reviews,
)
from mathbank.paper_parse import (
    PAPER_SPLIT_TIMEOUT_SECONDS, PAPER_SPLIT_CACHE_MAX_CHARACTERS,
    parse_paper_completion, finalize_source_answers, request_pdf_paper_completion,
)
from mathbank.source_metadata import prepare_word_source_metadata, source_metadata_diagnostics, normalize_source_fillin
from mathbank.source_metadata_request import request_word_source_metadata
from mathbank.task_manager import (
    TaskCancelled,
    TaskManager,
    TaskQueueFull,
)
from pathlib import Path
import copy
import hashlib
import json
import os


def run_docx_parsing_task(
    task_id: str,
    file_bytes: bytes,
    filename: str,
    generate_answers: bool = False,
    docx_verify_suspicions: bool = False, *, dependencies: DocumentImportDependencies):
    temp_assets = []
    diagnostics = {}
    try:
        dependencies.tasks.check_cancelled(task_id)
        dependencies.tasks.update(
            task_id,
            status="extracting_docx",
            progress=25,
            log="已接收 Word 试卷，正在安全提取 OMML 公式、文字与配图...",
            document_type="docx",
            temp_assets=[],
        )

        # 2. 安全提取 Word Markdown；资产先放入 tmp，入库时再晋升。
        docx_res = dependencies.extract_docx(
            file_bytes,
            output_dir=dependencies.tmp_upload_dir,
            url_prefix=f"/{dependencies.upload_dir_rel}/tmp",
            asset_prefix=f"word_{task_id}",
            include_source_asset_evidence=True,
            include_source_review_evidence=True,
        )
        temp_assets = docx_res.get("image_paths", [])
        if not docx_res.get("success") or not docx_res.get("markdown"):
            raise ValueError(docx_res.get("error") or "未能从 Word 文档中提取出有效试题内容！")

        full_markdown_content = docx_res["markdown"]
        img_count = docx_res.get("image_count", 0)
        diagnostics = docx_res.get("diagnostics", {})
        extraction_diagnostics = copy.deepcopy(diagnostics)
        extraction_review_evidence = docx_res.get("_source_review_evidence")
        source_document_sha256 = hashlib.sha256(file_bytes).hexdigest()
        diagnostics["word_extraction_warnings"] = list(diagnostics.get("warnings", []))
        converted_count = diagnostics.get("omml_converted", 0) + diagnostics.get("mtef_converted", 0)
        review_count = diagnostics.get("review_required", 0)
        extraction_log = (
            f"Word 提取完成：{converted_count} 个公式已转换，{img_count} 张图片已保留"
            + ((f"，{review_count} 处提取疑点将在拆题后自动核验。" if docx_verify_suspicions
                else f"，{review_count} 处提取疑点，自动核验已关闭。") if review_count else "。")
        )

        dependencies.tasks.check_cancelled(task_id)
        dependencies.tasks.update(
            task_id,
            status="ai_splitting",
            progress=70,
            log=extraction_log + " 正在调用教研模型拆题...",
            document_type="docx",
            diagnostics=diagnostics,
            temp_assets=list(temp_assets),
        )

        # 3. 智能提取标题与题目切片
        paper_title = os.path.splitext(filename)[0]
        auto_title = extract_title_from_latex(full_markdown_content)
        if auto_title:
            paper_title = auto_title

        # Keep every formula visible in-place for the model's mathematical
        # understanding, while assigning an immutable ID. The model returns
        # the ID and the server restores the exact Word-extracted source.
        locked_markdown_content, math_locks = lock_visible_math(
            full_markdown_content,
            task_id.replace("-", "")[:16],
        )
        diagnostics["math_locks_created"] = len(math_locks)
        dependencies.tasks.check_cancelled(task_id)
        from mathbank.word_hybrid_plan import build_word_hybrid_plan, word_hybrid_plan_diagnostics
        from mathbank.word_hybrid_request import request_word_hybrid
        hybrid_plan = None
        preserved_indices = frozenset()
        if docx_res.get("_source_review_evidence") is not None:
            hybrid_plan = build_word_hybrid_plan(full_markdown_content, diagnostics,
                task_id=task_id, generation=0, source_document_sha256=hashlib.sha256(file_bytes).hexdigest(),
                min_metadata_source_fraction=0.5,
                asset_evidence=docx_res.get("_source_asset_evidence"),
                source_review_evidence=docx_res.get("_source_review_evidence"))
            diagnostics["word_hybrid"] = word_hybrid_plan_diagnostics(hybrid_plan)
        # Keep verified independent source bodies local. A single metadata-only
        # request can avoid copying every formula/image/answer through the LLM.
        # Ambiguous or damaged source structure continues through full splitting.
        source_plan = None
        try:
            source_plan = prepare_word_source_metadata(full_markdown_content, diagnostics,
                asset_evidence=docx_res.get("_source_asset_evidence"))
            if hybrid_plan is not None:
                if hybrid_plan["mode"] == "whole_metadata":
                    source_plan = hybrid_plan["_whole_source_metadata_plan"]
                elif source_plan["eligible"]:
                    source_plan["eligible"] = False
                    source_plan["fallback_reasons"] = hybrid_plan["global_reasons"] or ["native_scope_not_whole_reliable"]
            diagnostics["word_source_metadata"] = source_metadata_diagnostics(source_plan)
        except Exception as exc:
            # The optimization must never block an otherwise usable import.
            diagnostics["word_source_metadata"] = {
                "status": "fallback", "eligible": False, "calls": 0,
                "error_type": type(exc).__name__,
            }
        parsed_questions = None
        if hybrid_plan is not None and hybrid_plan["mode"] == "hybrid":
            parse_model = os.getenv("PREFER_PARSE_MODEL") or os.getenv("DEEPSEEK_PARSE_MODEL", "deepseek-flash")
            result = request_word_hybrid(hybrid_plan, dependencies.get_curriculum(),
                provider=dependencies.resolve_provider(parse_model), post=dependencies.post, diagnostics=diagnostics,
                normalize_fillin=normalize_fillin_macro, task_id=task_id, generation=0,
                check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id),
                full_source_fallback=lambda: dependencies.parse_text(locked_markdown_content, False,
                    diagnostics=diagnostics, preserve_source_answers=True, connection_retry=False,
                    check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id)))
            parsed_questions = result.questions
            preserved_indices = result.preserved_indices
            diagnostics["word_hybrid"]["partial"] = result.partial
        if parsed_questions is None and source_plan is not None and source_plan["eligible"]:
            parse_model = os.getenv("PREFER_PARSE_MODEL") or os.getenv("DEEPSEEK_PARSE_MODEL", "deepseek-flash")
            try:
                parsed_questions = request_word_source_metadata(
                    source_plan, dependencies.get_curriculum(), provider=dependencies.resolve_provider(parse_model),
                    post=dependencies.post, diagnostics=diagnostics,
                    normalize_fillin=normalize_fillin_macro,
                    check_cancelled=lambda: dependencies.tasks.check_cancelled(task_id),
                )
            except TaskCancelled:
                raise
            except Exception as exc:
                diagnostics["word_source_metadata"].update(
                    status="fallback", error_type=type(exc).__name__,
                )
                if diagnostics["word_source_metadata"].get("calls"):
                    raise ValueError("Word 元数据请求未完成；请求可能已计费，未自动重试。请核对原文后手动重试。") from exc
        if parsed_questions is None:
            dependencies.tasks.check_cancelled(task_id)
            fallback_kwargs = {}
            if diagnostics["word_source_metadata"].get("calls"):
                # At most one metadata POST followed by one ordinary split POST.
                fallback_kwargs["connection_retry"] = False
                fallback_kwargs["check_cancelled"] = lambda: dependencies.tasks.check_cancelled(task_id)
            parsed_questions = dependencies.parse_text(
                locked_markdown_content,
                False,  # Extract original answers; solve reviewed questions in the frontend.
                diagnostics=diagnostics,
                preserve_source_answers=True,
                **fallback_kwargs,
            )
        # Keep a bounded task-local baseline before local validation. A local
        # post-processing failure must not erase the already paid split output.
        # This is not a cross-upload model cache and is never a normal log entry.
        word_source_cache = {
            "source_markdown": full_markdown_content,
            "split_questions": parsed_questions,
            "source_sha256": hashlib.sha256(file_bytes).hexdigest(),
        }
        if len(json.dumps(word_source_cache, ensure_ascii=False)) <= 500_000:
            dependencies.tasks.update(task_id, docx_source_cache=copy.deepcopy(word_source_cache))
        staged = copy.deepcopy(parsed_questions) if preserved_indices else parsed_questions
        lock_report = dependencies.reconcile_math(staged, math_locks, full_markdown_content)
        if preserved_indices:
            for index, candidate in enumerate(staged):
                if index not in preserved_indices:
                    parsed_questions[index] = candidate
                    continue
                original = parsed_questions[index]
                changed = any(original.get(field) != candidate.get(field) for field in ("content", "answer_markdown"))
                if candidate.get("source_review"):
                    original["source_review"] = candidate["source_review"]
                if changed:
                    review = original.setdefault("source_review", {})
                    review["required"] = True
                    review.setdefault("reasons", []).append("全卷来源比对未唯一对应，已保留局部认证原文，请对照原卷核对。")
        previous_warnings = list(diagnostics.get("warnings", []))
        diagnostics.update(lock_report)
        diagnostics["warnings"] = previous_warnings + lock_report.get("warnings", [])
        finalize_source_answers(parsed_questions, full_markdown_content)
        diagnostics["source_review_count"] = sum(
            bool(q.get("source_review", {}).get("required")) for q in parsed_questions
        )

        dependencies.tasks.check_cancelled(task_id)
        if preserved_indices:
            final_questions = dependencies.postprocess(
                parsed_questions, paper_title, task_id, [full_markdown_content], preserved_indices=preserved_indices)
        elif diagnostics["word_source_metadata"].get("status") == "used":
            final_questions = dependencies.postprocess(
                parsed_questions, paper_title, task_id, [full_markdown_content],
                source_body_preserved=True,
            )
        else:
            final_questions = dependencies.postprocess(parsed_questions, paper_title, task_id, [full_markdown_content])
        prepare_word_extraction_reviews(
            final_questions, diagnostics, full_markdown_content,
            extraction_diagnostics=extraction_diagnostics,
            source_review_evidence=extraction_review_evidence,
            source_document_sha256=source_document_sha256,
        )
        if docx_verify_suspicions and diagnostics.get("source_review_count"):
            def check_word_cancelled():
                dependencies.tasks.check_cancelled(task_id)

            def register_word_page(path):
                temp_assets.append(path)
                dependencies.tasks.update(task_id, temp_assets=list(temp_assets))

            dependencies.tasks.update(
                task_id, status="source_verification", progress=90,
                log="正在将原 Word 渲染成页面，仅对剩余疑点进行原文核验...",
                diagnostics=diagnostics,
            )
            acquired = False
            try:
                from mathbank.docx_source_evidence import prepare_docx_source_evidence
                from mathbank.docx_source_verify import verify_docx_source_suspicions

                evidence = prepare_docx_source_evidence(
                    file_bytes, output_dir=Path(dependencies.tmp_upload_dir), url_prefix=f"/{dependencies.upload_dir_rel}/tmp",
                    task_id=task_id, register_asset=register_word_page, check_cancelled=check_word_cancelled,
                )
                dependencies.tasks.update(task_id, docx_source_evidence=evidence)
                while not acquired:
                    check_word_cancelled()
                    acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                diagnostics["docx_source_verification"] = verify_docx_source_suspicions(
                    final_questions, diagnostics, full_markdown_content, evidence,
                    check_cancelled=check_word_cancelled,
                )
            except TaskCancelled:
                raise
            except Exception as exc:
                # Optional verification must never discard the completed split
                # or manufacture a successful review when its preparation fails.
                pending = sum(bool(q.get("source_review", {}).get("required")) for q in final_questions)
                diagnostics["source_review_count"] = pending
                diagnostics["docx_source_verification"] = {
                    "status": "failed", "pending": pending,
                    "notes": [f"原文核验未完成（{type(exc).__name__}），已保留拆题结果和原核对提示。"],
                }
            finally:
                if acquired:
                    dependencies.ocr_semaphore.release()
        else:
            diagnostics["docx_source_verification"] = {
                "status": "no_candidates" if docx_verify_suspicions else "disabled",
                "calls": 0, "checked": 0, "confirmed": 0,
                "pending": diagnostics.get("source_review_count", 0), "usage": {},
            }
        finalize_word_extraction_reviews(
            final_questions, diagnostics, full_markdown_content,
            extraction_diagnostics=extraction_diagnostics,
            source_review_evidence=extraction_review_evidence,
            source_document_sha256=source_document_sha256,
        )
        make_source_review_advisory(final_questions, diagnostics)
        dependencies.tasks.check_cancelled(task_id)
        partial = bool(diagnostics.get("word_hybrid", {}).get("partial"))
        completion_log = (f"Word 已保留 {len(final_questions)} 道完整题目；部分疑点题组未完成，原文与未匹配题段可展开核对。"
                          if partial else "Word 拆分完成，可选择题目导入；原文说明可按需展开查看。")
        completed = dependencies.tasks.complete(
            task_id,
            log=completion_log,
            partial=partial,
            data=final_questions,
            generate_answers=generate_answers,
            document_type="docx",
            diagnostics=diagnostics,
            temp_assets=list(temp_assets),
        )
        if not completed:
            dependencies.delete_temp_assets(temp_assets)
    except TaskCancelled:
        dependencies.delete_temp_assets(temp_assets)
    except Exception as ex:
        dependencies.delete_temp_assets(temp_assets)
        dependencies.tasks.fail(
            task_id,
            f"Word 试卷拆解失败: {str(ex)}",
            document_type="docx",
            diagnostics=diagnostics,
        )
