"""Paper export service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Depends
from sqlalchemy.orm import Session
from mathbank.database import get_db


@dataclass(frozen=True)
class PaperExportServiceDependencies:
    state: RuntimeState
    FIGURE_SIZE_VALUES: Any
    JSONResponse: Any
    PaperExportValidationError: Any
    Question: Any
    Response: Any
    _prepare_paper_export_questions: Callable
    apply_model_thinking_policy: Any
    build_answer_sheet_latex: Any
    build_latex_document: Any
    build_latex_error_explanation_prompts: Any
    build_local_latex_diagnostic: Any
    build_word_document: Any
    collect_referenced_images: Any
    compile_tex_to_pdf: Any
    create_full_bundle_zip_package: Any
    create_tex_zip_package: Any
    create_word_bundle_zip: Any
    datetime: Any
    explain_latex_compile_error: Callable
    merge_ai_latex_diagnostic: Any
    os: Any
    parse_ai_json: Any
    post_chat_completion: Any
    re: Any
    resolve_text_provider: Any


def _prepare_paper_export_questions(questions_input, db: Session, *, dependencies: PaperExportServiceDependencies) -> list[dict]:
    """Validate an export cart and hydrate every referenced question in order."""
    if not isinstance(questions_input, list) or not questions_input:
        raise dependencies.PaperExportValidationError("卷面为空，试卷中至少需要包含一道题目。")
    if len(questions_input) > 200:
        raise dependencies.PaperExportValidationError("单份试卷不能超过 200 道题。")

    normalized_items = []
    seen_question_ids = set()
    for item in questions_input:
        if not isinstance(item, dict):
            raise dependencies.PaperExportValidationError("试卷题目数据格式不正确。")
        raw_question_id = item.get("id")
        if isinstance(raw_question_id, bool):
            raise dependencies.PaperExportValidationError("试卷中包含无效的题目 ID。")
        if isinstance(raw_question_id, int):
            question_id = raw_question_id
        elif isinstance(raw_question_id, str) and raw_question_id.strip().isdigit():
            question_id = int(raw_question_id.strip())
        else:
            raise dependencies.PaperExportValidationError("试卷中包含无效的题目 ID。")
        if question_id <= 0:
            raise dependencies.PaperExportValidationError("试卷中包含无效的题目 ID。")
        if question_id in seen_question_ids:
            raise dependencies.PaperExportValidationError("同一道题不能在一份试卷中重复出现。")
        seen_question_ids.add(question_id)
        normalized_items.append((item, question_id))

    questions_db = db.query(dependencies.Question).filter(
        dependencies.Question.id.in_(seen_question_ids)
    ).all()
    question_map = {question.id: question.to_dict() for question in questions_db}
    if seen_question_ids - set(question_map):
        raise dependencies.PaperExportValidationError("试卷中包含已删除或不存在的题目。")

    questions_data = []
    for item, question_id in normalized_items:
        question_data = dict(question_map[question_id])
        if item.get("figure_align"):
            question_data["figure_align"] = item.get("figure_align")
        if isinstance(item.get("figure_align_custom"), bool):
            question_data["figure_align_custom"] = item.get("figure_align_custom")
        if (
            isinstance(item.get("figure_size"), str)
            and item.get("figure_size") in dependencies.FIGURE_SIZE_VALUES
        ):
            question_data["figure_size"] = item.get("figure_size")
        try:
            score = int(item.get("score", 5))
        except (TypeError, ValueError) as exc:
            raise dependencies.PaperExportValidationError("试卷中包含无效的题目分值。") from exc
        export_item = {"question": question_data, "score": score}
        if item.get("solution_space") is not None:
            export_item["solution_space"] = item.get("solution_space")
        questions_data.append(export_item)
    return questions_data


def export_paper_tex(payload: dict, db: Session=Depends(get_db), *, dependencies: PaperExportServiceDependencies):
    """导出 LaTeX 源码 ZIP 压缩包"""
    try:
        title = payload.get("title", "2026年高中物理模拟考试试卷")
        subtitle = payload.get("subtitle", "")
        paper_type = payload.get("paper_type", "exam")
        show_secret = payload.get("show_secret", True)
        show_notice = payload.get("show_notice", True)
        questions_input = payload.get("questions", [])
        questions_data = dependencies._prepare_paper_export_questions(questions_input, db)

        tex_main = dependencies.build_latex_document(title, subtitle, paper_type, questions_data, include_answers=False, show_secret=show_secret, show_notice=show_notice, question_types=dependencies.state.METADATA_CACHE.get("question_types", []), section_order=payload.get("section_order"))
        tex_ans = dependencies.build_latex_document(title + " (参考答案与解析)", subtitle, paper_type, questions_data, include_answers=True, show_secret=show_secret, show_notice=show_notice, question_types=dependencies.state.METADATA_CACHE.get("question_types", []), section_order=payload.get("section_order"))

        if paper_type == "exam_19":
            tex_answer_sheet = dependencies.build_answer_sheet_latex(title, subtitle, questions_data)
        else:
            tex_answer_sheet = None

        image_paths = dependencies.collect_referenced_images(questions_data, dependencies.state.UPLOAD_DIR, dependencies.state.UPLOAD_DIR_REL)
        zip_bytes = dependencies.create_tex_zip_package(title, tex_main, tex_ans, image_paths, answer_sheet_tex=tex_answer_sheet)

        from urllib.parse import quote
        safe_title = dependencies.re.sub(r'[/\\?%*:|"<>]', '_', title.strip()) or "试卷"
        encoded_filename = quote(f"{safe_title}.zip")
        return dependencies.Response(content=zip_bytes, media_type="application/zip", headers={
            "Content-Disposition": f"attachment; filename=\"paper_export.zip\"; filename*=utf-8''{encoded_filename}"
        })
    except dependencies.PaperExportValidationError as e:
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": f"生成 LaTeX 源码失败: {str(e)}"}, status_code=500)


def export_paper_bundle(payload: dict, db: Session=Depends(get_db), *, dependencies: PaperExportServiceDependencies):
    """一键导出合并全套 Zip 压缩包（包含 LaTeX 源码、相关插图以及已编译好的 PDF）"""
    try:
        title = payload.get("title", "2026年高中物理模拟考试试卷")
        subtitle = payload.get("subtitle", "")
        paper_type = payload.get("paper_type", "exam")
        show_secret = payload.get("show_secret", True)
        show_notice = payload.get("show_notice", True)
        questions_input = payload.get("questions", [])
        questions_data = dependencies._prepare_paper_export_questions(questions_input, db)

        tex_main = dependencies.build_latex_document(title, subtitle, paper_type, questions_data, include_answers=False, show_secret=show_secret, show_notice=show_notice, question_types=dependencies.state.METADATA_CACHE.get("question_types", []), section_order=payload.get("section_order"))
        tex_ans = dependencies.build_latex_document(title + " (参考答案与解析)", subtitle, paper_type, questions_data, include_answers=True, show_secret=show_secret, show_notice=show_notice, question_types=dependencies.state.METADATA_CACHE.get("question_types", []), section_order=payload.get("section_order"))

        if paper_type == "exam_19":
            tex_answer_sheet = dependencies.build_answer_sheet_latex(title, subtitle, questions_data)
        else:
            tex_answer_sheet = None

        image_paths = dependencies.collect_referenced_images(questions_data, dependencies.state.UPLOAD_DIR, dependencies.state.UPLOAD_DIR_REL)

        # Pre-compile PDFs
        main_pdf_bytes, _ = dependencies.compile_tex_to_pdf(tex_main, image_paths)
        ans_pdf_bytes, _ = dependencies.compile_tex_to_pdf(tex_ans, image_paths)
        if paper_type == "exam_19" and tex_answer_sheet:
            answer_sheet_pdf_bytes, _ = dependencies.compile_tex_to_pdf(tex_answer_sheet, image_paths)
        else:
            answer_sheet_pdf_bytes = None

        zip_bytes = dependencies.create_full_bundle_zip_package(
            title, tex_main, tex_ans, image_paths,
            answer_sheet_tex=tex_answer_sheet,
            main_pdf_bytes=main_pdf_bytes,
            ans_pdf_bytes=ans_pdf_bytes,
            answer_sheet_pdf_bytes=answer_sheet_pdf_bytes
        )

        from urllib.parse import quote
        safe_title = dependencies.re.sub(r'[/\\?%*:|"<>]', '_', title.strip()) or "试卷"
        filename = f"{safe_title}_全套归档.zip"
        encoded_filename = quote(filename)
        return dependencies.Response(content=zip_bytes, media_type="application/zip", headers={
            "Content-Disposition": f"attachment; filename=\"paper_bundle.zip\"; filename*=utf-8''{encoded_filename}"
        })
    except dependencies.PaperExportValidationError as e:
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": f"生成全套合并包失败: {str(e)}"}, status_code=500)


def explain_latex_compile_error(log_text: str, tex_content: str, *, dependencies: PaperExportServiceDependencies) -> dict:
    """Explain one compile failure locally, then enrich it with the parse model."""
    diagnostic = dependencies.build_local_latex_diagnostic(log_text, tex_content)
    parse_model = dependencies.os.getenv("PREFER_PARSE_MODEL") or dependencies.os.getenv(
        "DEEPSEEK_PARSE_MODEL", "deepseek-flash"
    )
    provider = dependencies.resolve_text_provider(parse_model)
    if not provider.api_key:
        diagnostic["ai_note"] = "试卷拆解模型未配置，当前显示本地诊断结果。"
        return diagnostic

    system_prompt, user_prompt = dependencies.build_latex_error_explanation_prompts(diagnostic)
    payload = {
        "model": provider.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 1200,
    }
    payload = dependencies.apply_model_thinking_policy(
        payload,
        provider=provider,
        task="latex_diagnostic",
    )

    try:
        response = dependencies.post_chat_completion(
            provider,
            payload,
            timeout=45,
            provider_name=provider.provider_label,
        )
        raw_text = response.json()["choices"][0]["message"]["content"].strip()
        ai_value = dependencies.parse_ai_json(raw_text)
        return dependencies.merge_ai_latex_diagnostic(diagnostic, ai_value)
    except Exception:
        diagnostic["ai_note"] = "AI 暂时无法解释该错误，当前显示本地诊断结果。"
        return diagnostic


def export_paper_pdf(payload: dict, db: Session=Depends(get_db), *, dependencies: PaperExportServiceDependencies):
    """在线静默编译生成高清 PDF"""
    try:
        title = payload.get("title", "2026年高中物理模拟考试试卷")
        subtitle = payload.get("subtitle", "")
        paper_type = payload.get("paper_type", "exam")
        target = payload.get("target", "paper")  # "paper" or "sheet"
        include_answers = payload.get("include_answers", False)
        show_secret = payload.get("show_secret", True)
        show_notice = payload.get("show_notice", True)
        questions_input = payload.get("questions", [])
        questions_data = dependencies._prepare_paper_export_questions(questions_input, db)

        if target == "sheet":
            tex_content = dependencies.build_answer_sheet_latex(title, subtitle, questions_data)
        else:
            tex_content = dependencies.build_latex_document(title, subtitle, paper_type, questions_data, include_answers=include_answers, show_secret=show_secret, show_notice=show_notice, question_types=dependencies.state.METADATA_CACHE.get("question_types", []), section_order=payload.get("section_order"))

        image_paths = dependencies.collect_referenced_images(questions_data, dependencies.state.UPLOAD_DIR, dependencies.state.UPLOAD_DIR_REL)
        pdf_bytes, log_or_err = dependencies.compile_tex_to_pdf(tex_content, image_paths)

        if pdf_bytes:
            filename = f"sheet_{dependencies.datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf" if target == "sheet" else f"paper_{dependencies.datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            return dependencies.Response(content=pdf_bytes, media_type="application/pdf", headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            })
        else:
            diagnostic = dependencies.explain_latex_compile_error(log_or_err, tex_content)
            return dependencies.JSONResponse(
                content={
                    "status": "error",
                    "message": diagnostic.get("summary", "PDF 编译失败"),
                    "diagnostic": diagnostic,
                },
                status_code=400,
            )
    except dependencies.PaperExportValidationError as e:
        return dependencies.JSONResponse(content={"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        return dependencies.JSONResponse(content={"status": "error", "message": f"编译 PDF 异常: {str(e)}"}, status_code=500)


def export_paper_word(payload: dict, db: Session=Depends(get_db), *, dependencies: PaperExportServiceDependencies):
    """导出包含试卷正文与含答案解析两个 Word 文件的 ZIP 压缩包。"""
    try:
        title = payload.get("title", "2026年高中物理模拟考试试卷")
        subtitle = payload.get("subtitle", "")
        paper_type = payload.get("paper_type", "exam")
        show_secret = payload.get("show_secret", True)
        show_notice = payload.get("show_notice", True)
        questions_input = payload.get("questions", [])
        as_single_docx = bool(payload.get("as_single_docx", False))
        include_answers = bool(payload.get("include_answers", False))
        questions_data = dependencies._prepare_paper_export_questions(questions_input, db)

        from urllib.parse import quote
        safe_title = dependencies.re.sub(r'[/\\?%*:|"<>]', "_", title.strip()) or "试卷"

        if as_single_docx:
            docx_bytes, diagnostics = dependencies.build_word_document(
                title,
                subtitle,
                paper_type,
                questions_data,
                include_answers=include_answers,
                show_secret=show_secret,
                show_notice=show_notice,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                question_types=dependencies.state.METADATA_CACHE.get("question_types", []),
                section_order=payload.get("section_order"),
            )
            suffix = "_含答案与解析" if include_answers else ""
            filename = f"{safe_title}{suffix}.docx"
            encoded_filename = quote(filename)
            return dependencies.Response(
                content=docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f"attachment; filename=\"paper.docx\"; filename*=utf-8''{encoded_filename}",
                    "X-Word-Native-Formulas": str(diagnostics.get("native_formulas", 0)),
                    "X-Word-Fallback-Formulas": str(diagnostics.get("fallback_formulas", 0)),
                    "X-Word-Failed-Formulas": str(diagnostics.get("failed_formulas", 0)),
                    "X-Word-Missing-Images": str(diagnostics.get("missing_images", 0)),
                    "X-Word-Answer-Card-Omitted": "1" if diagnostics.get("answer_card_omitted") else "0",
                },
            )

        # Default: build clean student docx and full teacher docx with answers into a ZIP bundle
        main_docx, main_diag = dependencies.build_word_document(
            title,
            subtitle,
            paper_type,
            questions_data,
            include_answers=False,
            show_secret=show_secret,
            show_notice=show_notice,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            question_types=dependencies.state.METADATA_CACHE.get("question_types", []),
            section_order=payload.get("section_order"),
        )
        ans_docx, ans_diag = dependencies.build_word_document(
            title,
            subtitle,
            paper_type,
            questions_data,
            include_answers=True,
            show_secret=show_secret,
            show_notice=show_notice,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            question_types=dependencies.state.METADATA_CACHE.get("question_types", []),
            section_order=payload.get("section_order"),
        )

        zip_bytes = dependencies.create_word_bundle_zip(title, main_docx, ans_docx)
        filename = f"{safe_title}_Word打包.zip"
        encoded_filename = quote(filename)
        return dependencies.Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=\"paper_word_bundle.zip\"; filename*=utf-8''{encoded_filename}",
                "X-Word-Native-Formulas": str(main_diag.get("native_formulas", 0) + ans_diag.get("native_formulas", 0)),
                "X-Word-Fallback-Formulas": str(main_diag.get("fallback_formulas", 0) + ans_diag.get("fallback_formulas", 0)),
                "X-Word-Failed-Formulas": str(main_diag.get("failed_formulas", 0) + ans_diag.get("failed_formulas", 0)),
                "X-Word-Missing-Images": str(main_diag.get("missing_images", 0) + ans_diag.get("missing_images", 0)),
                "X-Word-Answer-Card-Omitted": "1" if main_diag.get("answer_card_omitted") else "0",
            },
        )
    except dependencies.PaperExportValidationError as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": str(e)}, status_code=400
        )
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"生成 Word 试卷包失败: {str(e)}"},
            status_code=500,
        )
