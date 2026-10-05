"""Paper parse service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Form


@dataclass(frozen=True)
class PaperParseServiceDependencies:
    state: RuntimeState
    JSONResponse: Any
    ParseConfigurationError: Any
    apply_model_thinking_policy: Any
    build_import_parse_system_prompt: Any
    build_pdf_parse_system_prompt: Any
    finalize_source_answers: Any
    get_current_curriculum: Callable
    json: Any
    lock_visible_math: Any
    make_source_review_advisory: Any
    normalize_question_math_markdown: Any
    os: Any
    parse_paper_completion: Any
    post_chat_completion: Any
    prepare_tex_source: Any
    re: Any
    reconcile_visible_math: Any
    resolve_text_provider: Any
    tex_asset_references_match: Any
    uuid: Any


def parse_paper_text_internal(latex_content: str, generate_answers_bool: bool, *, diagnostics: dict | None=None, preserve_source_answers: bool=False, dependencies: PaperParseServiceDependencies) -> list:
    """内部通用函数：调用选定的 LLM 接口，将 LaTeX 试卷内容解析拆分为结构化 JSON 卡片"""
    parse_model = dependencies.os.getenv("PREFER_PARSE_MODEL") or dependencies.os.getenv("DEEPSEEK_PARSE_MODEL", "deepseek-flash")
    provider = dependencies.resolve_text_provider(parse_model)
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.provider_label

    if not api_key:
        raise dependencies.ParseConfigurationError(f"未配置对应的 API Key ({provider.credential_label})，无法智能拆解试卷！请在工作台右上角设置面板进行配置。")

    system_instructions = dependencies.build_pdf_parse_system_prompt(
        dependencies.get_current_curriculum(), generate_answers_bool
    )

    max_output_tokens = 65536

    data = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": latex_content}
        ],
        "response_format": {
            "type": "json_object"
        },
        "temperature": 0.2,
        "max_tokens": max_output_tokens
    }

    data = dependencies.apply_model_thinking_policy(
        data,
        provider=provider,
        task="parse",
    )

    response = dependencies.post_chat_completion(
        provider,
        data,
        timeout=180,
        provider_name=provider_name,
    )

    parsed_questions = dependencies.parse_paper_completion(
        response.json(),
        raw_markdown="" if preserve_source_answers else latex_content,
        diagnostics=diagnostics,
    )
    if preserve_source_answers:
        # Compare the original response before answer filtering or formula edits.
        return parsed_questions

    # 强制进行静默净化：若未勾选自动生成答案，则对于没有带有 [EXTRACTED_ORIGINAL] 的解析和解答，将其强行抹平为空。
    for q in parsed_questions:
        ans = q.get("answer_markdown", "")
        if not ans:
            q["answer_markdown"] = ""
        elif not generate_answers_bool:
            if "[EXTRACTED_ORIGINAL]" in ans:
                q["answer_markdown"] = ans.replace("[EXTRACTED_ORIGINAL]", "").strip()
            else:
                q["answer_markdown"] = ""
        else:
            q["answer_markdown"] = ans.replace("[EXTRACTED_ORIGINAL]", "").strip()

        for field in ("content", "answer_markdown"):
            value = q.get(field, "")
            if isinstance(value, str) and value:
                q[field] = dependencies.normalize_question_math_markdown(value)

    return parsed_questions


def ai_parse_paper(latex_content: str=Form(...), paper_title: str=Form(''), image_mapping_json: str=Form('{}'), generate_answers: str=Form('false'), *, dependencies: PaperParseServiceDependencies):
    generate_answers_bool = generate_answers.lower() in ("true", "1", "yes")
    parse_model = dependencies.os.getenv("PREFER_PARSE_MODEL") or dependencies.os.getenv("DEEPSEEK_PARSE_MODEL", "deepseek-flash")
    provider = dependencies.resolve_text_provider(parse_model)
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.provider_label

    if not api_key:
        return dependencies.JSONResponse(
            content={
                "status": "error",
                "message": f"未配置对应的 API Key ({provider.credential_label})，无法智能拆解试卷！请在工作台右上角设置面板进行配置。"
            },
            status_code=400
        )

    try:
        image_mapping = dependencies.json.loads(image_mapping_json)
        if not isinstance(image_mapping, dict):
            image_mapping = {}
    except Exception:
        image_mapping = {}

    try:
        tex_result = dependencies.prepare_tex_source(latex_content)
        tex_diagnostics = tex_result["diagnostics"]
        model_source, math_locks = dependencies.lock_visible_math(
            tex_result["model_source"],
            "TEX_" + dependencies.uuid.uuid4().hex[:16],
        )
        tex_diagnostics["math_locks_created"] = len(math_locks)
        if not paper_title.strip() and tex_result["title"]:
            paper_title = tex_result["title"]

        system_instructions = dependencies.build_import_parse_system_prompt(dependencies.get_current_curriculum())

        max_output_tokens = 65536

        data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": model_source}
            ],
            "response_format": {
                "type": "json_object"
            },
            "temperature": 0.2,
            "max_tokens": max_output_tokens
        }

        data = dependencies.apply_model_thinking_policy(
            data,
            provider=provider,
            task="parse",
        )

        response = dependencies.post_chat_completion(
            provider,
            data,
            timeout=180,
            provider_name=provider_name,
        )

        parsed_questions = dependencies.parse_paper_completion(
            response.json(), diagnostics=tex_diagnostics,
        )
        lock_report = dependencies.reconcile_visible_math(
            parsed_questions, math_locks, tex_result["model_source"],
        )
        previous_warnings = list(tex_diagnostics.get("warnings", []))
        tex_diagnostics.update(lock_report)
        tex_diagnostics["warnings"] = previous_warnings + lock_report.get("warnings", [])
        dependencies.finalize_source_answers(parsed_questions, tex_result["model_source"])
        tex_diagnostics["source_review_count"] = sum(
            bool(q.get("source_review", {}).get("required")) for q in parsed_questions
        )
        tex_diagnostics["question_count_actual"] = len(parsed_questions)
        estimated_count = tex_diagnostics.get("question_count_estimate", 0)
        if estimated_count and estimated_count != len(parsed_questions):
            tex_diagnostics.setdefault("warnings", []).append(
                f"源码约识别到 {estimated_count} 道题，但模型返回 {len(parsed_questions)} 道，请重点核对是否漏题或误拆。"
            )

        for graphic_ref in tex_diagnostics.get("referenced_graphics", []):
            graphic_ref = str(graphic_ref)
            candidates = []
            for question in parsed_questions:
                content_graphics = dependencies.re.findall(
                    r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}",
                    question.get("content", ""),
                )
                question_refs = content_graphics + [
                    str(value) for value in question.get("referenced_images", [])
                ]
                if any(dependencies.tex_asset_references_match(graphic_ref, value) for value in question_refs):
                    candidates.append(question)
            if len(candidates) == 1 and not any(
                dependencies.tex_asset_references_match(graphic_ref, existing)
                for existing in candidates[0]["referenced_images"]
            ):
                candidates[0]["referenced_images"].append(graphic_ref)
            elif not candidates:
                tex_diagnostics.setdefault("unassigned_source_images", []).append(graphic_ref)

        # Translate referenced_images to server paths
        for q in parsed_questions:
            # 智能提取出处双重保险：AI 提取优先，若 AI 未提取则尝试正则从 content 中提取
            extracted_source = q.get("source")
            content_str = q.get("content", "")

            # 正则匹配题干开头形如 "10. (2019·全国·高考真题)已知..." 的出处
            # group(1): 题号前缀, group(2): 左括号, group(3): 出处内容, group(4): 右括号
            prefix_match = dependencies.re.match(r'^(\s*(?:\d+[\.、\s]*)?)([\(（])([^\(（\)）\s]{4,})([\)）])', content_str)
            if prefix_match:
                if not extracted_source:
                    extracted_source = prefix_match.group(3).strip()
                # 剔除题干中的出处括号及前面的题号前缀，保持题干纯净
                to_remove = prefix_match.group(1) + prefix_match.group(2) + prefix_match.group(3) + prefix_match.group(4)
                content_str = content_str.replace(to_remove, "", 1).strip()
                # 移除可能残存的开头符号（如句点或顿号）
                content_str = dependencies.re.sub(r'^[\s、\.．]+', '', content_str)
                q["content"] = content_str

            q["source"] = (extracted_source or paper_title).strip()

            # Clean up double-escaped literal \n in fields
            for field in ["content", "answer_markdown"]:
                if field in q and isinstance(q[field], str):
                    text = q[field]
                    # Replace literal "\n" safely using negative lookahead (so it doesn't touch commands like \normalsize or \nabla)
                    text = dependencies.re.sub(r'\\n(?![a-zA-Z])', '\n', text)
                    q[field] = text

            # Map images
            mapped_images = []
            ref_imgs = q.get("referenced_images", [])
            for ref_name in ref_imgs:
                ref_name = str(ref_name)
                # Direct match or fuzzy match
                found_path = None
                for orig_name, serv_path in image_mapping.items():
                    if dependencies.tex_asset_references_match(ref_name, orig_name):
                        found_path = serv_path
                        break
                if found_path:
                    if found_path not in mapped_images:
                        mapped_images.append(found_path)
                    include_pattern = dependencies.re.compile(
                        r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{\s*([^}]+?)\s*\}"
                    )
                    q["content"] = include_pattern.sub(
                        lambda match: (
                            f"![插图]({found_path})"
                            if dependencies.tex_asset_references_match(ref_name, match.group(1))
                            else match.group(0)
                        ),
                        q["content"],
                    )
                else:
                    tex_diagnostics.setdefault("unmapped_images", []).append(str(ref_name))

            q["image_paths"] = mapped_images

            # If AI didn't map it in content text but referenced it, append it to content
            for img_path in mapped_images:
                if img_path not in q["content"]:
                    q["content"] += f"\n\n![插图]({img_path})\n\n"

        unmapped_images = sorted(set(tex_diagnostics.get("unmapped_images", [])))
        unassigned_images = sorted(set(tex_diagnostics.get("unassigned_source_images", [])))
        tex_diagnostics["unmapped_images"] = unmapped_images
        tex_diagnostics["unassigned_source_images"] = unassigned_images
        if unmapped_images:
            tex_diagnostics.setdefault("warnings", []).append(
                "以下 TeX 配图未找到同名上传文件：" + "、".join(unmapped_images[:8])
            )
        if unassigned_images:
            tex_diagnostics.setdefault("warnings", []).append(
                "以下配图未能确定所属题目：" + "、".join(unassigned_images[:8])
            )
        dependencies.make_source_review_advisory(parsed_questions, tex_diagnostics)
        return {
            "status": "success",
            "questions": parsed_questions,
            "tex_diagnostics": tex_diagnostics,
        }
    except Exception as e:
        return dependencies.JSONResponse(
            content={
                "status": "error", "message": f"试卷解析失败: {str(e)}",
                "tex_diagnostics": locals().get("tex_diagnostics", {}),
            },
            status_code=500
        )
