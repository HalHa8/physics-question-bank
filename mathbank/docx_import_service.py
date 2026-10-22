"""Document orchestration; runtime and all external callbacks are injected."""
from mathbank.document_import_context import DocumentImportDependencies

def run_docx_parsing_task(task_id: str, file_bytes: bytes, filename: str, generate_answers: bool=False, docx_verify_suspicions: bool=False, resume_state: dict | None=None, *, dependencies: DocumentImportDependencies):
    temp_assets = []
    diagnostics = {}
    try:
        dependencies.tasks.check_cancelled(task_id)
        dependencies.tasks.update(task_id, status='extracting_docx', progress=25, log='已接收 Word 试卷，正在安全提取 OMML 公式、文字与配图...', document_type='docx', temp_assets=[])
        docx_res = dependencies.extract_docx(file_bytes, output_dir=dependencies.tmp_upload_dir, url_prefix=f'/{dependencies.upload_dir_rel}/tmp', asset_prefix=f'word_{task_id}', include_source_asset_evidence=True, include_source_review_evidence=True)
        temp_assets = docx_res.get('image_paths', [])
        if not docx_res.get('success') or not docx_res.get('markdown'):
            raise ValueError(docx_res.get('error') or '未能从 Word 文档中提取出有效试题内容！')
        full_markdown_content = docx_res['markdown']
        img_count = docx_res.get('image_count', 0)
        diagnostics = docx_res.get('diagnostics', {})
        extraction_diagnostics = dependencies.copy.deepcopy(diagnostics)
        extraction_review_evidence = docx_res.get('_source_review_evidence')
        source_document_sha256 = dependencies.hashlib.sha256(file_bytes).hexdigest()
        diagnostics['word_extraction_warnings'] = list(diagnostics.get('warnings', []))
        converted_count = diagnostics.get('omml_converted', 0) + diagnostics.get('mtef_converted', 0)
        review_count = diagnostics.get('review_required', 0)
        extraction_log = f'Word 提取完成：{converted_count} 个公式已转换，{img_count} 张图片已保留' + ((f'，{review_count} 处提取疑点将在拆题后自动核验。' if docx_verify_suspicions else f'，{review_count} 处提取疑点，自动核验已关闭。') if review_count else '。')
        dependencies.tasks.check_cancelled(task_id)
        dependencies.tasks.update(task_id, status='ai_splitting', progress=70, log=extraction_log + ' 正在调用教研模型拆题...', document_type='docx', diagnostics=diagnostics, temp_assets=list(temp_assets))
        task_options = (dependencies.tasks.snapshot(task_id) or {}).get('document_input', {}).get('options', {})
        paper_title = task_options.get('paper_title') or dependencies.os.path.splitext(filename)[0]
        auto_title = dependencies.extract_title_from_latex(full_markdown_content)
        if auto_title and (not task_options.get('paper_title')):
            paper_title = auto_title
        (locked_markdown_content, math_locks) = dependencies.lock_visible_math(full_markdown_content, task_id.replace('-', '')[:16])
        diagnostics['math_locks_created'] = len(math_locks)
        dependencies.tasks.check_cancelled(task_id)
        from mathbank.word_hybrid_plan import build_word_hybrid_plan, word_hybrid_plan_diagnostics
        from mathbank.word_hybrid_request import request_word_hybrid
        hybrid_plan = None
        preserved_indices = frozenset()
        if docx_res.get('_source_review_evidence') is not None:
            hybrid_plan = build_word_hybrid_plan(full_markdown_content, diagnostics, task_id=task_id, generation=0, source_document_sha256=dependencies.hashlib.sha256(file_bytes).hexdigest(), min_metadata_source_fraction=0.5, asset_evidence=docx_res.get('_source_asset_evidence'), source_review_evidence=docx_res.get('_source_review_evidence'))
            diagnostics['word_hybrid'] = word_hybrid_plan_diagnostics(hybrid_plan)
        source_plan = None
        try:
            source_plan = dependencies.prepare_word_source_metadata(full_markdown_content, diagnostics, asset_evidence=docx_res.get('_source_asset_evidence'))
            if hybrid_plan is not None:
                if hybrid_plan['mode'] == 'whole_metadata':
                    source_plan = hybrid_plan['_whole_source_metadata_plan']
                elif source_plan['eligible']:
                    source_plan['eligible'] = False
                    source_plan['fallback_reasons'] = hybrid_plan['global_reasons'] or ['native_scope_not_whole_reliable']
            diagnostics['word_source_metadata'] = dependencies.source_metadata_diagnostics(source_plan)
        except Exception as exc:
            diagnostics['word_source_metadata'] = {'status': 'fallback', 'eligible': False, 'calls': 0, 'error_type': type(exc).__name__}
        parsed_questions = None
        if resume_state:
            if resume_state.get('source_sha256') != source_document_sha256:
                raise ValueError('Word 原文件已变化，不能复用旧拆题结果。')
            if resume_state.get('source_markdown') != full_markdown_content:
                raise ValueError('Word 提取内容已变化，不能复用旧拆题结果。')
            parsed_questions = dependencies.copy.deepcopy(resume_state.get('split_questions'))
            preserved_indices = frozenset(resume_state.get('preserved_indices', []))
        if parsed_questions is None and hybrid_plan is not None and (hybrid_plan['mode'] == 'hybrid'):
            parse_model = dependencies.os.getenv('PREFER_PARSE_MODEL') or dependencies.os.getenv('DEEPSEEK_PARSE_MODEL', 'deepseek-flash')
            result = request_word_hybrid(hybrid_plan, dependencies.get_current_curriculum(), provider=dependencies.resolve_text_provider(parse_model), post=dependencies.post_chat_completion, diagnostics=diagnostics, normalize_fillin=dependencies.normalize_fillin_macro, task_id=task_id, generation=0, check_cancelled=lambda : dependencies.tasks.check_cancelled(task_id), full_source_fallback=lambda : dependencies.parse_text(locked_markdown_content, False, diagnostics=diagnostics, preserve_source_answers=True, connection_retry=False, check_cancelled=lambda : dependencies.tasks.check_cancelled(task_id)))
            parsed_questions = result.questions
            preserved_indices = result.preserved_indices
            diagnostics['word_hybrid']['partial'] = result.partial
        if parsed_questions is None and source_plan is not None and source_plan['eligible']:
            parse_model = dependencies.os.getenv('PREFER_PARSE_MODEL') or dependencies.os.getenv('DEEPSEEK_PARSE_MODEL', 'deepseek-flash')
            try:
                parsed_questions = dependencies.request_word_source_metadata(source_plan, dependencies.get_current_curriculum(), provider=dependencies.resolve_text_provider(parse_model), post=dependencies.post_chat_completion, diagnostics=diagnostics, normalize_fillin=dependencies.normalize_fillin_macro, check_cancelled=lambda : dependencies.tasks.check_cancelled(task_id))
            except dependencies.TaskCancelled:
                raise
            except dependencies.SourceMetadataPermanentHTTPError:
                raise
            except Exception as exc:
                diagnostics['word_source_metadata'].update(status='fallback', error_type=type(exc).__name__)
                if diagnostics['word_source_metadata'].get('calls', 0):
                    raise ValueError('Word 拆题响应未通过校验；原文件已保留，请手动重试，未自动追加付费请求。') from exc
        if parsed_questions is None:
            dependencies.tasks.check_cancelled(task_id)
            fallback_kwargs = {'connection_retry': False, 'check_cancelled': lambda : dependencies.tasks.check_cancelled(task_id)}
            parsed_questions = dependencies.parse_text(locked_markdown_content, False, diagnostics=diagnostics, preserve_source_answers=True, **fallback_kwargs)
        word_source_cache = {'source_markdown': full_markdown_content, 'split_questions': parsed_questions, 'source_sha256': dependencies.hashlib.sha256(file_bytes).hexdigest(), 'preserved_indices': sorted(preserved_indices)}
        dependencies.tasks.update(task_id, docx_resume_state=dependencies.copy.deepcopy(word_source_cache))
        if len(dependencies.json.dumps(word_source_cache, ensure_ascii=False)) <= 500000:
            dependencies.tasks.update(task_id, docx_source_cache=dependencies.copy.deepcopy(word_source_cache))
        staged = dependencies.copy.deepcopy(parsed_questions) if preserved_indices else parsed_questions
        lock_report = dependencies.reconcile_math(staged, math_locks, full_markdown_content)
        if preserved_indices:
            for (index, candidate) in enumerate(staged):
                if index not in preserved_indices:
                    parsed_questions[index] = candidate
                    continue
                original = parsed_questions[index]
                changed = any((original.get(field) != candidate.get(field) for field in ('content', 'answer_markdown')))
                if candidate.get('source_review'):
                    original['source_review'] = candidate['source_review']
                if changed:
                    review = original.setdefault('source_review', {})
                    review['required'] = True
                    review.setdefault('reasons', []).append('全卷来源比对未唯一对应，已保留局部认证原文，请对照原卷核对。')
        previous_warnings = list(diagnostics.get('warnings', []))
        diagnostics.update(lock_report)
        diagnostics['warnings'] = previous_warnings + lock_report.get('warnings', [])
        dependencies.finalize_source_answers(parsed_questions, full_markdown_content)
        diagnostics['source_review_count'] = sum((bool(q.get('source_review', {}).get('required')) for q in parsed_questions))
        dependencies.tasks.check_cancelled(task_id)
        if preserved_indices:
            final_questions = dependencies.postprocess(parsed_questions, paper_title, task_id, [full_markdown_content], preserved_indices=preserved_indices)
        elif diagnostics['word_source_metadata'].get('status') == 'used':
            final_questions = dependencies.postprocess(parsed_questions, paper_title, task_id, [full_markdown_content], source_body_preserved=True)
        else:
            final_questions = dependencies.postprocess(parsed_questions, paper_title, task_id, [full_markdown_content])
        dependencies.prepare_word_extraction_reviews(final_questions, diagnostics, full_markdown_content, extraction_diagnostics=extraction_diagnostics, source_review_evidence=extraction_review_evidence, source_document_sha256=source_document_sha256)
        if docx_verify_suspicions and diagnostics.get('source_review_count'):

            def check_word_cancelled():
                dependencies.tasks.check_cancelled(task_id)

            def register_word_page(path):
                temp_assets.append(path)
                dependencies.tasks.update(task_id, temp_assets=list(temp_assets))
            dependencies.tasks.update(task_id, status='source_verification', progress=90, log='正在将原 Word 渲染成页面，仅对剩余疑点进行原文核验...', diagnostics=diagnostics)
            acquired = False
            try:
                from mathbank.docx_source_evidence import prepare_docx_source_evidence
                from mathbank.docx_source_verify import verify_docx_source_suspicions
                evidence = prepare_docx_source_evidence(file_bytes, output_dir=dependencies.Path(dependencies.tmp_upload_dir), url_prefix=f'/{dependencies.upload_dir_rel}/tmp', task_id=task_id, register_asset=register_word_page, check_cancelled=check_word_cancelled)
                dependencies.tasks.update(task_id, docx_source_evidence=evidence)
                while not acquired:
                    check_word_cancelled()
                    acquired = dependencies.ocr_semaphore.acquire(timeout=0.25)
                diagnostics['docx_source_verification'] = verify_docx_source_suspicions(final_questions, diagnostics, full_markdown_content, evidence, candidate_image_paths=list(temp_assets), progress=lambda message: dependencies.tasks.update(task_id, log=message), check_cancelled=check_word_cancelled)
            except dependencies.TaskCancelled:
                raise
            except Exception as exc:
                pending = sum((bool(q.get('source_review', {}).get('required')) for q in final_questions))
                diagnostics['source_review_count'] = pending
                diagnostics['docx_source_verification'] = {'status': 'failed', 'pending': pending, 'notes': [f'原文核验未完成（{type(exc).__name__}），已保留拆题结果和原核对提示。']}
            finally:
                if acquired:
                    dependencies.ocr_semaphore.release()
        else:
            diagnostics['docx_source_verification'] = {'status': 'no_candidates' if docx_verify_suspicions else 'disabled', 'calls': 0, 'checked': 0, 'confirmed': 0, 'pending': diagnostics.get('source_review_count', 0), 'usage': {}}
        dependencies.finalize_word_extraction_reviews(final_questions, diagnostics, full_markdown_content, extraction_diagnostics=extraction_diagnostics, source_review_evidence=extraction_review_evidence, source_document_sha256=source_document_sha256)
        dependencies.separate_formula_notices(final_questions, preserve_missing=True)
        dependencies.make_source_review_advisory(final_questions, diagnostics)
        diagnostics['import_classification'] = dependencies.summarize_import_classifications(final_questions)
        dependencies.tasks.check_cancelled(task_id)
        partial = bool(diagnostics.get('word_hybrid', {}).get('partial'))
        completion_log = f'Word 已保留 {len(final_questions)} 道完整题目；部分疑点题组仍需校对，未处理范围已保留，可展开原文与未匹配题段核对。' if partial else 'Word 拆分完成，可选择题目导入；原文说明可按需展开查看。'
        completed = dependencies.tasks.complete(task_id, log=completion_log, partial=partial, data=final_questions, generate_answers=generate_answers, document_type='docx', diagnostics=diagnostics, temp_assets=list(temp_assets))
        if not completed:
            dependencies.delete_temp_assets(temp_assets)
    except dependencies.TaskCancelled:
        dependencies.delete_temp_assets(temp_assets)
    except Exception as ex:
        dependencies.delete_temp_assets(temp_assets)
        dependencies.tasks.fail(task_id, f'Word 试卷拆解失败: {str(ex)}', document_type='docx', diagnostics=diagnostics)
