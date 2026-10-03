"""Shared PDF/Word result cleanup; paths and hooks are explicitly supplied."""

from pathlib import Path

from mathbank.document_text import normalize_fillin_macro, find_source_page_by_overlap


def post_process_questions(
    parsed_questions: list, paper_title: str, task_id: str = None,
    ocr_results: list = None, *, tmp_upload_dir: str | Path,
    upload_dir_rel: str, normalize_fillin=normalize_fillin_macro,
    find_source_page=find_source_page_by_overlap,
) -> list:
    """PDF/Word 解析卡片后处理：修复图片路径并登记资产，保留正文中的图片锚点。

    image_paths 负责资产生命周期，不能替代选项、表格或正文中的图片位置。
    """
    import re
    import os
    import glob

    # 0. 规范化所有拆解题目的填空下划线为 \fillin 宏
    for q in parsed_questions:
        if q.get("content"):
            q["content"] = normalize_fillin(q.get("content", ""))

    # 1. 搜集该 PDF 任务在 tmp 文件夹中生成的所有物理裁剪图片，按生成时间（mtime）进行排序
    task_crop_urls = []
    if task_id:
        crop_pattern = os.path.join(tmp_upload_dir, f"pdf_crop_{task_id}_*.png")
        crop_files = glob.glob(crop_pattern)
        crop_files.sort(key=lambda x: os.path.getmtime(x))
        task_crop_urls = [f"/{upload_dir_rel}/tmp/{os.path.basename(f)}" for f in crop_files]
        print(f"[PDF PostProcess] 发现任务 {task_id} 的实际裁剪图片 {len(task_crop_urls)} 张: {task_crop_urls}")

    # 2. 顺序提取出所有题目中未成功解析的插图占位符（例如 图1.png, 图2.png, 图1, 图2 等，特征是不以 /static/ 开头的图片引用路径）
    placeholders_in_order = []
    placeholder_seen = set()

    # 匹配 Markdown 图片格式: ![alt](url)
    md_pattern = r'!\[.*?\]\(([^)]+)\)'
    # 匹配 LaTeX 图片格式: \includegraphics[...]{path}
    latex_pattern = r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}'

    for q in parsed_questions:
        for field in ["content", "answer_markdown"]:
            text_val = q.get(field, "")
            if isinstance(text_val, str):
                # 提取 Markdown 图片占位符
                for m in re.finditer(md_pattern, text_val):
                    url = m.group(1).strip()
                    if url and not url.startswith("/static/") and url not in placeholder_seen:
                        placeholder_seen.add(url)
                        placeholders_in_order.append(url)
                # 提取 LaTeX 图片占位符
                for m in re.finditer(latex_pattern, text_val):
                    url = m.group(1).strip()
                    if url and not url.startswith("/static/") and url not in placeholder_seen:
                        placeholder_seen.add(url)
                        placeholders_in_order.append(url)

    # 3. 建立占位符与物理裁剪图片路径的 1-to-1 映射关系
    mapping = {}
    for idx, ph in enumerate(placeholders_in_order):
        if idx < len(task_crop_urls):
            mapping[ph] = task_crop_urls[idx]
    if mapping:
        print(f"[PDF PostProcess] 成功建立占位符修复映射: {mapping}")

    # 4. 对每个题目卡片进行字段修补、占位符替换与资源晋升准备
    for q in parsed_questions:
        q["source"] = (q.get("source") or paper_title).strip()

        # 清理多余的双重转义 \n
        for field in ["content", "answer_markdown"]:
            if field in q and isinstance(q[field], str):
                text = q[field]
                text = re.sub(r'\\n(?![a-zA-Z])', '\n', text)
                q[field] = text

        # 智能替换 Markdown 和 LaTeX 字段中的图片占位符
        for field in ["content", "answer_markdown"]:
            if field in q and isinstance(q[field], str):
                # 替换已建立映射的非标准路径
                for ph, real_url in mapping.items():
                    if ph in q[field]:
                        q[field] = q[field].replace(ph, real_url)
                        # 如果是 LaTeX 的 \includegraphics 语法，顺带转换为 Markdown 图片语法以供前端预览渲染
                        latex_img_pattern = r'\\includegraphics(?:\[.*?\])?\{' + re.escape(real_url) + r'\}'
                        q[field] = re.sub(latex_img_pattern, f'![插图]({real_url})', q[field])

        # 寻找本题正文中夹带的所有临时图片 URL (注意：UUID 中含有 -，所以 regex 必须支持 [a-zA-Z0-9_-]+)
        found_crops = {}
        for field in ["content", "answer_markdown"]:
            if field in q and isinstance(q[field], str):
                for match in re.finditer(r'/static/(?:uploads|test_uploads)/tmp/[a-zA-Z0-9_.-]+', q[field]):
                    found_crops[match.group(0)] = None

        # 顺带检查 referenced_images 属性并应用修复映射
        ref_imgs = q.get("referenced_images", [])
        for ref in ref_imgs:
            mapped_ref = mapping.get(ref, ref)
            if "/tmp/" in mapped_ref:
                filename = os.path.basename(mapped_ref)
                found_crops[f"/{upload_dir_rel}/tmp/{filename}"] = None

        # 按正文、解答、补充引用的首次出现顺序登记，不能用无序集合打乱图片。
        q["image_paths"] = list(found_crops)

    # 5. 极致兜底机制：如果大模型在拆题时完全删除了图片占位标记或路径，导致最终题目关联的图片为空，
    # 我们利用 3-shingle 文本重合度，将原始 PDF 物理页面产生的物理插图自动关联绑定回拆分出的题目！
    if ocr_results and task_id:
        page_crops = {}
        for p_idx, page_text in enumerate(ocr_results):
            # 获取当前页生成的所有 pdf_crop_ 临时文件 URL
            urls_on_page = re.findall(r'/static/uploads(?:_test|/test_uploads|/uploads)?/tmp/pdf_crop_[a-zA-Z0-9_-]+\.png', page_text or "")
            page_crops[p_idx] = list(dict.fromkeys(urls_on_page))

        print(f"[PDF PostProcess Failsafe] 每页识别到的插图关系: {page_crops}")

        for q in parsed_questions:
            if not q.get("image_paths"):
                p_source = find_source_page(q.get("content", ""), ocr_results)
                crops = page_crops.get(p_source, [])
                if crops:
                    q["image_paths"] = crops
                    print(f"[PDF PostProcess Failsafe] 成功通过重合度，将第 {p_source + 1} 页的插图 {crops} 兜底分配给题目: {q.get('content')[:40]}...")

    # Keep image markup in place. The preview already skips thumbnails for images
    # rendered in Markdown; stripping markup here empties image-only choices and
    # destroys the relationship between an option label and its graph.
    return parsed_questions
