"""Document orchestration; runtime and all external callbacks are injected."""
from mathbank.document_import_context import DocumentImportDependencies
from mathbank.ai_providers import OCRConfigurationError, OCRResponseTimeoutError, ParseConfigurationError

def run_pdf_parsing_task(task_id: str, file_bytes: bytes, filename: str, generate_answers: bool=False, page_range: str=None, pdf_strategy: str='native_preferred', pdf_verify_suspicions: bool=False, *, dependencies: DocumentImportDependencies):
    """PDF parsing with bounded OCR concurrency and cooperative cancellation."""
    import concurrent.futures
    temp_assets: list[str] = []
    tmp_pdf_path = dependencies.Path(dependencies.tmp_upload_dir) / f'{task_id}.pdf'
    diagnostics: dict = {}
    layout_result = None
    page_urls = []
    target_page_indices = []
    ocr_results = []
    source_pages = None
    vision_lock = dependencies.threading.Lock()

    def check_pdf_cancelled():
        dependencies.tasks.check_cancelled(task_id)
        if not dependencies.tasks.exists(task_id):
            raise dependencies.TaskCancelled('PDF 任务已移除。')

    def report_pdf_attempt(event):
        check_pdf_cancelled()
        with vision_lock:
            report = diagnostics.setdefault('pdf_vision', {'timeout_seconds': dependencies.DOCUMENT_AI_TIMEOUT_SECONDS, 'max_attempts': 1, 'attempts': []})
            event = {**event, 'page_number': event['page_index'] + 1}
            identity = (event['page_index'], event['stage'], event['attempt'])
            previous = next((item for item in report['attempts'] if (item['page_index'], item['stage'], item['attempt']) == identity), None)
            if previous is None:
                report['attempts'].append(event)
            else:
                previous.update(event)
            report['calls'] = len(report['attempts'])
            report['retries'] = sum((item['attempt'] > 1 for item in report['attempts']))
            report['usage'] = dependencies.collected_usage(report['attempts'])
            report['usage_complete'] = all((all((key in item['usage'] for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'))) for item in report['attempts']))
            if event['status'] == 'running':
                log = f"第 {event['page_number']} 页识别：第 {event['attempt']} / 1 次请求，每次等待上限 {dependencies.DOCUMENT_AI_TIMEOUT_SECONDS} 秒..."
            elif event.get('retrying'):
                log = f"第 {event['page_number']} 页识别失败，准备重试一次：{event['error']}"
            else:
                log = None
            changes = {'diagnostics': dependencies.copy.deepcopy(diagnostics)}
            if log:
                changes['log'] = log
            dependencies.tasks.update(task_id, **changes)

    def report_pdf_split_attempt(event):
        check_pdf_cancelled()
        if event.get('stream_progress'):
            received = event.get('stream_content_characters', 0)
            log = f'模型已返回 {received} 个正文字符，正在接收完整拆题结果...' if received else None
        elif event['status'] == 'running':
            log = f"正在拆解已识别的试卷文本：第 {event['attempt']} / 1 次请求，每次等待上限 {dependencies.PAPER_SPLIT_TIMEOUT_SECONDS} 秒..."
        elif event.get('retrying'):
            log = f"试卷文本拆题失败，准备重试一次：{event['error']}"
        else:
            log = None
        changes = {'diagnostics': dependencies.copy.deepcopy(diagnostics)}
        if log:
            changes['log'] = log
        dependencies.tasks.update(task_id, **changes)

    def retain_split_input(source_content, model_source):
        cache = {'source_sha256': dependencies.hashlib.sha256(file_bytes).hexdigest(), 'model_source_sha256': dependencies.hashlib.sha256(model_source.encode('utf-8')).hexdigest(), 'input_characters': len(model_source), 'status': 'complete', 'source_markdown': source_content, 'model_source': model_source}
        if len(dependencies.json.dumps(cache, ensure_ascii=False)) > dependencies.PAPER_SPLIT_CACHE_MAX_CHARACTERS:
            cache = {key: value for (key, value) in cache.items() if key not in ('source_markdown', 'model_source')}
            cache['status'] = 'metadata_only'
        dependencies.tasks.update(task_id, pdf_source_cache=cache)
    try:
        import pymupdf as fitz
    except ImportError:
        dependencies.tasks.fail(task_id, '本地 Python 环境未安装 PyMuPDF，请通过 pip install pymupdf 安装依赖！', document_type='pdf')
        return
    try:
        dependencies.tasks.check_cancelled(task_id)
        if pdf_strategy not in dependencies.PDF_STRATEGIES:
            raise ValueError('不支持的 PDF 解析策略。')
        tmp_pdf_path.write_bytes(file_bytes)
        dependencies.tasks.update(task_id, status='processing_images', progress=10, log='已接收文件，正在渲染 PDF 高清页面...', document_type='pdf', temp_assets=[])
        page_images: list[str] = []
        page_urls: list[str] = []
        page_layout_infos: dict[int, dict] = {}
        joint_page_results: dict[int, dict] = {}
        with fitz.open(tmp_pdf_path) as document:
            total_pages = len(document)
            if total_pages == 0:
                raise ValueError('此 PDF 没有有效页面，或者格式已损坏！')
            target_page_indices = dependencies.parse_page_range(page_range, total_pages)
            if len(target_page_indices) > dependencies.max_pdf_pages:
                raise ValueError(f'单次最多解析 {dependencies.max_pdf_pages} 页，请填写较小的页码范围。')
            for page_num in target_page_indices:
                dependencies.tasks.check_cancelled(task_id)
                page = document.load_page(page_num)
                if pdf_strategy == 'layout_aware':
                    page_layout_infos[page_num] = dependencies.inspect_pdf_page(page, page_num)
                estimated_pixels = int(page.rect.width / 72 * 150 * (page.rect.height / 72 * 150))
                if estimated_pixels > 30000000:
                    raise ValueError(f'第 {page_num + 1} 页尺寸异常，已停止高清渲染。')
                pixmap = page.get_pixmap(dpi=150)
                image_filename = f'pdf_page_{task_id}_{page_num}.png'
                image_path = dependencies.Path(dependencies.tmp_upload_dir) / image_filename
                pixmap.save(image_path)
                image_url = f'/{dependencies.upload_dir_rel}/tmp/{image_filename}'
                page_images.append(str(image_path))
                page_urls.append(image_url)
                temp_assets.append(image_url)
                dependencies.tasks.update(task_id, page_images=list(page_urls), page_numbers=[number + 1 for number in target_page_indices[:len(page_urls)]], temp_assets=list(temp_assets))
        tmp_pdf_path.unlink(missing_ok=True)
        dependencies.tasks.check_cancelled(task_id)
        total_target_pages = len(target_page_indices)
        if pdf_strategy == 'force_ocr':
            inspector_result = {'pages': [], 'pdf_type': 'scanned'}
            inspector_pages = {}
        else:
            inspector_result = dependencies.inspect_pdf(file_bytes, task_id, page_indices=target_page_indices, include_source_review_evidence=True)
            inspector_pages = {int(page.get('page_index')): page for page in inspector_result.get('pages', []) if page.get('page_index') is not None}
            diagnostics['pdf_native_quality'] = [{'page_number': index + 1, 'reasons': page['quality_reasons']} for (index, page) in inspector_pages.items() if page.get('quality_reasons')]
            diagnostics['pdf_native_repair'] = [{'page_number': index + 1, **page['native_repair']} for (index, page) in inspector_pages.items() if page.get('native_repair')]
        dependencies.tasks.check_cancelled(task_id)
        ocr_results = [None] * total_target_pages
        pages_requiring_ocr = []
        native_page_count = 0
        for (local_idx, page_num) in enumerate(target_page_indices):
            page_info = inspector_pages.get(page_num)
            native_text = str((page_info or {}).get('markdown') or '').strip()
            if page_info and (not page_info.get('needs_ocr')) and native_text:
                ocr_results[local_idx] = f'<!-- MATHBANK_PDF_PAGE:{page_num + 1} -->\n{native_text}'
                native_page_count += 1
            else:
                pages_requiring_ocr.append(local_idx)
        regional_plans: dict[int, dict] = {}
        if pdf_strategy != 'force_ocr' and pages_requiring_ocr:
            from mathbank.pdf_native_regions import plan_pdf_regions
            with fitz.open(stream=file_bytes, filetype='pdf') as document:
                for local_idx in pages_requiring_ocr:
                    dependencies.tasks.check_cancelled(task_id)
                    page_num = target_page_indices[local_idx]
                    info = page_layout_infos.get(page_num)
                    if info is None:
                        info = dependencies.inspect_pdf_page(document[page_num], page_num)
                        page_layout_infos[page_num] = info
                    plan = plan_pdf_regions(document[page_num], info)
                    if plan is not None:
                        regional_plans[local_idx] = plan
        detail_results: dict[int, dict] = {}
        if pdf_strategy == 'layout_aware':
            from mathbank.pdf_vision_details import render_pdf_detail_views
            detail_bytes_remaining = 80 * 1024 * 1024

            def register_detail_asset(path):
                if path not in temp_assets:
                    temp_assets.append(path)
                if not dependencies.tasks.add_temp_asset(task_id, path):
                    raise dependencies.TaskCancelled('PDF 任务已移除。')
                check_pdf_cancelled()
            full_page_indices = [index for index in pages_requiring_ocr if index not in regional_plans]
            if full_page_indices:
                dependencies.tasks.update(task_id, log='正在准备原页局部放大视图，辅助精读小字和数学符号...')
                with fitz.open(stream=file_bytes, filetype='pdf') as document:
                    for local_idx in full_page_indices:
                        check_pdf_cancelled()
                        page_num = target_page_indices[local_idx]
                        try:
                            details = render_pdf_detail_views(document[page_num], page_index=page_num, output_dir=dependencies.Path(dependencies.tmp_upload_dir), asset_prefix=f'pdf_detail_{task_id}_{page_num}', url_prefix=f'/{dependencies.upload_dir_rel}/tmp', register_asset=register_detail_asset, check_cancelled=check_pdf_cancelled, byte_budget=detail_bytes_remaining)
                        except dependencies.TaskCancelled:
                            raise
                        except Exception:
                            details = {'status': 'skipped', 'views': [], 'total_png_bytes': 0, 'notes': ['本页高清辅助视图无法准备，继续使用整页识图。']}
                        detail_results[local_idx] = details
                        detail_bytes_remaining -= details.get('total_png_bytes', 0)
            diagnostics['pdf_detail_views'] = {'prepared_pages': sum((bool(item['views']) for item in detail_results.values())), 'prepared_images': sum((len(item['views']) for item in detail_results.values())), 'separate_detail_requests': 0, 'independent_verification': False, 'pages': [{'page_number': target_page_indices[index] + 1, 'status': item['status'], 'notes': list(item['notes']), 'views': [{key: view[key] for key in ('id', 'page_index', 'bbox', 'actualdpi', 'width', 'height', 'sha256')} for view in item['views']]} for (index, item) in detail_results.items()]}
        extraction_pages = []
        for (local_idx, page_num) in enumerate(target_page_indices):
            plan = regional_plans.get(local_idx)
            extraction_pages.append({'page_number': page_num + 1, 'mode': ('regional' if plan else 'full_vision') if local_idx in pages_requiring_ocr else 'native', 'structure_repaired': inspector_pages.get(page_num, {}).get('native_repair', {}).get('status') == 'repaired', 'native_characters': plan['native_characters'] if plan else 0, 'region_count': len(plan['regions']) if plan else 0, 'image_area_ratio': plan['area_ratio'] if plan else 1 if local_idx in pages_requiring_ocr else 0})
        diagnostics['pdf_extraction'] = {'native_pages': native_page_count, 'repaired_pages': sum((inspector_pages.get(page_num, {}).get('native_repair', {}).get('status') == 'repaired' and (not inspector_pages.get(page_num, {}).get('needs_ocr')) for page_num in target_page_indices)), 'regional_pages': len(regional_plans), 'full_vision_pages': len(pages_requiring_ocr) - len(regional_plans), 'native_characters_reused': sum((plan['native_characters'] for plan in regional_plans.values())), 'pages': extraction_pages}
        dependencies.tasks.update(task_id, diagnostics=diagnostics)
        if native_page_count:
            print(f"[PDF Inspector Flow] 原生直提 {native_page_count} 页，视觉 OCR {len(pages_requiring_ocr)} 页 (Type: {inspector_result.get('pdf_type')})", flush=True)
        if not pages_requiring_ocr:
            dependencies.tasks.update(task_id, status='ai_splitting', progress=60, log=f'pdf-inspector 已按所选范围可靠提取 {native_page_count} 页原生文本，正在连续拆题...', page_images=list(page_urls), temp_assets=list(temp_assets))
        else:
            if pdf_strategy == 'force_ocr':
                extraction_log = f'按所选全页识图模式，正在识别 {total_target_pages} 页文字与公式...'
            elif regional_plans:
                extraction_log = f'所选 {total_target_pages} 页：原生直提 {native_page_count} 页，局部识别 {len(regional_plans)} 页，整页识别 {len(pages_requiring_ocr) - len(regional_plans)} 页；局部页保留可靠原文，仅发送需要补全的区域...'
            elif native_page_count == 0:
                extraction_log = f'已尝试原生提取，所选 {total_target_pages} 页的文字或公式未通过质量检查，改用逐页视觉识别...'
            else:
                extraction_log = f'所选 {total_target_pages} 页中，{native_page_count} 页采用原生文字，其余 {len(pages_requiring_ocr)} 页因提取质量问题改用视觉识别...'
            dependencies.tasks.update(task_id, status='ocr_extraction', progress=30, log=extraction_log, page_images=list(page_urls), temp_assets=list(temp_assets))

            def ocr_worker(local_idx, image_path):
                acquired = False
                try:
                    while not acquired:
                        check_pdf_cancelled()
                        acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                    check_pdf_cancelled()
                    real_page_num = target_page_indices[local_idx] + 1
                    joint = None
                    if local_idx in regional_plans:
                        from mathbank.pdf_region_vision import request_pdf_regions
                        joint = request_pdf_regions(image_path, page_layout_infos[real_page_num - 1], regional_plans[local_idx], include_figures=pdf_strategy == 'layout_aware', check_cancelled=check_pdf_cancelled, report_attempt=report_pdf_attempt, include_transcription_evidence=True)
                        raw_text = joint['markdown']
                    elif pdf_strategy == 'layout_aware':
                        from mathbank.pdf_page_vision import request_pdf_page, choose_pdf_page_vision_dpi
                        detail_kwargs = {'detail_views': detail_results[local_idx]['views']} if detail_results.get(local_idx, {}).get('views') else {}
                        if choose_pdf_page_vision_dpi(inspector_pages.get(real_page_num - 1)) == 110:
                            import tempfile
                            with tempfile.TemporaryDirectory(prefix='pdf-request-', dir=dependencies.tmp_upload_dir) as request_dir:
                                request_path = dependencies.Path(request_dir) / dependencies.Path(image_path).name
                                with fitz.open(stream=file_bytes, filetype='pdf') as original:
                                    original[real_page_num - 1].get_pixmap(dpi=110).save(request_path)
                                check_pdf_cancelled()
                                joint = request_pdf_page(str(request_path), page_layout_infos[real_page_num - 1], check_cancelled=check_pdf_cancelled, report_attempt=report_pdf_attempt)
                        else:
                            joint = request_pdf_page(image_path, page_layout_infos[real_page_num - 1], check_cancelled=check_pdf_cancelled, report_attempt=report_pdf_attempt, **detail_kwargs, include_transcription_evidence=True)
                        raw_text = joint['markdown']
                    else:
                        raw_text = dependencies.ocr_page(image_path, check_cancelled=check_pdf_cancelled, report_attempt=report_pdf_attempt, page_index=real_page_num - 1)
                    print(f'[PDF OCR] 第 {real_page_num} 页识别完成 (characters={len(raw_text)}).')
                    return (local_idx, raw_text, None, joint)
                except dependencies.TaskCancelled:
                    raise
                except Exception as ocr_error:
                    code = ('ocr_configuration_required' if isinstance(ocr_error, OCRConfigurationError)
                            else 'ocr_response_timeout' if isinstance(ocr_error, OCRResponseTimeoutError)
                            else 'document_parse_failed')
                    return (local_idx, '', {'message': str(ocr_error), 'error_code': code}, None)
                finally:
                    if acquired:
                        dependencies.ocr_semaphore.release()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(pages_requiring_ocr), 4), thread_name_prefix='mathbank-pdf-ocr')
            futures = []
            try:
                for local_idx in pages_requiring_ocr:
                    dependencies.tasks.check_cancelled(task_id)
                    futures.append(executor.submit(ocr_worker, local_idx, page_images[local_idx]))
                completed = 0
                page_errors = []
                for future in dependencies.iter_completed_futures(futures, check_pdf_cancelled):
                    check_pdf_cancelled()
                    (local_idx, text, error, joint) = future.result()
                    if error:
                        real_page_num = target_page_indices[local_idx] + 1
                        page_errors.append({'page_number': real_page_num,
                            'error': error['message'], 'error_code': error['error_code']})
                    else:
                        processed_text = dependencies.process_ocr_illustrations(text)
                        real_page_num = target_page_indices[local_idx] + 1
                        if joint is not None:
                            joint_page_results[real_page_num - 1] = joint
                        ocr_results[local_idx] = f'<!-- MATHBANK_PDF_PAGE:{real_page_num} -->\n{processed_text.strip()}'
                    completed += 1
                    progress = 30 + int(completed / len(pages_requiring_ocr) * 40)
                    dependencies.tasks.update(task_id, progress=progress, log=f'视觉转译进度: {completed} / {len(pages_requiring_ocr)} 页已处理...' + (f'（局部识别 {len(regional_plans)} 页）' if regional_plans else '') + (f'；{len(page_errors)} 页未完成，已保留其他页面结果。' if page_errors else ''))
                if page_errors:
                    diagnostics['pdf_failed_pages'] = sorted(page_errors, key=lambda item: item['page_number'])
                    message = '；'.join(
                        f"第 {item['page_number']} 页" + (
                            '需要识图，请检查服务配置: ' if item['error_code'] == 'ocr_configuration_required'
                            else '识图超时: ' if item['error_code'] == 'ocr_response_timeout'
                            else '解析出错: ') + item['error']
                        for item in diagnostics['pdf_failed_pages'])
                    codes = {item['error_code'] for item in page_errors}
                    if 'ocr_configuration_required' in codes:
                        raise OCRConfigurationError(message)
                    if 'ocr_response_timeout' in codes:
                        raise OCRResponseTimeoutError(message)
                    raise RuntimeError(message)
            finally:
                cancelled = dependencies.tasks.is_cancelled(task_id) or not dependencies.tasks.exists(task_id)
                if cancelled:
                    for future in futures:
                        future.cancel()
                executor.shutdown(wait=not cancelled, cancel_futures=True)
        regional_results = [joint_page_results[target_page_indices[index]] for index in regional_plans]
        if 'pdf_detail_views' in diagnostics:
            successful_details = [item.get('detail_input', {}) for item in joint_page_results.values() if item.get('detail_input', {}).get('status') == 'included']
            diagnostics['pdf_detail_views']['successful_input_pages'] = len(successful_details)
            diagnostics['pdf_detail_views']['successful_input_images'] = sum((item['detail_count'] for item in successful_details))
            for (index, details) in detail_results.items():
                joint = joint_page_results.get(target_page_indices[index], {})
                for note in [*details['notes'], *joint.get('detail_input', {}).get('notes', [])]:
                    if joint.get('layout') is not None:
                        joint['layout'].setdefault('notes', []).append(note)
        if regional_results:
            diagnostics['pdf_regional_usage'] = {key: sum((item['usage'][key] for item in regional_results)) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens') if all((key in item.get('usage', {}) for item in regional_results))}
        dependencies.tasks.check_cancelled(task_id)
        if pdf_strategy == 'layout_aware':

            def check_layout_cancelled():
                dependencies.tasks.check_cancelled(task_id)
                if not dependencies.tasks.exists(task_id):
                    raise dependencies.TaskCancelled('PDF 任务已移除。')

            def register_figure_asset(path):
                temp_assets.append(path)
                if not dependencies.tasks.add_temp_asset(task_id, path):
                    raise dependencies.TaskCancelled('PDF 任务已移除。')
                check_layout_cancelled()

            def report_layout_progress(local_index, message):
                check_layout_cancelled()
                dependencies.tasks.update(task_id, status='layout_analysis', progress=72 + int(7 * local_index / max(1, total_target_pages)), log=message)
            layout_result = dependencies.enrich_pdf_with_figures(file_bytes, target_page_indices, page_images, page_urls, ocr_results, {target_page_indices[index] for index in pages_requiring_ocr}, output_dir=dependencies.Path(dependencies.tmp_upload_dir), url_prefix=f'/{dependencies.upload_dir_rel}/tmp', task_id=task_id, check_cancelled=check_layout_cancelled, register_asset=register_figure_asset, report_progress=report_layout_progress, report_attempt=report_pdf_attempt, precomputed_layouts={index: item['layout'] for (index, item) in joint_page_results.items()}, precomputed_page_infos=page_layout_infos, vision_semaphore=dependencies.ocr_semaphore)
            ocr_results = layout_result['page_texts']
            diagnostics['pdf_layout'] = layout_result['diagnostics']
            diagnostics['pdf_layout']['joint_visual_calls'] = sum((item.get('visual_calls', 1) for item in joint_page_results.values()))
            diagnostics['pdf_layout']['regional_visual_calls'] = sum((item.get('visual_calls', 1) for item in regional_results))
            diagnostics['pdf_joint_usage'] = {key: sum((item['usage'][key] for item in joint_page_results.values())) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens') if joint_page_results and all((key in item.get('usage', {}) for item in joint_page_results.values()))}
            dependencies.tasks.update(task_id, pdf_layout={'schema': layout_result['schema'], 'pages': layout_result['pages']}, diagnostics=diagnostics)
        source_pages = []
        if sum((len(str(text or '')) for text in ocr_results)) <= 500000:
            for (local_idx, page_num) in enumerate(target_page_indices):
                page = next((item for item in (layout_result or {}).get('pages', []) if item['page_index'] == page_num), {})
                origin = 'regional_vision' if local_idx in regional_plans else 'joint_vision' if page_num in joint_page_results else 'ocr' if local_idx in pages_requiring_ocr else 'native_repaired' if inspector_pages.get(page_num, {}).get('native_repair', {}).get('status') == 'repaired' else 'native'
                source_pages.append({'page_number': page_num + 1, 'origin': origin, 'markdown': str(ocr_results[local_idx] or ''), 'figures': page.get('figures', [])})
            dependencies.tasks.update(task_id, pdf_source_pages=source_pages)
        full_latex_content = dependencies.merge_pdf_page_texts(ocr_results)
        if not full_latex_content.strip():
            raise ValueError('所选 PDF 页面未能提取出可解析的文字内容。')
        dependencies.tasks.update(task_id, status='ai_splitting', progress=80, log='文本与公式准备就绪！正在调用大模型拆解题目与标注属性...')
        dependencies.tasks.check_cancelled(task_id)
        task = dependencies.tasks.snapshot(task_id) or {}
        options = (task.get('document_input') or {}).get('options') or {}
        paper_title = str(options.get('paper_title') or '').strip()
        if not paper_title:
            paper_title = dependencies.extract_title_from_latex(full_latex_content) or dependencies.os.path.splitext(filename)[0]
        if layout_result is not None:
            source_content = dependencies.re.sub('<!-- MATHBANK_PDF_PAGE:\\d+ -->', '', full_latex_content)
            (locked_source, math_locks) = dependencies.lock_visible_math(source_content, task_id.replace('-', '')[:16])
            diagnostics['math_locks_created'] = len(math_locks)
            retain_split_input(source_content, locked_source)
            from mathbank.pdf_hybrid_request import prepare_pdf_task_plan, request_pdf_hybrid
            from mathbank.pdf_hybrid_plan import pdf_hybrid_plan_diagnostics
            source_assets = {}
            for page in layout_result.get('pages', []):
                for figure in page.get('figures', []):
                    url = figure.get('image_path')
                    if isinstance(url, str):
                        source_assets[url] = str(dependencies.resolve_upload_asset(url, uploads_dir=dependencies.UPLOAD_DIR, url_prefix=dependencies.upload_dir_rel))
            pdf_plan = prepare_pdf_task_plan(source_content, diagnostics, source_pages=source_pages, layout_result=layout_result, task_id=task_id, generation=0, source_document_sha256=dependencies.hashlib.sha256(file_bytes).hexdigest(), native_evidence=inspector_result.get('_native_source_review_evidence'), witnesses={index: value.get('_transcription_witness') for (index, value) in joint_page_results.items()}, transcript_normalizer=dependencies.process_ocr_illustrations, figure_assets=source_assets)
            diagnostics['pdf_hybrid'] = pdf_hybrid_plan_diagnostics(pdf_plan)
            pdf_preserved_indices = frozenset()
            if pdf_plan['mode'] in {'hybrid', 'whole_metadata'}:
                parse_model = dependencies.os.getenv('PREFER_PARSE_MODEL') or dependencies.os.getenv('DEEPSEEK_PARSE_MODEL', 'deepseek-flash')
                hybrid_result = request_pdf_hybrid(pdf_plan, dependencies.get_current_curriculum(), provider=dependencies.resolve_text_provider(parse_model), post=dependencies.post_chat_completion, diagnostics=diagnostics, normalize_fillin=dependencies.normalize_fillin_macro, task_id=task_id, generation=0, check_cancelled=check_pdf_cancelled, full_source_fallback=lambda : dependencies.parse_text(locked_source, False, diagnostics=diagnostics, preserve_source_answers=True, pdf_retry=False, connection_retry=False, check_cancelled=check_pdf_cancelled))
                parsed_questions = hybrid_result.questions
                pdf_preserved_indices = hybrid_result.preserved_indices
                diagnostics['pdf_hybrid']['partial'] = hybrid_result.partial
            else:
                parsed_questions = dependencies.parse_text(locked_source, False, diagnostics=diagnostics, preserve_source_answers=True, pdf_retry=True, check_cancelled=check_pdf_cancelled, report_attempt=report_pdf_split_attempt)
            dependencies.tasks.check_cancelled(task_id)
            staged = dependencies.copy.deepcopy(parsed_questions) if pdf_preserved_indices else parsed_questions
            diagnostics.update(dependencies.reconcile_math(staged, math_locks, source_content))
            if pdf_preserved_indices:
                for (index, candidate) in enumerate(staged):
                    if index not in pdf_preserved_indices:
                        parsed_questions[index] = candidate
                    elif candidate.get('source_review'):
                        parsed_questions[index]['source_review'] = candidate['source_review']
            dependencies.finalize_source_answers(parsed_questions, source_content)
            dependencies.apply_pdf_layout_reviews(parsed_questions, layout_result, diagnostics)
            dependencies.isolate_shared_pdf_figures(parsed_questions, layout_result, output_dir=dependencies.Path(dependencies.tmp_upload_dir), url_prefix=f'/{dependencies.upload_dir_rel}/tmp', register_asset=register_figure_asset, check_cancelled=check_layout_cancelled)
        else:
            pdf_preserved_indices = frozenset()
            retain_split_input(full_latex_content, full_latex_content)
            parsed_questions = dependencies.parse_text(full_latex_content, False, diagnostics=diagnostics, pdf_retry=True, check_cancelled=check_pdf_cancelled, report_attempt=report_pdf_split_attempt)
        dependencies.tasks.check_cancelled(task_id)
        final_questions = dependencies.postprocess(parsed_questions, paper_title, task_id, None if layout_result is not None else ocr_results, preserved_indices=pdf_preserved_indices)
        if layout_result is not None:
            from mathbank.pdf_symbol_risks import annotate_pdf_symbol_risks
            annotate_pdf_symbol_risks(final_questions, diagnostics)
            dependencies.refresh_pdf_review_items(final_questions, layout_result, diagnostics)
            if pdf_verify_suspicions and diagnostics.get('source_review_count'):
                dependencies.tasks.update(task_id, status='source_verification', progress=90, log='正在对照原页核验疑点，发现明确差异后将尝试修正并复核...', diagnostics=diagnostics)
                acquired = False
                try:
                    from mathbank.pdf_source_verify import verify_pdf_source_suspicions
                    while not acquired:
                        dependencies.tasks.check_cancelled(task_id)
                        acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                    diagnostics['pdf_source_verification'] = verify_pdf_source_suspicions(final_questions, diagnostics, page_urls, [number + 1 for number in target_page_indices], source_pages=source_pages, candidate_image_paths=list(temp_assets), progress=lambda message: dependencies.tasks.update(task_id, log=message), check_cancelled=lambda : dependencies.tasks.check_cancelled(task_id))
                except dependencies.TaskCancelled:
                    raise
                except Exception as exc:
                    diagnostics['pdf_source_verification'] = {'status': 'failed', 'pending': diagnostics.get('source_review_count', 0), 'notes': [f'原页核验未完成（{type(exc).__name__}），已保留拆题结果和原核对提示。']}
                finally:
                    if acquired:
                        dependencies.ocr_semaphore.release()
            else:
                diagnostics['pdf_source_verification'] = {'status': 'no_candidates' if pdf_verify_suspicions else 'disabled', 'calls': 0, 'checked': 0, 'confirmed': 0, 'pending': diagnostics.get('source_review_count', 0), 'skipped': 0, 'usage': {}}
        dependencies.make_source_review_advisory(final_questions, diagnostics)
        dependencies.tasks.check_cancelled(task_id)
        partial = bool(diagnostics.get('pdf_hybrid', {}).get('partial'))
        completion_log = f'PDF 已保留 {len(final_questions)} 道完整题目；部分疑点题组仍需校对，未处理范围已保留，可展开原文与未匹配题段核对。' if partial else '拆分完成，可选择题目导入；原文和配图说明可按需展开查看。'
        completed = dependencies.tasks.complete(task_id, log=completion_log, partial=partial, data=final_questions, generate_answers=generate_answers, page_images=list(page_urls), page_numbers=[number + 1 for number in target_page_indices], temp_assets=list(temp_assets), document_type='pdf', diagnostics=diagnostics)
        if not completed:
            dependencies.delete_temp_assets(temp_assets)
    except dependencies.TaskCancelled:
        dependencies.delete_temp_assets(temp_assets)
    except Exception as ex:
        error_code = ('ocr_configuration_required' if isinstance(ex, OCRConfigurationError)
                      else 'ocr_response_timeout' if isinstance(ex, OCRResponseTimeoutError)
                      else 'parse_configuration_required' if isinstance(ex, ParseConfigurationError)
                      else 'document_parse_failed')
        evidence = source_pages
        if evidence is None:
            evidence = [{'page_number': page_num + 1, 'markdown': str(ocr_results[index] or ''), 'status': 'completed' if ocr_results[index] else 'failed'} for (index, page_num) in enumerate(target_page_indices) if index < len(ocr_results)]
            evidence = evidence if sum((len(item['markdown']) for item in evidence)) <= 500000 else None
        dependencies.tasks.fail(task_id, f'PDF 智能拆解解析失败: {str(ex)}', document_type='pdf', error_code=error_code, diagnostics=dependencies.copy.deepcopy(diagnostics), pdf_source_pages=evidence, page_images=list(page_urls), page_numbers=[number + 1 for number in target_page_indices], temp_assets=list(temp_assets))
    finally:
        tmp_pdf_path.unlink(missing_ok=True)
