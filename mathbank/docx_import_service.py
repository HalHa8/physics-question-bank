"""Word import orchestration, sharing only the task-scoped dependency contract."""

import copy
import hashlib
import json
import os
from pathlib import Path

from mathbank.document_import_context import DocumentImportDependencies
from mathbank.document_text import extract_title_from_latex
from mathbank.task_manager import TaskCancelled
from mathbank.content_locks import lock_visible_math
from mathbank.paper_parse import finalize_source_answers
from mathbank.import_review import make_source_review_advisory


def run_docx_parsing_task(
    task_id: str,
    file_bytes: bytes,
    filename: str,
    generate_answers: bool = False,
    docx_verify_suspicions: bool = False,
    *, dependencies: DocumentImportDependencies,
):
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
        )
        temp_assets = docx_res.get("image_paths", [])
        if not docx_res.get("success") or not docx_res.get("markdown"):
            raise ValueError(docx_res.get("error") or "未能从 Word 文档中提取出有效试题内容！")

        full_markdown_content = docx_res["markdown"]
        img_count = docx_res.get("image_count", 0)
        diagnostics = docx_res.get("diagnostics", {})
        converted_count = diagnostics.get("omml_converted", 0) + diagnostics.get("mtef_converted", 0)
        review_count = diagnostics.get("review_required", 0)
        extraction_log = (
            f"Word 提取完成：{converted_count} 个公式已转换，{img_count} 张图片已保留"
            + (f"，{review_count} 处需人工核对。" if review_count else "，未发现需人工核对的内容。")
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
        parsed_questions = dependencies.parse_text(
            locked_markdown_content,
            False,  # Extract original answers; solve reviewed questions in the frontend.
            diagnostics=diagnostics,
            preserve_source_answers=True,
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
        lock_report = dependencies.reconcile_math(parsed_questions, math_locks, full_markdown_content)
        previous_warnings = list(diagnostics.get("warnings", []))
        diagnostics.update(lock_report)
        diagnostics["warnings"] = previous_warnings + lock_report.get("warnings", [])
        finalize_source_answers(parsed_questions, full_markdown_content)
        diagnostics["source_review_count"] = sum(
            bool(q.get("source_review", {}).get("required")) for q in parsed_questions
        )

        dependencies.tasks.check_cancelled(task_id)
        final_questions = dependencies.postprocess(parsed_questions, paper_title, task_id, [full_markdown_content])
        if docx_verify_suspicions and diagnostics.get("source_review_count"):
            from mathbank.docx_source_evidence import prepare_docx_source_evidence
            from mathbank.docx_source_verify import verify_docx_source_suspicions

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
            evidence = prepare_docx_source_evidence(
                file_bytes, output_dir=Path(dependencies.tmp_upload_dir), url_prefix=f"/{dependencies.upload_dir_rel}/tmp",
                task_id=task_id, register_asset=register_word_page, check_cancelled=check_word_cancelled,
            )
            dependencies.tasks.update(task_id, docx_source_evidence=evidence)
            acquired = False
            try:
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
        make_source_review_advisory(final_questions, diagnostics)
        dependencies.tasks.check_cancelled(task_id)
        completed = dependencies.tasks.complete(
            task_id,
            log="Word 拆分完成，可选择题目导入；原文说明可按需展开查看。",
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
