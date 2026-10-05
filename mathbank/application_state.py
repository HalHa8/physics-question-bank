"""One application-owned runtime state, never initialized at module import."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeState:
    IS_TESTING: bool = False
    SERVER_INSTANCE_ID: str = ""
    LOCAL_TOKEN: str = ""
    LAST_ACTIVE_TIME: float = 0.0
    UPLOAD_DIR: str = ""
    UPLOAD_DIR_REL: str = ""
    TMP_UPLOAD_DIR: str = ""
    METADATA_FILE: str = ""
    METADATA_CACHE: dict = field(default_factory=dict)
    PHYSICS_CURRICULUM: dict = field(default_factory=dict)
    RENJIAO_A_CURRICULUM: dict = field(default_factory=dict)
    RENJIAO_B_CURRICULUM: dict = field(default_factory=dict)
    SUJIAO_CURRICULUM: dict = field(default_factory=dict)
    HUJIAO_CURRICULUM: dict = field(default_factory=dict)
    MAX_PDF_TASK_PAGES: int = 80
    DOCUMENT_TASKS: Any = None
    PDF_OCR_SEMAPHORE: Any = None
    _RUNTIME_LOCK: Any = None
    _SHUTDOWN_SCHEDULED: Any = None
    _SHUTDOWN_SCHEDULE_LOCK: Any = None
