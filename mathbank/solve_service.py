"""Solve service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Form


@dataclass(frozen=True)
class SolveServiceDependencies:
    state: RuntimeState
    JSONResponse: Any
    StreamingResponse: Any
    apply_model_thinking_policy: Any
    build_ai_solve_prompts: Any
    json: Any
    os: Any
    post_chat_completion: Any
    requests: Any
    resolve_text_provider: Any


def ai_solve(content: str=Form(...), question_type: str=Form('detailed_answer'), ocr_result: str=Form(''), custom_prompt: str=Form(''), thinking: str=Form('enabled'), model: str=Form(''), stream: str=Form('false'), *, dependencies: SolveServiceDependencies):
    provider = dependencies.resolve_text_provider(model or dependencies.os.getenv("PREFER_SOLVE_MODEL") or "deepseek-v4-pro")
    api_key = provider.api_key
    api_base = provider.api_base
    model_name = provider.model_name
    provider_name = provider.credential_label

    if not api_key:
        return dependencies.JSONResponse(
            content={
                "status": "error",
                "message": f"未配置对应的 API Key ({provider_name})，无法智能解答！请在工作台右上角设置面板进行配置。"
            },
            status_code=400
        )

    try:
        system_instructions, user_prompt = dependencies.build_ai_solve_prompts(
            question_type=question_type,
            content=content,
            ocr_result=ocr_result,
            custom_prompt=custom_prompt,
        )

        # Keep the legacy fallback cap for older Bailian models. Current
        # Qwen3.7/3.8 requests are converted below to max_completion_tokens.
        max_output_tokens = 8192 if provider.provider_code == "bailian" else 16384

        data = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_output_tokens
        }

        data["temperature"] = 0.2
        data = dependencies.apply_model_thinking_policy(
            data,
            provider=provider,
            task="solve",
            thinking_enabled=thinking == "enabled",
        )

        if stream == "true":
            def event_generator():
                data["stream"] = True
                try:
                    response = dependencies.post_chat_completion(
                        provider,
                        data,
                        timeout=300,
                        stream=True,
                        check_status=False,
                    )
                    if response.status_code != 200:
                        error_msg = f"{provider_name} 接口错误: HTTP {response.status_code}"
                        yield f"data: {dependencies.json.dumps({'status': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                        return

                    reasoning_count = 0
                    content_count = 0

                    for line in response.iter_lines():
                        if not line:
                            continue
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data:"):
                            data_content = line_str[5:].strip()
                            if data_content == "[DONE]":
                                break
                            try:
                                chunk_json = dependencies.json.loads(data_content)

                                # 优先读取接口可能返回的官方 usage 统计
                                usage = chunk_json.get("usage")
                                if usage and isinstance(usage, dict):
                                    c_tok = usage.get("completion_tokens")
                                    r_tok = usage.get("completion_tokens_details", {}).get("reasoning_tokens") if isinstance(usage.get("completion_tokens_details"), dict) else None
                                    if c_tok is not None:
                                        content_count = max(content_count, c_tok)
                                    if r_tok is not None:
                                        reasoning_count = max(reasoning_count, r_tok)

                                delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                                content_piece = delta.get("content") or ""

                                # 针对不同模型的流式数据块进行动态 Token 数量估算（兼容大 Chunk 输出模型如 Gemini Flash）
                                if reasoning:
                                    cjk_c = sum(1 for c in reasoning if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f' or '\uff00' <= c <= '\uffef')
                                    oth_c = len(reasoning) - cjk_c
                                    reasoning_count += max(1, int(cjk_c * 1.2 + oth_c / 4.0 + 0.99))
                                if content_piece:
                                    cjk_c = sum(1 for c in content_piece if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f' or '\uff00' <= c <= '\uffef')
                                    oth_c = len(content_piece) - cjk_c
                                    content_count += max(1, int(cjk_c * 1.2 + oth_c / 4.0 + 0.99))

                                if reasoning or content_piece:
                                    yield f"data: {dependencies.json.dumps({'status': 'processing', 'reasoning': reasoning, 'content': content_piece, 'reasoning_count': reasoning_count, 'content_count': content_count}, ensure_ascii=False)}\n\n"
                            except Exception:
                                continue
                    yield f"data: {dependencies.json.dumps({'status': 'done'}, ensure_ascii=False)}\n\n"
                except dependencies.requests.exceptions.Timeout:
                    friendly_msg = (
                        f"AI 解析生成超时（限制为 300 秒）。这通常是因为 {provider_name} "
                        f"服务端当前排队拥堵或推理速度过慢。建议您稍后再试，或在设置中切换为「DeepSeek 官方」或「阿里百炼」等更稳定的接口平台。"
                    )
                    yield f"data: {dependencies.json.dumps({'status': 'error', 'message': friendly_msg}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    yield f"data: {dependencies.json.dumps({'status': 'error', 'message': f'AI 解析生成出错: {str(e)}'}, ensure_ascii=False)}\n\n"

            return dependencies.StreamingResponse(event_generator(), media_type="text/event-stream")

        # Generous 300 seconds timeout (5 minutes) for high-school math reasoning and network proxies
        response = dependencies.post_chat_completion(
            provider,
            data,
            timeout=300,
            provider_name=provider_name,
        )

        res_json = response.json()

        msg_obj = res_json.get("choices", [{}])[0].get("message", {})
        ai_message = msg_obj.get("content") or ""
        reasoning_content = msg_obj.get("reasoning_content") or ""

        # Robust fallback: if content is empty but reasoning is present, use reasoning as explanation
        if not ai_message and reasoning_content:
            ai_message = f"【深度思考推理过程】\n{reasoning_content}\n\n【参考解析】已成功生成推理步骤。如果需要标准的三板块排版，请尝试在控制面板中关闭「AI 深度思考推理」再次生成。"

        if not ai_message:
            print(
                f"[Solve API] Provider returned an empty message "
                f"(provider={provider.provider_code}, status={response.status_code})."
            )
            raise Exception(f"{provider_name} 返回了空消息，请检查 API 或账户余额。")

        return {
            "status": "success",
            "solution": ai_message
        }
    except dependencies.requests.exceptions.Timeout:
        friendly_msg = (
            f"AI 解析生成超时（限制为 300 秒）。这通常是因为 {provider_name} "
            f"服务端当前排队拥堵或推理速度过慢。建议您稍后再试，或在设置中切换为「DeepSeek 官方」或「阿里百炼」等更稳定的接口平台。"
        )
        return dependencies.JSONResponse(
            content={"status": "error", "message": friendly_msg},
            status_code=500
        )
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"AI 解析生成出错: {str(e)}"},
            status_code=500
        )
