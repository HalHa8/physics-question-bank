"""Shared local postprocessing, with original physical content retained."""
from mathbank.document_text import normalize_fillin_macro, find_source_page_by_overlap
from mathbank.ai_knowledge_points import annotate_ai_knowledge_points, load_ai_knowledge_catalog
from mathbank.math_markdown import normalize_question_math_markdown
from mathbank.source_metadata import normalize_source_fillin
from mathbank.question_assets import embedded_question_assets
from pathlib import Path

def post_process_questions(parsed_questions: list, paper_title: str, task_id: str=None, ocr_results: list=None, *, source_body_preserved: bool=False, preserved_indices=None, tmp_upload_dir, upload_dir_rel, normalize_fillin=normalize_fillin_macro, find_source_page=find_source_page_by_overlap) -> list:
    """PDF/Word 解析卡片后处理：修复图片路径并登记资产，保留正文中的图片锚点。

    image_paths 负责资产生命周期，不能替代选项、表格或正文中的图片位置。
    """
    import re
    import os
    import glob
    preserved = set(range(len(parsed_questions))) if source_body_preserved else set(preserved_indices or ())
    if any((type(index) is not int or not 0 <= index < len(parsed_questions) for index in preserved)):
        raise ValueError('保真题目位置无效。')
    for (index, q) in enumerate(parsed_questions):
        if q.get('content'):
            q['content'] = normalize_source_fillin(q['content'], normalize_fillin) if index in preserved else normalize_fillin(q['content'])
    task_crop_urls = []
    if task_id:
        crop_pattern = os.path.join(tmp_upload_dir, f'pdf_crop_{task_id}_*.png')
        crop_files = glob.glob(crop_pattern)
        crop_files.sort(key=lambda x: os.path.getmtime(x))
        task_crop_urls = [f'/{upload_dir_rel}/tmp/{os.path.basename(f)}' for f in crop_files]
        print(f'[PDF PostProcess] 发现任务 {task_id} 的实际裁剪图片 {len(task_crop_urls)} 张: {task_crop_urls}')
    placeholders_in_order = []
    placeholder_seen = set()
    md_pattern = '!\\[.*?\\]\\(([^)]+)\\)'
    latex_pattern = '\\\\includegraphics(?:\\[.*?\\])?\\{([^}]+)\\}'
    for (index, q) in enumerate(parsed_questions):
        if index in preserved:
            continue
        for field in ['content', 'answer_markdown']:
            text_val = q.get(field, '')
            if isinstance(text_val, str):
                for m in re.finditer(md_pattern, text_val):
                    url = m.group(1).strip()
                    if url and (not url.startswith('/static/')) and (url not in placeholder_seen):
                        placeholder_seen.add(url)
                        placeholders_in_order.append(url)
                for m in re.finditer(latex_pattern, text_val):
                    url = m.group(1).strip()
                    if url and (not url.startswith('/static/')) and (url not in placeholder_seen):
                        placeholder_seen.add(url)
                        placeholders_in_order.append(url)
    mapping = {}
    for (idx, ph) in enumerate(placeholders_in_order):
        if idx < len(task_crop_urls):
            mapping[ph] = task_crop_urls[idx]
    if mapping:
        print(f'[PDF PostProcess] 成功建立占位符修复映射: {mapping}')
    for (index, q) in enumerate(parsed_questions):
        q['source'] = (q.get('source') or paper_title).strip()
        if index not in preserved:
            for field in ['content', 'answer_markdown']:
                if field in q and isinstance(q[field], str):
                    text = q[field]
                    text = re.sub('\\\\n(?![a-zA-Z])', '\n', text)
                    q[field] = text
        for field in ['content', 'answer_markdown']:
            if field in q and isinstance(q[field], str):
                for (ph, real_url) in () if index in preserved else mapping.items():
                    if ph in q[field]:
                        q[field] = q[field].replace(ph, real_url)
                        latex_img_pattern = '\\\\includegraphics(?:\\[.*?\\])?\\{' + re.escape(real_url) + '\\}'
                        q[field] = re.sub(latex_img_pattern, f'![插图]({real_url})', q[field])
        found_crops = {}
        if index in preserved:
            for path in embedded_question_assets(q.get('content', ''), q.get('answer_markdown', '')):
                if '/tmp/' in path:
                    found_crops[path] = None
        else:
            for field in ['content', 'answer_markdown']:
                if field in q and isinstance(q[field], str):
                    for match in re.finditer('/static/(?:uploads|test_uploads)/tmp/[a-zA-Z0-9_.-]+', q[field]):
                        found_crops[match.group(0)] = None
        ref_imgs = [] if index in preserved else q.get('referenced_images', [])
        for ref in ref_imgs:
            mapped_ref = mapping.get(ref, ref)
            if '/tmp/' in mapped_ref:
                filename = os.path.basename(mapped_ref)
                found_crops[f'/{upload_dir_rel}/tmp/{filename}'] = None
        q['image_paths'] = list(found_crops)
    if ocr_results and task_id and (len(preserved) < len(parsed_questions)):
        page_crops = {}
        for (p_idx, page_text) in enumerate(ocr_results):
            urls_on_page = re.findall('/static/uploads(?:_test|/test_uploads|/uploads)?/tmp/pdf_crop_[a-zA-Z0-9_-]+\\.png', page_text or '')
            page_crops[p_idx] = list(dict.fromkeys(urls_on_page))
        print(f'[PDF PostProcess Failsafe] 每页识别到的插图关系: {page_crops}')
        for (index, q) in enumerate(parsed_questions):
            if index in preserved:
                continue
            if not q.get('image_paths'):
                p_source = find_source_page(q.get('content', ''), ocr_results)
                crops = page_crops.get(p_source, [])
                if crops:
                    q['image_paths'] = crops
                    print(f"[PDF PostProcess Failsafe] 成功通过重合度，将第 {p_source + 1} 页的插图 {crops} 兜底分配给题目: {q.get('content')[:40]}...")
    knowledge_catalog = load_ai_knowledge_catalog()
    for question in parsed_questions:
        if 'knowledge_points' in question:
            annotate_ai_knowledge_points(question, knowledge_catalog)
    return parsed_questions
