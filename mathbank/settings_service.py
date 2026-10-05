"""Settings service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Form


@dataclass(frozen=True)
class SettingsServiceDependencies:
    state: RuntimeState
    ENV_FILE: Any
    JSONResponse: Any
    os: Any
    write_private_text_atomic: Any


def get_settings(*, dependencies: SettingsServiceDependencies):
    ds_key = dependencies.os.getenv("DEEPSEEK_API_KEY", "")
    sf_key = dependencies.os.getenv("SILICONFLOW_API_KEY", "")
    ali_key = dependencies.os.getenv("ALI_BAILIAN_API_KEY", "")

    # 兼容老版 ZHONGZHAN 环境变量
    zz_gpt_key = dependencies.os.getenv("ZHONGZHAN_GPT_API_KEY") or dependencies.os.getenv("ZHONGZHAN_API_KEY", "")
    zz_gpt_base = dependencies.os.getenv("ZHONGZHAN_GPT_BASE_URL") or dependencies.os.getenv("ZHONGZHAN_BASE_URL", "")
    zz_gpt_ocr_model = dependencies.os.getenv("ZHONGZHAN_GPT_OCR_MODEL") or dependencies.os.getenv("ZHONGZHAN_OCR_MODEL", "gpt-4o")

    zz_claude_key = dependencies.os.getenv("ZHONGZHAN_CLAUDE_API_KEY", "")
    zz_claude_base = dependencies.os.getenv("ZHONGZHAN_CLAUDE_BASE_URL", "")
    zz_claude_ocr_model = dependencies.os.getenv("ZHONGZHAN_CLAUDE_OCR_MODEL", "claude-3-5-sonnet")

    prefer_engine = dependencies.os.getenv("OCR_PREFER_ENGINE", "siliconflow")
    ds_model = dependencies.os.getenv("DEEPSEEK_OCR_MODEL") or "deepseek-flash"
    sf_model = dependencies.os.getenv("SILICONFLOW_OCR_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
    ali_model = dependencies.os.getenv("ALI_BAILIAN_OCR_MODEL", "qwen3.7-flash")
    prefer_solve_model = dependencies.os.getenv("PREFER_SOLVE_MODEL", "deepseek-v4-pro")
    prefer_parse_model = dependencies.os.getenv("PREFER_PARSE_MODEL", "deepseek-flash")
    prefer_classify_model = dependencies.os.getenv("PREFER_CLASSIFY_MODEL") or dependencies.os.getenv("DEEPSEEK_CLASSIFY_MODEL", "deepseek-flash")
    prefer_draw_model = dependencies.os.getenv("PREFER_DRAW_MODEL", "Qwen/Qwen3-VL-32B-Instruct")

    masked_ds = ""
    if ds_key:
        masked_ds = ds_key[:4] + "••••" + ds_key[-4:] if len(ds_key) > 8 else "••••••••"

    masked_sf = ""
    if sf_key:
        masked_sf = sf_key[:4] + "••••" + sf_key[-4:] if len(sf_key) > 8 else "••••••••"

    masked_ali = ""
    if ali_key:
        masked_ali = ali_key[:4] + "••••" + ali_key[-4:] if len(ali_key) > 8 else "••••••••"

    masked_zz_gpt = ""
    if zz_gpt_key:
        masked_zz_gpt = zz_gpt_key[:4] + "••••" + zz_gpt_key[-4:] if len(zz_gpt_key) > 8 else "••••••••"

    masked_zz_claude = ""
    if zz_claude_key:
        masked_zz_claude = zz_claude_key[:4] + "••••" + zz_claude_key[-4:] if len(zz_claude_key) > 8 else "••••••••"

    return {
        "deepseek_key": masked_ds,
        "siliconflow_key": masked_sf,
        "ali_bailian_key": masked_ali,
        "zhongzhan_gpt_key": masked_zz_gpt,
        "zhongzhan_gpt_base_url": zz_gpt_base,
        "zhongzhan_gpt_ocr_model": zz_gpt_ocr_model,
        "zhongzhan_claude_key": masked_zz_claude,
        "zhongzhan_claude_base_url": zz_claude_base,
        "zhongzhan_claude_ocr_model": zz_claude_ocr_model,
        "prefer_engine": prefer_engine,
        "deepseek_model": ds_model,
        "siliconflow_model": sf_model,
        "ali_bailian_model": ali_model,
        "prefer_solve_model": prefer_solve_model,
        "prefer_parse_model": prefer_parse_model,
        "prefer_classify_model": prefer_classify_model,
        "prefer_draw_model": prefer_draw_model
    }


def save_settings(deepseek_key: str=Form(''), siliconflow_key: str=Form(''), ali_bailian_key: str=Form(''), zhongzhan_gpt_key: str=Form(''), zhongzhan_gpt_base_url: str=Form(''), zhongzhan_gpt_ocr_model: str=Form(''), zhongzhan_claude_key: str=Form(''), zhongzhan_claude_base_url: str=Form(''), zhongzhan_claude_ocr_model: str=Form(''), prefer_engine: str=Form('siliconflow'), deepseek_model: str | None=Form(None), siliconflow_model: str=Form('Qwen/Qwen3-VL-8B-Instruct'), ali_bailian_model: str=Form('qwen3.7-flash'), prefer_solve_model: str=Form('deepseek-v4-pro'), prefer_parse_model: str=Form('deepseek-flash'), prefer_classify_model: str=Form('deepseek-flash'), prefer_draw_model: str=Form('Qwen/Qwen3-VL-32B-Instruct'), *, dependencies: SettingsServiceDependencies):
    try:
        # Older clients and other OCR providers may omit this new field.
        deepseek_model = deepseek_model or dependencies.os.getenv("DEEPSEEK_OCR_MODEL") or "deepseek-flash"
        settings_values = {
            "deepseek_key": deepseek_key,
            "siliconflow_key": siliconflow_key,
            "ali_bailian_key": ali_bailian_key,
            "zhongzhan_gpt_key": zhongzhan_gpt_key,
            "zhongzhan_gpt_base_url": zhongzhan_gpt_base_url,
            "zhongzhan_gpt_ocr_model": zhongzhan_gpt_ocr_model,
            "zhongzhan_claude_key": zhongzhan_claude_key,
            "zhongzhan_claude_base_url": zhongzhan_claude_base_url,
            "zhongzhan_claude_ocr_model": zhongzhan_claude_ocr_model,
            "prefer_engine": prefer_engine,
            "deepseek_model": deepseek_model,
            "siliconflow_model": siliconflow_model,
            "ali_bailian_model": ali_bailian_model,
            "prefer_solve_model": prefer_solve_model,
            "prefer_parse_model": prefer_parse_model,
            "prefer_classify_model": prefer_classify_model,
            "prefer_draw_model": prefer_draw_model,
        }
        if any("\r" in value or "\n" in value for value in settings_values.values()):
            raise ValueError("配置值不能包含换行符。")

        # If masked, preserve current key
        if "••••" in deepseek_key:
            deepseek_key = dependencies.os.getenv("DEEPSEEK_API_KEY", "")
        if "••••" in siliconflow_key:
            siliconflow_key = dependencies.os.getenv("SILICONFLOW_API_KEY", "")
        if "••••" in ali_bailian_key:
            ali_bailian_key = dependencies.os.getenv("ALI_BAILIAN_API_KEY", "")
        if "••••" in zhongzhan_gpt_key:
            zhongzhan_gpt_key = dependencies.os.getenv("ZHONGZHAN_GPT_API_KEY") or dependencies.os.getenv("ZHONGZHAN_API_KEY", "")
        if "••••" in zhongzhan_claude_key:
            zhongzhan_claude_key = dependencies.os.getenv("ZHONGZHAN_CLAUDE_API_KEY", "")

        # Read current .env
        env_lines = []
        if dependencies.ENV_FILE.exists():
            with dependencies.ENV_FILE.open("r", encoding="utf-8") as f:
                env_lines = f.readlines()

        keys_replaced = {
            "DEEPSEEK_API_KEY": False,
            "DEEPSEEK_OCR_MODEL": False,
            "SILICONFLOW_API_KEY": False,
            "ALI_BAILIAN_API_KEY": False,
            "ZHONGZHAN_GPT_API_KEY": False,
            "ZHONGZHAN_GPT_BASE_URL": False,
            "ZHONGZHAN_GPT_OCR_MODEL": False,
            "ZHONGZHAN_CLAUDE_API_KEY": False,
            "ZHONGZHAN_CLAUDE_BASE_URL": False,
            "ZHONGZHAN_CLAUDE_OCR_MODEL": False,
            "OCR_PREFER_ENGINE": False,
            "SILICONFLOW_OCR_MODEL": False,
            "ALI_BAILIAN_OCR_MODEL": False,
            "PREFER_SOLVE_MODEL": False,
            "PREFER_PARSE_MODEL": False,
            "PREFER_CLASSIFY_MODEL": False,
            "PREFER_DRAW_MODEL": False
        }
        new_lines = []

        for line in env_lines:
            line_strip = line.strip()
            # Skip old Pix2Text settings to clean .env
            if line_strip.startswith("PIX2TEXT_API_KEY=") or line_strip.startswith("PIX2TEXT_SERVER_TYPE="):
                continue

            if line_strip.startswith("DEEPSEEK_API_KEY="):
                new_lines.append(f"DEEPSEEK_API_KEY={deepseek_key}\n")
                keys_replaced["DEEPSEEK_API_KEY"] = True
            elif line_strip.startswith("DEEPSEEK_OCR_MODEL="):
                new_lines.append(f"DEEPSEEK_OCR_MODEL={deepseek_model}\n")
                keys_replaced["DEEPSEEK_OCR_MODEL"] = True
            elif line_strip.startswith("SILICONFLOW_API_KEY="):
                new_lines.append(f"SILICONFLOW_API_KEY={siliconflow_key}\n")
                keys_replaced["SILICONFLOW_API_KEY"] = True
            elif line_strip.startswith("ALI_BAILIAN_API_KEY="):
                new_lines.append(f"ALI_BAILIAN_API_KEY={ali_bailian_key}\n")
                keys_replaced["ALI_BAILIAN_API_KEY"] = True
            elif line_strip.startswith("ZHONGZHAN_GPT_API_KEY="):
                new_lines.append(f"ZHONGZHAN_GPT_API_KEY={zhongzhan_gpt_key}\n")
                keys_replaced["ZHONGZHAN_GPT_API_KEY"] = True
            elif line_strip.startswith("ZHONGZHAN_GPT_BASE_URL="):
                new_lines.append(f"ZHONGZHAN_GPT_BASE_URL={zhongzhan_gpt_base_url}\n")
                keys_replaced["ZHONGZHAN_GPT_BASE_URL"] = True
            elif line_strip.startswith("ZHONGZHAN_GPT_OCR_MODEL="):
                new_lines.append(f"ZHONGZHAN_GPT_OCR_MODEL={zhongzhan_gpt_ocr_model}\n")
                keys_replaced["ZHONGZHAN_GPT_OCR_MODEL"] = True
            elif line_strip.startswith("ZHONGZHAN_CLAUDE_API_KEY="):
                new_lines.append(f"ZHONGZHAN_CLAUDE_API_KEY={zhongzhan_claude_key}\n")
                keys_replaced["ZHONGZHAN_CLAUDE_API_KEY"] = True
            elif line_strip.startswith("ZHONGZHAN_CLAUDE_BASE_URL="):
                new_lines.append(f"ZHONGZHAN_CLAUDE_BASE_URL={zhongzhan_claude_base_url}\n")
                keys_replaced["ZHONGZHAN_CLAUDE_BASE_URL"] = True
            elif line_strip.startswith("ZHONGZHAN_CLAUDE_OCR_MODEL="):
                new_lines.append(f"ZHONGZHAN_CLAUDE_OCR_MODEL={zhongzhan_claude_ocr_model}\n")
                keys_replaced["ZHONGZHAN_CLAUDE_OCR_MODEL"] = True
            elif line_strip.startswith("OCR_PREFER_ENGINE="):
                new_lines.append(f"OCR_PREFER_ENGINE={prefer_engine}\n")
                keys_replaced["OCR_PREFER_ENGINE"] = True
            elif line_strip.startswith("SILICONFLOW_OCR_MODEL="):
                new_lines.append(f"SILICONFLOW_OCR_MODEL={siliconflow_model}\n")
                keys_replaced["SILICONFLOW_OCR_MODEL"] = True
            elif line_strip.startswith("ALI_BAILIAN_OCR_MODEL="):
                new_lines.append(f"ALI_BAILIAN_OCR_MODEL={ali_bailian_model}\n")
                keys_replaced["ALI_BAILIAN_OCR_MODEL"] = True
            elif line_strip.startswith("PREFER_SOLVE_MODEL="):
                new_lines.append(f"PREFER_SOLVE_MODEL={prefer_solve_model}\n")
                keys_replaced["PREFER_SOLVE_MODEL"] = True
            elif line_strip.startswith("PREFER_PARSE_MODEL="):
                new_lines.append(f"PREFER_PARSE_MODEL={prefer_parse_model}\n")
                keys_replaced["PREFER_PARSE_MODEL"] = True
            elif line_strip.startswith("PREFER_CLASSIFY_MODEL=") or line_strip.startswith("DEEPSEEK_CLASSIFY_MODEL="):
                new_lines.append(f"PREFER_CLASSIFY_MODEL={prefer_classify_model}\n")
                keys_replaced["PREFER_CLASSIFY_MODEL"] = True
            elif line_strip.startswith("PREFER_DRAW_MODEL="):
                new_lines.append(f"PREFER_DRAW_MODEL={prefer_draw_model}\n")
                keys_replaced["PREFER_DRAW_MODEL"] = True
            else:
                new_lines.append(line)

        # Append keys if not replaced
        if not keys_replaced["DEEPSEEK_API_KEY"]:
            new_lines.append(f"DEEPSEEK_API_KEY={deepseek_key}\n")
        if not keys_replaced["DEEPSEEK_OCR_MODEL"]:
            new_lines.append(f"DEEPSEEK_OCR_MODEL={deepseek_model}\n")
        if not keys_replaced["SILICONFLOW_API_KEY"]:
            new_lines.append(f"SILICONFLOW_API_KEY={siliconflow_key}\n")
        if not keys_replaced["ALI_BAILIAN_API_KEY"]:
            new_lines.append(f"ALI_BAILIAN_API_KEY={ali_bailian_key}\n")
        if not keys_replaced["ZHONGZHAN_GPT_API_KEY"]:
            new_lines.append(f"ZHONGZHAN_GPT_API_KEY={zhongzhan_gpt_key}\n")
        if not keys_replaced["ZHONGZHAN_GPT_BASE_URL"]:
            new_lines.append(f"ZHONGZHAN_GPT_BASE_URL={zhongzhan_gpt_base_url}\n")
        if not keys_replaced["ZHONGZHAN_GPT_OCR_MODEL"]:
            new_lines.append(f"ZHONGZHAN_GPT_OCR_MODEL={zhongzhan_gpt_ocr_model}\n")
        if not keys_replaced["ZHONGZHAN_CLAUDE_API_KEY"]:
            new_lines.append(f"ZHONGZHAN_CLAUDE_API_KEY={zhongzhan_claude_key}\n")
        if not keys_replaced["ZHONGZHAN_CLAUDE_BASE_URL"]:
            new_lines.append(f"ZHONGZHAN_CLAUDE_BASE_URL={zhongzhan_claude_base_url}\n")
        if not keys_replaced["ZHONGZHAN_CLAUDE_OCR_MODEL"]:
            new_lines.append(f"ZHONGZHAN_CLAUDE_OCR_MODEL={zhongzhan_claude_ocr_model}\n")
        if not keys_replaced["OCR_PREFER_ENGINE"]:
            new_lines.append(f"OCR_PREFER_ENGINE={prefer_engine}\n")
        if not keys_replaced["SILICONFLOW_OCR_MODEL"]:
            new_lines.append(f"SILICONFLOW_OCR_MODEL={siliconflow_model}\n")
        if not keys_replaced["ALI_BAILIAN_OCR_MODEL"]:
            new_lines.append(f"ALI_BAILIAN_OCR_MODEL={ali_bailian_model}\n")
        if not keys_replaced["PREFER_SOLVE_MODEL"]:
            new_lines.append(f"PREFER_SOLVE_MODEL={prefer_solve_model}\n")
        if not keys_replaced["PREFER_PARSE_MODEL"]:
            new_lines.append(f"PREFER_PARSE_MODEL={prefer_parse_model}\n")
        if not keys_replaced["PREFER_CLASSIFY_MODEL"]:
            new_lines.append(f"PREFER_CLASSIFY_MODEL={prefer_classify_model}\n")
        if not keys_replaced["PREFER_DRAW_MODEL"]:
            new_lines.append(f"PREFER_DRAW_MODEL={prefer_draw_model}\n")

        dependencies.write_private_text_atomic(dependencies.ENV_FILE, "".join(new_lines))

        # Clean current process env
        dependencies.os.environ.pop("PIX2TEXT_API_KEY", None)
        dependencies.os.environ.pop("PIX2TEXT_SERVER_TYPE", None)

        dependencies.os.environ["DEEPSEEK_API_KEY"] = deepseek_key
        dependencies.os.environ["DEEPSEEK_OCR_MODEL"] = deepseek_model
        dependencies.os.environ["SILICONFLOW_API_KEY"] = siliconflow_key
        dependencies.os.environ["ALI_BAILIAN_API_KEY"] = ali_bailian_key
        dependencies.os.environ["ZHONGZHAN_GPT_API_KEY"] = zhongzhan_gpt_key
        dependencies.os.environ["ZHONGZHAN_GPT_BASE_URL"] = zhongzhan_gpt_base_url
        dependencies.os.environ["ZHONGZHAN_GPT_OCR_MODEL"] = zhongzhan_gpt_ocr_model
        dependencies.os.environ["ZHONGZHAN_CLAUDE_API_KEY"] = zhongzhan_claude_key
        dependencies.os.environ["ZHONGZHAN_CLAUDE_BASE_URL"] = zhongzhan_claude_base_url
        dependencies.os.environ["ZHONGZHAN_CLAUDE_OCR_MODEL"] = zhongzhan_claude_ocr_model

        dependencies.os.environ["OCR_PREFER_ENGINE"] = prefer_engine
        dependencies.os.environ["SILICONFLOW_OCR_MODEL"] = siliconflow_model
        dependencies.os.environ["ALI_BAILIAN_OCR_MODEL"] = ali_bailian_model
        dependencies.os.environ["PREFER_SOLVE_MODEL"] = prefer_solve_model
        dependencies.os.environ["PREFER_PARSE_MODEL"] = prefer_parse_model
        dependencies.os.environ["PREFER_CLASSIFY_MODEL"] = prefer_classify_model
        dependencies.os.environ["PREFER_DRAW_MODEL"] = prefer_draw_model

        return {"status": "success", "message": "API 与首选大模型配置已成功保存并即时生效！"}
    except Exception as e:
        return dependencies.JSONResponse(
            content={"status": "error", "message": f"保存配置失败: {str(e)}"},
            status_code=500
        )
