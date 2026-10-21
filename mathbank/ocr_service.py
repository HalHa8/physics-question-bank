"""Ocr service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import UploadFile, File, Form
from mathbank.ai_providers import MultimodalProviderConfig
from mathbank.ocr_illustrations import parse_single_ocr_response, materialize_ocr_illustrations
from mathbank.math_markdown import normalize_table_math_wrappers
from mathbank.prompts import build_single_ocr_vision_prompt, SINGLE_OCR_STRUCTURED_INSTRUCTIONS


@dataclass(frozen=True)
class OcrServiceDependencies:
    state: RuntimeState
    COMMON_OCR_PROMPT: Any
    PDF_ORIGINAL_COMMON_OCR_PROMPT: Any
    PDF_VISUAL_FIDELITY_RULE: Any
    request_pdf_vision: Callable
    completion_content: Callable
    ILLUSTRATION_BOX_PROMPT: Any
    Image: Any
    InvalidImageError: Any
    JSONResponse: Any
    MAX_OCR_IMAGE_BYTES: Any
    OCRConfigurationError: Any
    UploadTooLargeError: Any
    apply_model_thinking_policy: Any
    auto_crop_image: Callable
    compile_tikz_to_png: Callable
    draw_tikz_via_high_model: Callable
    io: Any
    normalize_fillin_macro: Any
    normalize_question_math_markdown: Any
    normalize_raster_image: Any
    ocr_via_provider: Callable
    os: Any
    post_chat_completion: Any
    read_stream_limited: Any
    requests: Any
    resolve_ocr_fallbacks: Any
    resolve_ocr_provider: Any
    uuid: Any


def ocr_via_provider(image_path: str, provider: MultimodalProviderConfig, include_illustration_box: bool=False, *, pdf_page: bool=False, check_cancelled=lambda: None, report_attempt=lambda _event: None, page_index=None, on_response=None, dependencies: OcrServiceDependencies) -> str:
    """Use one resolved multimodal provider for formula and text OCR."""
    import base64

    if not provider.supports_image_input:
        raise ValueError(
            f"{provider.provider_label} 模型 {provider.model_name} 不支持图像输入，"
            "请在默认公式识图模型中选择支持图片的模型。"
        )

    if pdf_page:
        check_cancelled()
        with open(image_path, 'rb') as image_file:
            encoded = base64.b64encode(image_file.read()).decode('ascii')
        payload = {
            'model': provider.model_name, 'stream': True, 'max_tokens': 16384,
            'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': dependencies.PDF_ORIGINAL_COMMON_OCR_PROMPT + dependencies.PDF_VISUAL_FIDELITY_RULE},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}},
            ]}],
        }
        payload = dependencies.apply_model_thinking_policy(payload, provider=provider, task='ocr')
        result = dependencies.request_pdf_vision(provider, payload, post=dependencies.post_chat_completion,
            validate=lambda body: {'markdown': dependencies.completion_content(body, 'PDF 页面识别', max_chars=200000)},
            label='PDF 页面识别', stage='page_ocr', page_index=page_index, max_attempts=1,
            check_cancelled=check_cancelled, report_attempt=report_attempt, on_response=on_response)
        return result['markdown']

    print(
        f"[OCR Flow] 正在向 {provider.provider_label} 提交多模态识别任务: "
        f"{image_path} (模型: {provider.model_name})..."
    )
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"读取并对图片进行 Base64 编码失败: {str(e)}")

    prompt = dependencies.COMMON_OCR_PROMPT
    if include_illustration_box:
        # Preserve the legacy argument/signature, but use upstream's named,
        # per-figure protocol for single screenshots. PDF callers stay text-only.
        prompt = build_single_ocr_vision_prompt()

    payload = {
        "model": provider.model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded_string}"
                        }
                    }
                ]
            }
        ],
        "stream": False
    }

    payload = dependencies.apply_model_thinking_policy(
        payload,
        provider=provider,
        task="ocr",
    )
    if include_illustration_box:
        payload["messages"].insert(0, {
            "role": "system", "content": SINGLE_OCR_STRUCTURED_INSTRUCTIONS,
        })

    timeout = 240
    # Chat-completion POSTs are not idempotent: a read timeout can happen after
    # the provider has accepted (and billed) the request.  Do not automatically
    # send the same image two or three times, including transport fallback.
    transport_options = {"retry_connection": False}
    response = dependencies.post_chat_completion(
        provider,
        payload,
        timeout=timeout,
        check_status=False,
        **transport_options,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"{provider.provider_label} API 识别失败: HTTP {response.status_code}"
        )

    res_json = response.json()
    try:
        choices = res_json.get("choices", [])
        if choices and len(choices) > 0:
            if choices[0].get("finish_reason") not in (None, "stop"):
                raise RuntimeError("识图输出未完整结束，已拒绝采用；未自动重试，请缩小截图范围后手动处理。")
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        else:
            raise RuntimeError(
                f"{provider.provider_label} 返回的数据中未包含 Choices 结果。"
            )
    except Exception as e:
        raise RuntimeError(
            f"解析 {provider.provider_label} 响应数据失败: {str(e)}"
        )


def ocr_formula(file: UploadFile=File(...), engine: str=Form(None), skip_tikz: bool=Form(False), *, dependencies: OcrServiceDependencies):
    import re
    temp_filepath = None
    created_crops = []
    try:
        # OCR route is synchronous and runs in FastAPI's worker pool.  Stream
        # only up to the endpoint cap, then fully decode/re-encode the image.
        file_bytes = dependencies.read_stream_limited(file.file, dependencies.MAX_OCR_IMAGE_BYTES)
        normalized = dependencies.normalize_raster_image(file_bytes)
        image = dependencies.Image.open(dependencies.io.BytesIO(normalized.data)).convert("RGB")

        # Keep the complete normalized screenshot: auto-trimming can remove
        # faint force arrows, circuit leads, polarity signs and axis labels.

        # 将裁剪后的图片保存为持久化 OCR 文件，未来可作为题目配图
        filename = f"ocr_original_{dependencies.uuid.uuid4().hex[:12]}.png"
        temp_filepath = dependencies.os.path.join(dependencies.state.UPLOAD_DIR, filename)
        image.save(temp_filepath, format="PNG")

        # 确定调用的具体引擎。
        # 临时传参 engine 取值: default, siliconflow, simpletex, ali_bailian
        if not engine or engine == "default":
            engine = dependencies.os.getenv("OCR_PREFER_ENGINE", "siliconflow")

        print(f"[OCR Flow] 当前决策分配识图引擎: {engine}")

        latex_content = None
        confidence = 0.95
        provider = ""

        known_ocr_engines = {
            "deepseek",
            "siliconflow",
            "ali_bailian",
            "bailian",
            "zhongzhan",
            "zhongzhan_gpt",
            "zhongzhan_claude",
        }
        if engine in known_ocr_engines:
            ocr_provider = dependencies.resolve_ocr_provider(engine)
            if ocr_provider.api_key and ocr_provider.api_key.strip():
                try:
                    with dependencies.state.PDF_OCR_SEMAPHORE:
                        latex_content = dependencies.ocr_via_provider(
                            temp_filepath,
                            ocr_provider,
                            include_illustration_box=True,
                        )
                    confidence = 0.99
                    provider = (
                        f"{ocr_provider.provider_label} "
                        f"({ocr_provider.model_name})"
                    )
                except Exception as e:
                    print(
                        f"[{ocr_provider.provider_label} 识别失败] "
                        f"发生异常: {str(e)}"
                    )
            else:
                print(
                    f"[OCR Flow Warning] 未配置 {ocr_provider.credential_label}，"
                    "当前识图引擎无法启动！"
                )

        if not latex_content:
            raise RuntimeError("当前分配的识图引擎无法启动或识别失败。请检查系统设置中所选识图平台的 API Key、模型名称和接口地址。")

        recognized = parse_single_ocr_response(latex_content)
        prefer_draw = dependencies.os.getenv("PREFER_DRAW_MODEL", "Qwen/Qwen3-VL-32B-Instruct")

        def draw_one(crop_path, text_context, instruction):
            return dependencies.draw_tikz_via_high_model(
                crop_path, prefer_draw, latex_content=text_context,
                instruction=instruction,
            )

        # One OCR request supplies text plus boxes. Cropping is local and never
        # initiates paid review/retries. All source crops remain teacher-review
        # candidates, not visually verified evidence.
        figures = materialize_ocr_illustrations(
            recognized, image, skip_tikz=skip_tikz,
            upload_root=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
            draw=draw_one, compile_tikz=dependencies.compile_tikz_to_png,
        )
        for item in figures["illustrations"]:
            source_path = item.get("reference_image_path") or item.get("image_path")
            if source_path and dependencies.os.path.basename(source_path).startswith("ocr_figure_"):
                created_crops.append(dependencies.os.path.join(
                    dependencies.state.UPLOAD_DIR, dependencies.os.path.basename(source_path)))
            if item["status"] in ("cropped", "tikz"):
                item["review"] = {"status": "manual_required"}
        latex_content = figures["markdown"].replace("\\,", "").replace("\\!", "")
        latex_content = dependencies.normalize_fillin_macro(latex_content)
        latex_content = normalize_table_math_wrappers(latex_content)
        latex_content = dependencies.normalize_question_math_markdown(latex_content)
        first_asset = figures["tikz_assets"][0] if figures["tikz_assets"] else {}
        saved_filepath = temp_filepath
        result = {
            "status": "success",
            "latex": latex_content,
            "confidence": confidence,
            "provider": provider,
            "image_path": f"/{dependencies.state.UPLOAD_DIR_REL}/{dependencies.os.path.basename(saved_filepath)}",
            "tikz_code": first_asset.get("tikz_code"),
            "tikz_image_path": first_asset.get("image_path"),
            "illustrations": figures["illustrations"],
            "tikz_assets": figures["tikz_assets"],
            "image_layouts": figures["image_layouts"],
            "warnings": figures["warnings"],
            "illustration_review": {"status": "manual_required", "visual_calls": 0},
        }
        temp_filepath = None
        created_crops.clear()
        return result
    except dependencies.UploadTooLargeError:
        return dependencies.JSONResponse(
            content={"status": "error", "message": "公式识图失败: 图片不能超过 10MB。"},
            status_code=413,
        )
    except dependencies.InvalidImageError as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"公式识图失败: {str(e)}"},
            status_code=400,
        )
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"公式识图失败: {str(e)}"},
            status_code=500
        )
    finally:
        for path in created_crops:
            try:
                dependencies.os.remove(path)
            except OSError:
                pass
        # 确保清理临时文件
        if temp_filepath and dependencies.os.path.exists(temp_filepath):
            try:
                dependencies.os.remove(temp_filepath)
            except Exception as e_cleanup:
                print(f"[OCR Flow Cleanup Error] 无法删除临时文件 {temp_filepath}: {str(e_cleanup)}")


def ocr_pdf_page_image(image_path: str, *, check_cancelled=lambda: None,
                       report_attempt=lambda _event: None, page_index=None, on_response=None,
                       dependencies: OcrServiceDependencies) -> str:
    """Use the selected provider once; no paid retry or silent fallback."""
    check_cancelled()
    provider = dependencies.resolve_ocr_provider(dependencies.os.getenv('OCR_PREFER_ENGINE', 'siliconflow'))
    if not provider.api_key or not provider.chat_completions_url:
        raise dependencies.OCRConfigurationError('PDF 页面识别服务未配置，请在 API 设置中填写所选平台。')
    return dependencies.ocr_via_provider(image_path, provider, pdf_page=True,
        check_cancelled=check_cancelled, report_attempt=report_attempt, page_index=page_index,
        on_response=on_response)
