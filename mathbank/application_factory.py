"""Assemble the API and initialize its one runtime at an explicit entry point."""

import atexit
import os
import re
import sys
import threading
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mathbank import application_imports as defaults
from mathbank.api_routes import register_routes
from mathbank.application_bindings import ApplicationBindings
from mathbank.application_state import RuntimeState
from mathbank.domain_registry import DOMAINS
from mathbank.task_manager import TaskManager
from mathbank.asset_lifecycle import register_asset_store, RetainedUploadStaticFiles, serialize_asset_lifecycle
from mathbank.paths import RETAINED_UPLOADS_DIR


def create_application(*, initialize=True, state=None):
    """initialize=False supports source/contract tests without disk mutations."""
    if state is None:
        testing = "pytest" in sys.modules or any("pytest" in arg for arg in sys.argv)
        launch_id = os.environ.get("MATHBANK_LAUNCH_ID", "").strip().lower()
        state = RuntimeState(
            IS_TESTING=testing,
            SERVER_INSTANCE_ID=launch_id if re.fullmatch(r"[0-9a-f]{32}", launch_id) else uuid.uuid4().hex,
            LAST_ACTIVE_TIME=time.time(),
            UPLOAD_DIR_REL="static/test_uploads" if testing else "static/uploads",
            UPLOAD_DIR=str(defaults.TEST_UPLOADS_DIR if testing else defaults.UPLOADS_DIR),
            METADATA_FILE=str(defaults.DATA_BACKUP_DIR / (
                "custom_metadata_test.json" if testing else "custom_metadata.json")),
        )
    bindings = ApplicationBindings(state, defaults)
    for module, contract, names in DOMAINS:
        for name in names:
            function = getattr(module, name)
            if name in {"create_question", "update_question", "delete_question", "clean_orphaned_images",
                        "promote_question_temp_assets", "rollback_question_asset_promotions",
                        "delete_unreferenced_question_assets", "_delete_task_temp_assets"}:
                function = serialize_asset_lifecycle(function)
            bindings.services[name] = bindings.bind(function, contract)

    state.TMP_UPLOAD_DIR = os.path.join(state.UPLOAD_DIR, "tmp")
    state._SHUTDOWN_SCHEDULED = threading.Event()
    state._SHUTDOWN_SCHEDULE_LOCK = threading.Lock()
    state._METADATA_SAVE_LOCK = threading.RLock()
    state._LIBRARY_TRANSFER_TASKS_LOCK = threading.Lock()
    state._DOCUMENT_PROJECT_STOP = threading.Event()
    state.PDF_OCR_CAPACITY = defaults.PdfOcrCapacity(defaults.configured_pdf_ocr_concurrency())
    state.PDF_OCR_SEMAPHORE = state.PDF_OCR_CAPACITY.auxiliary
    state.DATABASE_EXPORT_QUEUE = defaults.DatabaseExportQueue(
        lambda: bindings.resolve("export_database_to_files")(),
        on_error=lambda exc, operation: bindings.resolve("_report_database_export_error")(exc, operation))
    # Durable storage is opened only after acquiring the restore/runtime lock.
    state.DOCUMENT_TASK_STORE = None
    state.DOCUMENT_PROJECTS = None
    state.DOCUMENT_TASKS = defaults.DurableDocumentTasks(
        store=state.DOCUMENT_TASK_STORE,
        transient_document_types={"pdf"} if state.PDF_CLOUD_ONLY else (),
        on_snapshot=lambda task_id, snapshot: bindings.resolve("_sync_document_project")(task_id, snapshot),
        max_workers=2, max_queue=4, terminal_ttl_seconds=3600,
        temp_asset_cleanup=lambda paths: bindings.resolve("_delete_task_temp_assets")(paths),
        record_cleanup=lambda task_id: state.DOCUMENT_TASK_INPUTS.pop(task_id, None),
    )
    # P remains the default; legacy mathematics trees are data-compatibility only.
    for name, code in (("PHYSICS_CURRICULUM", "P"), ("RENJIAO_A_CURRICULUM", "A"),
                       ("RENJIAO_B_CURRICULUM", "B"), ("SUJIAO_CURRICULUM", "S"),
                       ("HUJIAO_CURRICULUM", "H")):
        setattr(state, name, defaults.load_curriculum(code))

    if initialize:
        initialize_runtime(bindings)

    app = FastAPI(title="本地化物理题库管理系统 API", lifespan=bindings.resolve("app_lifespan"))
    bindings.app = app
    app.state.runtime = state
    app.state.bindings = bindings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1", "http://localhost"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    app.middleware("http")(bindings.resolve("security_and_heartbeat_middleware"))
    register_routes(app, bindings.resolve)
    app.mount("/static", defaults.RetainedUploadStaticFiles(directory=str(defaults.STATIC_DIR),
        uploads_dir=state.UPLOAD_DIR, url_prefix=state.UPLOAD_DIR_REL), name="static")
    return bindings


def initialize_runtime(bindings):
    state = bindings.state
    try:
        if not state.IS_TESTING:
            defaults.check_startup_storage(defaults.PROJECT_ROOT)
        defaults.load_dotenv(defaults.ENV_FILE)
        defaults.harden_private_path(defaults.ENV_FILE)
        # Read concurrency only after loading this installation's environment.
        state.PDF_OCR_CAPACITY = defaults.PdfOcrCapacity(defaults.configured_pdf_ocr_concurrency())
        state.PDF_OCR_SEMAPHORE = state.PDF_OCR_CAPACITY.auxiliary
        # The legacy entry loaded .env before deriving its instance identity.
        launch_id = os.environ.get("MATHBANK_LAUNCH_ID", "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{32}", launch_id):
            state.SERVER_INSTANCE_ID = launch_id
        # Acquire the restore lock before the first database access, as before.
        state._RUNTIME_LOCK = None if state.IS_TESTING else defaults.acquire_runtime_lock()
        if state._RUNTIME_LOCK is not None:
            atexit.register(state._RUNTIME_LOCK.close)
        defaults.init_db()
        if not state.IS_TESTING:
            state.DOCUMENT_TASK_STORE = defaults.DocumentTaskStore(defaults.DOCUMENT_TASKS_DIR)
            state.DOCUMENT_PROJECTS = defaults.DocumentProjectStore(defaults.DOCUMENT_PROJECTS_DIR)
            state.DOCUMENT_TASKS.shutdown(wait=False)
            state.DOCUMENT_TASKS = defaults.DurableDocumentTasks(
                store=state.DOCUMENT_TASK_STORE,
                transient_document_types={"pdf"} if state.PDF_CLOUD_ONLY else (),
                on_snapshot=lambda task_id, snapshot: bindings.resolve("_sync_document_project")(task_id, snapshot),
                max_workers=2, max_queue=4, terminal_ttl_seconds=3600,
                temp_asset_cleanup=lambda paths: bindings.resolve("_delete_task_temp_assets")(paths),
                record_cleanup=lambda task_id: state.DOCUMENT_TASK_INPUTS.pop(task_id, None))
        os.makedirs(state.UPLOAD_DIR, exist_ok=True)
        os.makedirs(state.TMP_UPLOAD_DIR, exist_ok=True)
        defaults.register_asset_store(state.UPLOAD_DIR,
            defaults.RETAINED_UPLOADS_DIR / ("test" if state.IS_TESTING else "uploads"))
        state.LOCAL_TOKEN = bindings.resolve("load_or_create_local_token")()
        bindings.resolve("load_or_init_metadata")()
        bindings.resolve("print_startup_diagnostics")()
    except BaseException:
        state.DOCUMENT_TASKS.shutdown(wait=False)
        state.DATABASE_EXPORT_QUEUE.close(wait=False)
        if state._RUNTIME_LOCK is not None:
            state._RUNTIME_LOCK.close()
        raise
