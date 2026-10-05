"""Drawing service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from typing import Optional
from fastapi import UploadFile, File, Form, Header


@dataclass(frozen=True)
class DrawingServiceDependencies:
    state: RuntimeState
    AssetSecurityError: Any
    HTTPException: Any
    InvalidImageError: Any
    MAX_SINGLE_IMAGE_BYTES: Any
    Optional: Any
    Path: Any
    UploadTooLargeError: Any
    apply_model_thinking_policy: Any
    build_restricted_tex_environment: Any
    build_tikz_correction_prompt: Any
    build_tikz_draw_prompt: Any
    compile_tikz_to_png: Callable
    draw_tikz_via_high_model: Callable
    extract_tikz_source: Callable
    normalize_raster_image: Any
    normalize_upload_asset_reference: Any
    os: Any
    post_chat_completion: Any
    re: Any
    read_stream_limited: Any
    request_tikz_completion: Callable
    resolve_draw_provider: Any
    resolve_upload_asset: Any
    secrets: Any
    uuid: Any


def extract_tikz_source(ai_message: str, *, dependencies: DrawingServiceDependencies) -> str:
    """Extract one complete TikZ environment from a model response."""

    message = str(ai_message or "").strip()
    match = dependencies.re.search(
        r"\\begin\s*\{\s*tikzpicture\s*\}.*?\\end\s*\{\s*tikzpicture\s*\}",
        message,
        dependencies.re.DOTALL | dependencies.re.IGNORECASE,
    )
    if match:
        return match.group(0).strip()

    match_block = dependencies.re.search(
        r"```(?:latex|tex)?\s*(.*?)```",
        message,
        dependencies.re.DOTALL | dependencies.re.IGNORECASE,
    )
    if match_block:
        code = match_block.group(1).strip()
        if code and "tikzpicture" not in code.lower():
            return f"\\begin{{tikzpicture}}\n{code}\n\\end{{tikzpicture}}"

    raise RuntimeError("绘图模型未返回完整的 tikzpicture 源码。")


def request_tikz_completion(provider, content_payload, *, timeout: int=120, dependencies: DrawingServiceDependencies) -> str:
    """Send one TikZ model request with the shared reasoning and parser policy."""

    payload = {
        "model": provider.model_name,
        "messages": [{"role": "user", "content": content_payload}],
        "stream": False,
    }
    payload = dependencies.apply_model_thinking_policy(
        payload,
        provider=provider,
        task="draw",
    )
    response = dependencies.post_chat_completion(
        provider,
        payload,
        timeout=timeout,
        check_status=False,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"{provider.provider_label} 绘图接口返回 HTTP {response.status_code}"
        )
    choices = response.json().get("choices", [])
    if not choices:
        raise RuntimeError(f"{provider.provider_label} 绘图接口未返回 choices。")
    ai_message = choices[0].get("message", {}).get("content", "")
    return dependencies.extract_tikz_source(ai_message)


def draw_tikz_via_high_model(image_path: Optional[str], prefer_draw: str, latex_content: Optional[str]=None, *, instruction: str='', existing_tikz: str='', require_image_support: bool=False, dependencies: DrawingServiceDependencies) -> Optional[str]:
    """使用指定的高级绘图模型（多模态或纯文本自适应）生成 TikZ 代码。"""
    import base64
    provider = dependencies.resolve_draw_provider(prefer_draw)
    if not provider.api_key:
        print(
            f"[High Model Draw] 未配置 {provider.credential_label}，降级跳过。"
        )
        return None

    has_reference_image = bool(image_path)
    if has_reference_image and require_image_support and not provider.supports_image_input:
        raise RuntimeError(
            f"当前绘图模型 {provider.model_name} 不支持参考图输入，"
            "请在 API 设置中选择支持图像的 TikZ 绘图模型。"
        )
    use_image_input = has_reference_image and provider.supports_image_input

    if use_image_input:
        # 多模态图文输入模式
        try:
            with open(image_path, "rb") as f:
                encoded_image = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"[High Model Draw] 读取裁剪小图 Base64 失败: {str(e)}")
            return None

        suffix = dependencies.Path(image_path).suffix.lower()
        image_media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(suffix, "image/png")
        prompt = dependencies.build_tikz_draw_prompt(
            latex_content,
            multimodal=True,
            instruction=instruction,
            existing_tikz=existing_tikz,
        )

        content_payload = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_media_type};base64,{encoded_image}"
                }
            }
        ]
    else:
        # 纯文本推理模式。带有视觉能力的模型也可以在没有参考图时走此分支。
        if not any((latex_content, instruction, existing_tikz)):
            print("[High Model Draw] 绘图模型未获得任何可用输入，跳过。")
            return None

        prompt = dependencies.build_tikz_draw_prompt(
            latex_content,
            multimodal=False,
            instruction=instruction,
            existing_tikz=existing_tikz,
        )
        content_payload = prompt

    try:
        return dependencies.request_tikz_completion(
            provider,
            content_payload,
            timeout=120,
        )
    except Exception as e:
        print(f"[High Model Draw Error] 大模型请求发生异常: {str(e)}")
    return None


def compile_tikz_to_png(tikz_code: str, *, dependencies: DrawingServiceDependencies) -> str:
    """
    编译 TikZ 代码为 PNG 并存放在静态资源目录中。
    如果编译成功，返回相对路径（如 /static/uploads/tikz_xxx.png）。
    如果编译失败，抛出 Exception 详细说明原因。
    """
    import shutil
    import uuid
    import subprocess
    import os
    import platform

    # 1. 检查 xelatex
    # macOS 特有处理：如果系统是 macOS 且标准 MacTeX 路径存在，确保其在 PATH 中，防止 GUI/后台进程环境变量丢失
    if platform.system() == "Darwin":
        mactex_bin = "/Library/TeX/texbin"
        if os.path.exists(mactex_bin) and mactex_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = os.environ.get("PATH", "") + os.path.pathsep + mactex_bin

    if not shutil.which("xelatex"):
        raise RuntimeError("系统未检测到 'xelatex' 编译器。请确保您的系统已安装 MacTeX/TeX Live 并将其加入 PATH。")

    # 2. 检查 PyMuPDF
    try:
        import pymupdf as fitz
    except ImportError:
        raise RuntimeError("Python 环境中未安装 'pymupdf'，无法将 PDF 转换为图像，请运行 'pip install pymupdf' 安装。")

    # 3. 创建临时文件夹
    temp_dir = os.path.join(dependencies.state.UPLOAD_DIR, ".tikz_temp")
    os.makedirs(temp_dir, exist_ok=True)

    unique_id = uuid.uuid4().hex
    tex_path = os.path.join(temp_dir, f"{unique_id}.tex")
    pdf_path = os.path.join(temp_dir, f"{unique_id}.pdf")
    png_path = os.path.join(temp_dir, f"{unique_id}.png")
    aux_path = os.path.join(temp_dir, f"{unique_id}.aux")
    log_path = os.path.join(temp_dir, f"{unique_id}.log")

    # 拼装完整的 TeX 模板
    tex_content = f"""\\documentclass[tikz, border=2mm]{{standalone}}
\\usepackage{{ctex}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{tikz}}
\\usepackage{{pgfplots}}
\\pgfplotsset{{compat=1.16}}
\\usetikzlibrary{{patterns}}
\\usetikzlibrary{{calc,positioning,intersections,arrows}}
\\usetikzlibrary{{shapes.geometric,through,decorations.pathmorphing,arrows.meta,quotes,mindmap,shapes.symbols,shapes.arrows,automata,angles,3d,trees,shadows,shapes.callouts,decorations.pathreplacing,decorations.markings}}
\\begin{{document}}
{tikz_code}
\\end{{document}}"""

    try:
        # 写入临时 tex 文件
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)

        # 调用 xelatex 编译
        result = subprocess.run(
            [
                "xelatex",
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-output-directory=.",
                os.path.basename(tex_path),
            ],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            env=dependencies.build_restricted_tex_environment(temp_dir),
        )

        if result.returncode != 0:
            # 尝试提取编译错误原因
            log_content = ""
            if os.path.exists(log_path):
                try:
                    with open(log_path, "rb") as lf:
                        raw_log = lf.read()
                        try:
                            log_text = raw_log.decode("utf-8")
                        except UnicodeDecodeError:
                            log_text = raw_log.decode("gbk", errors="replace")
                        lines = log_text.splitlines()
                        # 找到包含 ! 的报错行
                        error_lines = [line.strip() for line in lines if line.startswith("!")]
                        if error_lines:
                            log_content = "\n".join(error_lines[:3])
                except Exception:
                    pass
            error_msg = log_content if log_content else "LaTeX 语法错误，编译失败。"
            raise RuntimeError(f"编译错误: {error_msg}")

        if not os.path.exists(pdf_path):
            raise RuntimeError("编译未生成 PDF 文件。")

        # 使用 PyMuPDF 将 PDF 转换成 PNG，并确保异常路径也会关闭文档。
        with fitz.open(pdf_path) as doc:
            if len(doc) == 0:
                raise RuntimeError("生成的 PDF 文件为空。")
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            pix.save(png_path)

        if not os.path.exists(png_path):
            raise RuntimeError("PDF 转换 PNG 失败。")

        # 将最终生成的图片拷贝到 uploads 目录下
        final_filename = f"tikz_{unique_id}.png"
        final_dest = os.path.join(dependencies.state.UPLOAD_DIR, final_filename)
        shutil.copy2(png_path, final_dest)

        # 返回相对路径
        return f"/{dependencies.state.UPLOAD_DIR_REL}/{final_filename}"

    except subprocess.TimeoutExpired:
        raise RuntimeError("编译超时 (15秒)，可能是您的 TikZ 绘图循环出现了死循环。")
    except Exception as e:
        raise RuntimeError(str(e))
    finally:
        # 清理临时文件
        for temp_file in [tex_path, pdf_path, png_path, aux_path, log_path]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass


def render_tikz_endpoint(tikz_code: str=Form(...), *, dependencies: DrawingServiceDependencies):
    """接收 TikZ 代码并编译成静态 PNG，返回其相对路径"""
    try:
        image_path = dependencies.compile_tikz_to_png(tikz_code)
        return {"status": "success", "image_path": image_path}
    except Exception as e:
        raise dependencies.HTTPException(status_code=400, detail=str(e))


def correct_tikz_endpoint(tikz_code: str=Form(...), original_image_path: str=Form(...), user_prompt: str=Form(None), *, dependencies: DrawingServiceDependencies):
    """利用用户指定的高级绘图模型进行 TikZ 纠错，支持人工指导意见注入"""
    import base64

    # 动态读取高级绘图模型配置
    prefer_draw = dependencies.os.getenv("PREFER_DRAW_MODEL", "Qwen/Qwen3-VL-32B-Instruct")
    draw_provider = dependencies.resolve_draw_provider(prefer_draw)
    if not draw_provider.api_key:
        raise dependencies.HTTPException(
            status_code=400,
            detail=(
                f"未配置 {draw_provider.credential_label}！"
                "请在设置面板中配置后重试。"
            ),
        )
    print(
        f"[TikZ Correction] 启用 {draw_provider.provider_label} 高级模型进行纠错: "
        f"{draw_provider.model_name}, Base URL: {draw_provider.chat_completions_url}"
    )

    # 对原始截图进行 Base64 编码
    try:
        clean_original_path = dependencies.resolve_upload_asset(
            original_image_path,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
        )
    except dependencies.AssetSecurityError as exc:
        raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with open(clean_original_path, "rb") as f:
            encoded_original = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        raise dependencies.HTTPException(status_code=400, detail=f"读取原始图片失败: {str(e)}")

    # 尝试编译当前的 TikZ 代码
    rendered_image_path = None
    compile_error_log = None
    try:
        rendered_image_path = dependencies.compile_tikz_to_png(tikz_code)
    except Exception as e:
        compile_error_log = str(e)

    # 视觉比对模式（编译成功，获取到两张图）
    if rendered_image_path:
        try:
            clean_rendered_path = dependencies.resolve_upload_asset(
                rendered_image_path,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            )
        except dependencies.AssetSecurityError as exc:
            raise dependencies.HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            with open(clean_rendered_path, "rb") as f:
                encoded_rendered = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            raise dependencies.HTTPException(status_code=400, detail=f"读取渲染出的 TikZ 图片失败: {str(e)}")

        prompt = dependencies.build_tikz_correction_prompt(
            tikz_code,
            user_guidance=user_prompt,
            rendered_comparison=True,
        )

        content_payload = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{encoded_original}"
                }
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{encoded_rendered}"
                }
            }
        ]

        # 临时创建的渲染图在使用后也可以删除，以节省磁盘
        try:
            clean_rendered_path.unlink()
        except Exception:
            pass

    # 报错自愈模式（编译失败，只有原始图 + 报错日志）
    else:
        prompt = dependencies.build_tikz_correction_prompt(
            tikz_code,
            user_guidance=user_prompt,
            compile_error_log=compile_error_log,
            rendered_comparison=False,
        )

        content_payload = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{encoded_original}"
                }
            }
        ]

    try:
        corrected_code = dependencies.request_tikz_completion(
            draw_provider,
            content_payload,
            timeout=90,
        )
        return {
            "status": "success",
            "corrected_code": corrected_code,
            "mode": "visual_diff" if rendered_image_path else "error_recovery"
        }
    except Exception as e:
        raise dependencies.HTTPException(status_code=400, detail=f"AI 纠错请求失败: {str(e)}")


def draw_tikz_workbench_endpoint(instruction: str=Form(''), context: str=Form(''), existing_tikz: str=Form(''), reference_image_path: str=Form(''), reference_image: Optional[UploadFile]=File(None), *, dependencies: DrawingServiceDependencies):
    """从文字、参考图或已有源码生成/修改 TikZ，供手动录题工作台使用。"""

    instruction = (instruction or "").strip()
    context = (context or "").strip()
    existing_tikz = (existing_tikz or "").strip()
    reference_image_path = (reference_image_path or "").strip()
    has_uploaded_reference = bool(reference_image and reference_image.filename)
    has_reference = has_uploaded_reference or bool(reference_image_path)
    if not instruction and not existing_tikz and not has_reference:
        raise dependencies.HTTPException(status_code=400, detail="请输入绘图要求、上传参考图或提供已有 TikZ 源码。")
    if len(instruction) > 4000:
        raise dependencies.HTTPException(status_code=400, detail="绘图要求不能超过 4000 个字符。")
    if len(context) > 30000:
        raise dependencies.HTTPException(status_code=400, detail="绘图上下文不能超过 30000 个字符。")
    if len(existing_tikz) > 200000:
        raise dependencies.HTTPException(status_code=400, detail="TikZ 源码不能超过 200000 个字符。")

    reference_path: dependencies.Optional[dependencies.Path] = None
    temporary_reference_path: dependencies.Optional[dependencies.Path] = None
    persisted_reference_url = ""
    try:
        if has_uploaded_reference:
            raw = dependencies.read_stream_limited(reference_image.file, dependencies.MAX_SINGLE_IMAGE_BYTES)
            normalized = dependencies.normalize_raster_image(raw)
            temporary_reference_path = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR) / (
                f"tikz_reference_{dependencies.uuid.uuid4().hex}{normalized.extension}"
            )
            temporary_reference_path.write_bytes(normalized.data)
            reference_path = temporary_reference_path
        elif reference_image_path:
            normalized_reference = dependencies.normalize_upload_asset_reference(
                reference_image_path,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            )
            reference_path = dependencies.resolve_upload_asset(
                normalized_reference,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            )
            persisted_reference_url = normalized_reference

        prefer_draw = (
            dependencies.os.getenv("PREFER_DRAW_MODEL")
            or dependencies.os.getenv("PREFER_PARSE_MODEL")
            or "Qwen/Qwen3-VL-32B-Instruct"
        )
        tikz_code = dependencies.draw_tikz_via_high_model(
            str(reference_path) if reference_path else None,
            prefer_draw,
            latex_content=context,
            instruction=instruction,
            existing_tikz=existing_tikz,
            require_image_support=has_reference,
        )
        if not tikz_code:
            raise RuntimeError(
                "TikZ 绘图模型未返回可用源码，请检查绘图模型与 API 密钥设置。"
            )
        if temporary_reference_path is not None:
            persisted_name = (
                f"tikz_reference_{dependencies.uuid.uuid4().hex}"
                f"{temporary_reference_path.suffix.lower()}"
            )
            persisted_path = dependencies.Path(dependencies.state.UPLOAD_DIR) / persisted_name
            temporary_reference_path.replace(persisted_path)
            temporary_reference_path = None
            persisted_reference_url = f"/{dependencies.state.UPLOAD_DIR_REL}/{persisted_name}"
        return {
            "status": "success",
            "tikz_code": tikz_code,
            "used_reference_image": has_reference,
            "reference_image_path": persisted_reference_url,
        }
    except dependencies.UploadTooLargeError as exc:
        raise dependencies.HTTPException(status_code=413, detail="参考图不能超过 10MB。") from exc
    except dependencies.InvalidImageError as exc:
        raise dependencies.HTTPException(status_code=400, detail=f"参考图无效: {str(exc)}") from exc
    except dependencies.HTTPException:
        raise
    except Exception as exc:
        raise dependencies.HTTPException(status_code=400, detail=f"AI TikZ 绘图失败: {str(exc)}") from exc
    finally:
        if temporary_reference_path is not None:
            try:
                temporary_reference_path.unlink(missing_ok=True)
            except OSError:
                pass


def draw_tikz_from_image_endpoint(image_path: str=Form(...), latex_content: str=Form(None), x_local_token: str=Header(None, alias='X-Local-Token'), *, dependencies: DrawingServiceDependencies):
    """根据指定的题目图片，调用高级多模态模型生成对应的 LaTeX TikZ 代码"""
    # Middleware already enforces this header for HTTP calls.  Keep the direct
    # function guard tied to the same single token source for test/internal use.
    if not x_local_token or not dependencies.secrets.compare_digest(x_local_token, dependencies.state.LOCAL_TOKEN):
        raise dependencies.HTTPException(status_code=401, detail="Unauthorized")

    try:
        physical_path = dependencies.resolve_upload_asset(
            image_path,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
        )
    except dependencies.AssetSecurityError as exc:
        raise dependencies.HTTPException(status_code=404, detail=str(exc)) from exc

    # 动态读取绘图高级模型配置
    prefer_draw = dependencies.os.getenv("PREFER_DRAW_MODEL") or dependencies.os.getenv("PREFER_PARSE_MODEL") or "Qwen/Qwen3-VL-32B-Instruct"

    try:
        print(f"[API Draw TikZ] 正在调用高级模型 {prefer_draw} 对插图 {image_path} 进行多模态 TikZ 绘图分析...")
        tikz_code = dependencies.draw_tikz_via_high_model(
            physical_path,
            prefer_draw,
            latex_content=latex_content
        )

        if not tikz_code:
            raise RuntimeError(f"多模态高级模型 {prefer_draw} 未能生成有效的 TikZ 代码")

        return {
            "status": "success",
            "tikz_code": tikz_code
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise dependencies.HTTPException(status_code=400, detail=f"AI 识图绘图失败: {str(e)}")
