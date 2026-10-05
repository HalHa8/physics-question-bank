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
            bindings.services[name] = bindings.bind(getattr(module, name), contract)

    state.TMP_UPLOAD_DIR = os.path.join(state.UPLOAD_DIR, "tmp")
    state._SHUTDOWN_SCHEDULED = threading.Event()
    state._SHUTDOWN_SCHEDULE_LOCK = threading.Lock()
    state.PDF_OCR_SEMAPHORE = threading.BoundedSemaphore(4)
    state.DOCUMENT_TASKS = TaskManager(
        max_workers=2, max_queue=4, terminal_ttl_seconds=3600,
        temp_asset_cleanup=lambda paths: bindings.resolve("_delete_task_temp_assets")(paths),
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
    app.mount("/static", StaticFiles(directory=str(defaults.STATIC_DIR)), name="static")
    return bindings


def initialize_runtime(bindings):
    state = bindings.state
    try:
        defaults.load_dotenv(defaults.ENV_FILE)
        defaults.harden_private_path(defaults.ENV_FILE)
        # The legacy entry loaded .env before deriving its instance identity.
        launch_id = os.environ.get("MATHBANK_LAUNCH_ID", "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{32}", launch_id):
            state.SERVER_INSTANCE_ID = launch_id
        # Acquire the restore lock before the first database access, as before.
        state._RUNTIME_LOCK = None if state.IS_TESTING else defaults.acquire_runtime_lock()
        if state._RUNTIME_LOCK is not None:
            atexit.register(state._RUNTIME_LOCK.close)
        defaults.init_db()
        os.makedirs(state.UPLOAD_DIR, exist_ok=True)
        os.makedirs(state.TMP_UPLOAD_DIR, exist_ok=True)
        state.LOCAL_TOKEN = bindings.resolve("load_or_create_local_token")()
        bindings.resolve("load_or_init_metadata")()
        bindings.resolve("print_startup_diagnostics")()
    except BaseException:
        state.DOCUMENT_TASKS.shutdown(wait=False)
        if state._RUNTIME_LOCK is not None:
            state._RUNTIME_LOCK.close()
        raise
