"""Explicit task-scoped dependencies; no import of main or duplicate runtime state."""

from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore
from typing import Callable

from mathbank.task_manager import TaskManager
from mathbank.ai_providers import resolve_text_provider
from mathbank.ai_http import post_chat_completion


@dataclass(frozen=True)
class DocumentImportDependencies:
    tasks: TaskManager
    ocr_semaphore: BoundedSemaphore
    tmp_upload_dir: str | Path
    upload_dir_rel: str
    max_pdf_pages: int
    inspect_pdf: Callable[..., dict]
    ocr_page: Callable[[str], str]
    parse_text: Callable[..., list]
    postprocess: Callable[..., list]
    delete_temp_assets: Callable[[list], int]
    extract_docx: Callable[..., dict]
    reconcile_math: Callable[..., dict]

    # New source-only/recovery callbacks; no mutable module-level runtime.
    state: object
    DOCUMENT_AI_TIMEOUT_SECONDS: object
    PAPER_SPLIT_CACHE_MAX_CHARACTERS: object
    PAPER_SPLIT_TIMEOUT_SECONDS: object
    PDF_STRATEGIES: object
    Path: object
    SourceMetadataPermanentHTTPError: object
    TaskCancelled: object
    UPLOAD_DIR: object
    apply_pdf_layout_reviews: object
    collected_usage: object
    copy: object
    enrich_pdf_with_figures: object
    extract_title_from_latex: object
    finalize_source_answers: object
    finalize_word_extraction_reviews: object
    get_current_curriculum: object
    hashlib: object
    inspect_pdf_page: object
    isolate_shared_pdf_figures: object
    iter_completed_futures: object
    json: object
    lock_visible_math: object
    make_source_review_advisory: object
    merge_pdf_page_texts: object
    normalize_fillin_macro: object
    os: object
    parse_page_range: object
    post_chat_completion: object
    prepare_word_extraction_reviews: object
    prepare_word_source_metadata: object
    process_ocr_illustrations: object
    re: object
    refresh_pdf_review_items: object
    request_word_source_metadata: object
    resolve_text_provider: object
    resolve_upload_asset: object
    separate_formula_notices: object
    source_metadata_diagnostics: object
    summarize_import_classifications: object
    threading: object
