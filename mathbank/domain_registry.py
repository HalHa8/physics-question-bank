"""Explicit domain registration; no import of the compatibility entry point."""

from mathbank import knowledge_point_service
from mathbank import maintenance_service
from mathbank import runtime_service
from mathbank import system_routes
from mathbank import image_upload_service
from mathbank import image_import_service
from mathbank import ocr_service
from mathbank import drawing_service
from mathbank import solve_service
from mathbank import settings_service
from mathbank import question_queries
from mathbank import question_commands
from mathbank import curriculum_service
from mathbank import classification_service
from mathbank import paper_parse_service
from mathbank import question_asset_service
from mathbank import document_task_service
from mathbank import paper_selection_service
from mathbank import paper_record_service
from mathbank import paper_export_service
from mathbank import library_transfer_service
from mathbank import document_project_runtime

DOMAINS = (
    (knowledge_point_service, knowledge_point_service.KnowledgePointServiceDependencies, (
        'get_knowledge_points',
        'add_knowledge_point',
    )),
    (maintenance_service, maintenance_service.MaintenanceServiceDependencies, (
        'schedule_database_export',
        'schedule_question_fingerprint_retry',
        'print_startup_diagnostics',
        'print_optional_tool_diagnostics',
        'heal_database_curriculum_names',
        'clean_orphaned_images',
        'recalibrate_usage_counts',
        'start_startup_cleanup',
        '_report_database_export_error',
    )),
    (runtime_service, runtime_service.RuntimeServiceDependencies, (
        'load_or_create_local_token',
        'app_lifespan',
        'security_and_heartbeat_middleware',
        'api_heartbeat',
        'watchdog_loop',
        'shutdown_server',
    )),
    (system_routes, system_routes.SystemRoutesDependencies, (
        'healthz',
        'read_index',
        'read_favicon',
        'read_favicon_svg',
        'read_apple_touch_icon',
        'format_fraction_style',
        'get_version_info',
        'check_version_update',
        'get_pandoc_runtime_status',
        'install_pandoc_runtime',
        'get_pandoc_install_status',
    )),
    (image_upload_service, image_upload_service.ImageUploadServiceDependencies, (
        'upload_image',
        'auto_crop_image',
        'upload_tex_source',
        'upload_batch_images',
        'upload_markdown_source',
    )),
    (ocr_service, ocr_service.OcrServiceDependencies, (
        'ocr_via_provider',
        'ocr_formula',
        'ocr_pdf_page_image',
    )),
    (drawing_service, drawing_service.DrawingServiceDependencies, (
        'extract_tikz_source',
        'request_tikz_completion',
        'draw_tikz_via_high_model',
        'compile_tikz_to_png',
        'render_tikz_endpoint',
        'correct_tikz_endpoint',
        'draw_tikz_workbench_endpoint',
        'draw_tikz_from_image_endpoint',
    )),
    (solve_service, solve_service.SolveServiceDependencies, (
        'ai_solve',
    )),
    (settings_service, settings_service.SettingsServiceDependencies, (
        'get_settings',
        'save_settings',
    )),
    (question_queries, question_queries.QuestionQueriesDependencies, (
        'get_seq_mapping',
        'list_questions',
        '_duplicate_payload_list',
        '_duplicate_input_from_payload',
        '_prompt_visible_image_paths',
        'check_question_duplicates',
        'get_question',
        'get_db_stats',
        'list_categories',
        'get_sources',
        'list_association_candidates',
    )),
    (question_commands, question_commands.QuestionCommandsDependencies, (
        'committed_question_response',
        'prepare_question_assets',
        'build_prepared_question_fingerprint',
        'duplicate_review_required_response',
        'create_question',
        'update_question',
        'update_question_figure_align',
        'update_question_figure_layout',
        'get_associated_questions',
        'associate_questions_endpoint',
        'remove_association',
        'delete_question',
    )),
    (curriculum_service, curriculum_service.CurriculumServiceDependencies, (
        'get_current_curriculum',
        'load_or_init_metadata',
        'get_active_version_code',
        'get_metadata_config',
        'get_curriculum_preset_config',
        'route_chapter',
        'save_metadata_config',
        'curriculum_filter_expression',
        'apply_curriculum_filters',
        'require_expected_curriculum_version',
        'get_sub_knowledge_config',
        '_save_metadata_config',
    )),
    (classification_service, classification_service.ClassificationServiceDependencies, (
        'ai_classify',
    )),
    (paper_parse_service, paper_parse_service.PaperParseServiceDependencies, (
        'parse_paper_text_internal',
        'ai_parse_paper',
        'validate_import_knowledge',
    )),
    (question_asset_service, question_asset_service.QuestionAssetServiceDependencies, (
        'rollback_question_asset_promotions',
        '_referenced_question_assets',
        'delete_unreferenced_question_assets',
        'promote_question_temp_assets',
        '_delete_task_temp_assets',
    )),
    (document_task_service, document_task_service.DocumentTaskServiceDependencies, (
        'build_document_import_dependencies',
        'manual_crop_pdf',
        'post_process_pdf_parsed_questions',
        'run_pdf_parsing_task',
        'upload_pdf_task',
        'run_docx_parsing_task',
        'upload_docx_task',
        'get_pdf_task_status',
        'cancel_pdf_task',
        'clear_temp_crops',
        '_document_request_id',
        '_document_curriculum_sha256',
        '_register_document_input',
        '_document_status',
        '_manual_crop_pdf_impl',
        '_queue_document_upload',
        'get_document_task_by_request',
        'cancel_document_task_by_request',
        'resume_document_task',
        '_read_document_source',
        'download_document_source',
        'retain_document_task',
    )),
    (paper_selection_service, paper_selection_service.PaperSelectionServiceDependencies, (
        'ai_select_paper',
    )),
    (paper_record_service, paper_record_service.PaperRecordServiceDependencies, (
        'get_paper_questions',
        'save_paper',
        'list_papers',
        'get_paper_detail',
        'delete_paper',
    )),
    (paper_export_service, paper_export_service.PaperExportServiceDependencies, (
        '_prepare_paper_export_questions',
        'export_paper_tex',
        'export_paper_bundle',
        'explain_latex_compile_error',
        'export_paper_pdf',
        'export_paper_word',
        'get_paper_export_preflight',
    )),
    (library_transfer_service, library_transfer_service.LibraryTransferServiceDependencies, (
        'preview_library_transfer',
        'select_library_transfer_ids',
        'export_library_transfer',
        'import_library_transfer',
        '_sharing_backup',
        '_sharing_post_commit_export',
        '_check_library_import_storage',
        '_run_library_import_task',
        '_run_library_export_task',
        '_library_transfer_tasks',
        '_receive_library_archive',
        '_transfer_task_http_error',
        'start_library_import_task',
        'start_library_export_task',
        'get_library_transfer_task',
        'download_library_transfer_task',
    )),
    (document_project_runtime, document_project_runtime.DocumentProjectRuntimeDependencies, (
        '_document_project_service',
        '_sync_document_project',
        '_restore_document_project_asset',
        '_dispatch_document_project',
        '_release_document_project_assets',
        '_maintain_document_projects',
    )),
    (image_import_service, image_import_service.ImageImportServiceDependencies, ('upload_image_task',)),
)
