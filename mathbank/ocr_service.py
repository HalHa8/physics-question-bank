"""Ocr service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import UploadFile, File, Form
from mathbank.ai_providers import MultimodalProviderConfig


@dataclass(frozen=True)
class OcrServiceDependencies:
    state: RuntimeState
    COMMON_OCR_PROMPT: Any
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


def ocr_via_provider(image_path: str, provider: MultimodalProviderConfig, include_illustration_box: bool=False, *, dependencies: OcrServiceDependencies) -> str:
    """Use one resolved multimodal provider for formula and text OCR."""
    import base64

    if not provider.supports_image_input:
        raise ValueError(
            f"{provider.provider_label} 模型 {provider.model_name} 不支持图像输入，"
            "请在默认公式识图模型中选择支持图片的模型。"
        )

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
        prompt += dependencies.ILLUSTRATION_BOX_PROMPT

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

    timeout = 240
    # Chat-completion POSTs are not idempotent: a read timeout can happen after
    # the provider has accepted (and billed) the request.  Do not automatically
    # send the same image two or three times.  The shared transport still
    # retries a connection-establishment failure where no response was read.
    response = dependencies.post_chat_completion(
        provider,
        payload,
        timeout=timeout,
        check_status=False,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"{provider.provider_label} API 识别失败: HTTP {response.status_code}"
        )

    res_json = response.json()
    try:
        choices = res_json.get("choices", [])
        if choices and len(choices) > 0:
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
    try:
        # OCR route is synchronous and runs in FastAPI's worker pool.  Stream
        # only up to the endpoint cap, then fully decode/re-encode the image.
        file_bytes = dependencies.read_stream_limited(file.file, dependencies.MAX_OCR_IMAGE_BYTES)
        normalized = dependencies.normalize_raster_image(file_bytes)
        image = dependencies.Image.open(dependencies.io.BytesIO(normalized.data)).convert("RGB")

        # 1. 运行自适应图像去噪/自动切边预处理
        image = dependencies.auto_crop_image(image)

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

        # 成功，返回且进一步清洗
        if latex_content:
            # 过滤干扰字符
            latex_content = latex_content.replace("\\,", "").replace("\\!", "")
            # 自动清洗规范化下划线/连续划线/任何 \underline 变体为标准的 \fillin 宏
            latex_content = dependencies.normalize_fillin_macro(latex_content)

        # ----------------- 双阶段多模态识图与高级 TikZ 绘图模型联动 -----------------
        tikz_code_from_high_model = None
        tikz_image_path = None

        if latex_content:
            import re
            # 提取可能由默认模型标注的示意图 Bounding Box 标记
            box_match = re.search(r"\[ILLUSTRATION_BOX:\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", latex_content, re.IGNORECASE)
            if box_match:
                # 第一步先确保擦除标记，防止乱入题干文本框
                latex_content = re.sub(r"\[ILLUSTRATION_BOX:.*?\]", "", latex_content).strip()

                if not skip_tikz:
                    try:
                        # 不再执行物理分割裁剪，直接将整张原始题目截图发送给高级视觉绘图模型进行图形分析与重画
                        prefer_draw = dependencies.os.getenv("PREFER_DRAW_MODEL", "Qwen/Qwen3-VL-32B-Instruct")
                        print(f"[Illustration Draw] 检测到插图标记，直接将整张原图送往高级模型 {prefer_draw} 进行 TikZ 解析绘图...")

                        tikz_code_from_high_model = dependencies.draw_tikz_via_high_model(
                            temp_filepath, # 传入整图
                            prefer_draw,
                            latex_content=latex_content
                        )
                    except Exception as draw_err:
                        print(f"[Illustration Draw Fail] 高级多模态模型整图分析绘图失败: {str(draw_err)}")
                else:
                    print("[Illustration Draw] 检测到插图标记，但由于已勾选跳过，故未调用高级绘图模型进行 TikZ 绘制")
            else:
                # 剔除可能存在的由于大模型幻觉或者部分输出造成的残缺标记
                latex_content = re.sub(r"\[ILLUSTRATION_BOX:.*?\]", "", latex_content).strip()

            # Remove OCR protocol markers before repairing naked math. Otherwise
            # the underscore in ILLUSTRATION_BOX can be mistaken for a subscript
            # and leave behind an empty ``$$`` pair after marker cleanup.
            latex_content = dependencies.normalize_question_math_markdown(latex_content)

        # 如果高级模型成功生成了 TikZ 代码，我们在后台自动进行编译预览，并格式化追加到 latex 文本中！
        if tikz_code_from_high_model:
            try:
                print(f"[Illustration Draw] 高级绘图模型成功输出 TikZ 源码！正在开始编译为预览图...")
                compiled_path = dependencies.compile_tikz_to_png(tikz_code_from_high_model)
                if compiled_path:
                    tikz_image_path = compiled_path
                    # 自动在题干文本的尾部追加 Markdown 插图引用
                    latex_content += f"\n\n![]({compiled_path})"
                    print(f"[Illustration Draw] 编译成功: {compiled_path}")
            except Exception as compile_err:
                print(f"[Illustration Draw] 编译高级模型生成的 TikZ 失败: {str(compile_err)}")

        # 将 temp_filepath 置为 None，避免在 finally 块中被删除
        saved_filepath = temp_filepath
        temp_filepath = None

        return {
            "status": "success",
            "latex": latex_content,
            "confidence": confidence,
            "provider": provider,
            "image_path": f"/{dependencies.state.UPLOAD_DIR_REL}/{dependencies.os.path.basename(saved_filepath)}",
            "tikz_code": tikz_code_from_high_model,
            "tikz_image_path": tikz_image_path
        }
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
        # 确保清理临时文件
        if temp_filepath and dependencies.os.path.exists(temp_filepath):
            try:
                dependencies.os.remove(temp_filepath)
            except Exception as e_cleanup:
                print(f"[OCR Flow Cleanup Error] 无法删除临时文件 {temp_filepath}: {str(e_cleanup)}")


def ocr_pdf_page_image(image_path: str, *, dependencies: OcrServiceDependencies) -> str:
    """自动选择已配置的 VLM 识别引擎进行单页识别，支持故障转移（Fallback）与兜底识别"""
    errors = []
    prefer_engine = dependencies.os.getenv("OCR_PREFER_ENGINE", "siliconflow")
    providers_to_try = dependencies.resolve_ocr_fallbacks(prefer_engine)

    if not providers_to_try:
        raise dependencies.OCRConfigurationError("未配置任何识图 Key，请在系统设置中配置所选识图平台的 DeepSeek、硅基流动、阿里百炼或中转站 API 密钥。")

    for ocr_provider in providers_to_try:
        label = ocr_provider.provider_label
        try:
            print(f"[PDF OCR Flow] 正在尝试调用识图引擎: {label}...")
            return dependencies.ocr_via_provider(image_path, ocr_provider)
        except dependencies.requests.exceptions.ReadTimeout as e_single:
            # The first provider may already have accepted the image.  Sending
            # it immediately to another provider can create a duplicate bill.
            raise RuntimeError(
                f"{label} 读取超时，请求是否已被处理尚不确定。"
                "为避免重复计费，本次未自动切换到下一家模型，请稍后手动重试。"
            ) from e_single
        except Exception as e_single:
            err_msg = f"{label} 出错: {str(e_single)}"
            print(f"[PDF OCR Flow Warning] {err_msg}")
            errors.append(err_msg)

    # 如果全部都失败了，抛出包含所有尝试错误细节的汇总异常
    raise RuntimeError("所有配置的识图引擎均尝试失败。详情:\n" + "\n".join(errors))
