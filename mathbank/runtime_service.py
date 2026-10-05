"""Runtime service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header


@dataclass(frozen=True)
class RuntimeServiceDependencies:
    state: RuntimeState
    HTTPException: Any
    JSONResponse: Any
    SYSTEM_GENERATED_DIR: Any
    harden_private_path: Any
    os: Any
    secrets: Any
    signal: Any
    start_startup_cleanup: Callable
    threading: Any
    time: Any
    write_private_text_atomic: Any


def load_or_create_local_token(*, dependencies: RuntimeServiceDependencies) -> str:
    token_dir = str(dependencies.SYSTEM_GENERATED_DIR)
    dependencies.os.makedirs(token_dir, exist_ok=True)
    dependencies.harden_private_path(token_dir, directory=True)
    token_file = dependencies.os.path.join(token_dir, "local_token")
    if dependencies.os.path.exists(token_file):
        try:
            dependencies.harden_private_path(token_file)
            with open(token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token and len(token) >= 16:
                    return token
        except Exception as e:
            print(f"[Security] Failed to read persistent token: {e}")

    # Generate new token
    token = dependencies.secrets.token_hex(16)
    try:
        dependencies.write_private_text_atomic(token_file, token)
    except Exception as e:
        print(f"[Security] Failed to write persistent token: {e}")
    return token


@asynccontextmanager
async def app_lifespan(_app: FastAPI, *, dependencies: RuntimeServiceDependencies):
    """在模块完整导入后再启动低优先级维护任务。"""

    if dependencies.state.IS_TESTING:
        yield
        return

    dependencies.state.DOCUMENT_TASKS.start_maintenance(interval_seconds=60.0)
    dependencies.threading.Thread(
        target=dependencies.start_startup_cleanup,
        name="mathbank-post-startup-maintenance",
        daemon=True,
    ).start()
    try:
        yield
    finally:
        dependencies.state.DOCUMENT_TASKS.shutdown(wait=False)


async def security_and_heartbeat_middleware(request: Request, call_next, *, dependencies: RuntimeServiceDependencies):
    pass  # State lives on the application instance.
    dependencies.state.LAST_ACTIVE_TIME = dependencies.time.time()

    # Verify local security token for modifying operations
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.url.path != "/api/heartbeat":
            token = request.headers.get("X-Local-Token")
            if not token or not dependencies.secrets.compare_digest(token, dependencies.state.LOCAL_TOKEN):
                print(f"[Security Alert] Blocked {request.method} {request.url.path} - invalid local token")
                return dependencies.JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "Forbidden: Invalid or missing local token."}
                )

    response = await call_next(request)
    return response


def api_heartbeat(*, dependencies: RuntimeServiceDependencies):
    pass  # State lives on the application instance.
    dependencies.state.LAST_ACTIVE_TIME = dependencies.time.time()
    return {"status": "success", "timestamp": dependencies.state.LAST_ACTIVE_TIME}


def watchdog_loop(*, dependencies: RuntimeServiceDependencies):
    pass  # State lives on the application instance.
    # 1小时闲置超时 (3600秒)
    TIMEOUT_LIMIT = 3600
    while True:
        dependencies.time.sleep(15) # 每 15 秒轻量巡检一次
        elapsed = dependencies.time.time() - dependencies.state.LAST_ACTIVE_TIME
        if elapsed > TIMEOUT_LIMIT:
            print(f"[Watchdog] 检测到网页已关闭且超过 1 小时无任何动作 (已静默 {int(elapsed)} 秒)，正在自动安全关闭题库程序...")
            # 进程内触发 SIGINT，让 uvicorn 执行正常 lifespan 关闭。
            dependencies.signal.raise_signal(dependencies.signal.SIGINT)
            break


def shutdown_server(x_mathbank_launch_id: str | None=Header(None, alias='X-MathBank-Launch-ID'), *, dependencies: RuntimeServiceDependencies):
    if not x_mathbank_launch_id or not dependencies.secrets.compare_digest(
        x_mathbank_launch_id, dependencies.state.SERVER_INSTANCE_ID
    ):
        raise dependencies.HTTPException(status_code=409, detail="Server instance changed")

    def stop_server():
        dependencies.time.sleep(0.5)
        # Raising SIGINT inside this process lets uvicorn's installed handler
        # run its normal lifespan shutdown.  On Windows, os.kill(SIGINT) would
        # call TerminateProcess instead of delivering a cooperative console
        # control event.
        try:
            dependencies.signal.raise_signal(dependencies.signal.SIGINT)
        except Exception as exc:
            dependencies.state._SHUTDOWN_SCHEDULED.clear()
            print(f"[shutdown] Failed to raise cooperative SIGINT: {exc}")

    with dependencies.state._SHUTDOWN_SCHEDULE_LOCK:
        if dependencies.state._SHUTDOWN_SCHEDULED.is_set():
            return {
                "status": "already_stopping",
                "message": "题库系统已在关闭中...",
            }
        dependencies.state._SHUTDOWN_SCHEDULED.set()
        worker = dependencies.threading.Thread(target=stop_server, daemon=True)
        try:
            worker.start()
        except Exception:
            dependencies.state._SHUTDOWN_SCHEDULED.clear()
            raise

    return {"status": "success", "message": "题库系统正在关闭中..."}
