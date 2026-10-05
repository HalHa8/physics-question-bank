"""System routes; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import Form


@dataclass(frozen=True)
class SystemRoutesDependencies:
    state: RuntimeState
    JSONResponse: Any
    PANDOC_INSTALL_MANAGER: Any
    PROJECT_ROOT: Any
    STATIC_CSS_DIR: Any
    STATIC_DIR: Any
    STATIC_JS_DIR: Any
    engine: Any
    normalize_fraction_style: Any
    pandoc_status: Any
    readiness_report: Any
    version_updates: Any
    web_assets: Any


def healthz(*, dependencies: SystemRoutesDependencies):
    report = dependencies.readiness_report(dependencies.engine)
    report["server_instance_id"] = dependencies.state.SERVER_INSTANCE_ID
    return dependencies.JSONResponse(report, status_code=200 if report["ready"] else 503)


def read_index(*, dependencies: SystemRoutesDependencies):
    return dependencies.web_assets.build_index_response(
        static_dir=dependencies.STATIC_DIR, js_dir=dependencies.STATIC_JS_DIR, css_dir=dependencies.STATIC_CSS_DIR,
        local_token=dependencies.state.LOCAL_TOKEN, server_instance_id=dependencies.state.SERVER_INSTANCE_ID,
    )


def read_favicon(*, dependencies: SystemRoutesDependencies):
    return dependencies.web_assets.favicon_response(dependencies.STATIC_DIR)


def read_favicon_svg(*, dependencies: SystemRoutesDependencies):
    return dependencies.web_assets.favicon_svg_response(dependencies.STATIC_DIR)


def read_apple_touch_icon(*, dependencies: SystemRoutesDependencies):
    return dependencies.web_assets.apple_touch_icon_response(dependencies.STATIC_DIR)


def format_fraction_style(text: str=Form('', max_length=200000), *, dependencies: SystemRoutesDependencies):
    """Format an editor snapshot without reading or writing stored questions."""
    normalized = dependencies.normalize_fraction_style(text)
    return {"text": normalized, "changed": normalized != text}


def get_version_info(*, dependencies: SystemRoutesDependencies):
    """Return local version info."""
    from mathbank import __version__, GITHUB_REPO
    is_git_repo = (dependencies.PROJECT_ROOT / ".git").exists()
    return {
        "current_version": __version__,
        "repo": GITHUB_REPO,
        "is_git_repo": is_git_repo,
        "server_instance_id": dependencies.state.SERVER_INSTANCE_ID,
    }


def check_version_update(*, dependencies: SystemRoutesDependencies):
    from mathbank import __version__, GITHUB_REPO
    from mathbank.ai_http import robust_request_get
    return dependencies.version_updates.check_release_update(
        current_version=__version__, repo=GITHUB_REPO,
        project_root=dependencies.PROJECT_ROOT, request_get=robust_request_get,
    )


def get_pandoc_runtime_status(*, dependencies: SystemRoutesDependencies):
    """Report whether Word-native formula conversion is currently available."""
    install_state = dependencies.PANDOC_INSTALL_MANAGER.snapshot()
    if install_state.get("status") in {"queued", "downloading", "verifying"}:
        return {"status": "success", "pandoc": install_state}
    return {"status": "success", "pandoc": dependencies.pandoc_status()}


def install_pandoc_runtime(*, dependencies: SystemRoutesDependencies):
    """Start or join the single verified app-local Pandoc installation task."""
    state = dependencies.PANDOC_INSTALL_MANAGER.ensure()
    status_code = 200 if state.get("status") == "ready" else 202
    return dependencies.JSONResponse(
        status_code=status_code,
        content={"status": "success", "pandoc": state},
    )


def get_pandoc_install_status(task_id: str, *, dependencies: SystemRoutesDependencies):
    state = dependencies.PANDOC_INSTALL_MANAGER.snapshot()
    if not state.get("task_id") or state.get("task_id") != task_id:
        return dependencies.JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Pandoc 安装任务不存在或已过期。"},
        )
    return {"status": "success", "pandoc": state}
