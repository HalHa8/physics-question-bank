"""Explicit task-scoped dependencies; no import of main or duplicate runtime state."""

from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore
from typing import Callable

from mathbank.task_manager import TaskManager


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
