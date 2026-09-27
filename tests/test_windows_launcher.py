"""Shared local-launcher behavior; runs without importing the application or data."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import local_launcher as launcher
from mathbank import GITHUB_REPO


def test_windows_entry_uses_shared_launcher():
    from scripts import windows_launcher
    assert windows_launcher.main is launcher.main


@pytest.mark.parametrize("old_state", ['broken JSON', '{"pid": 1}', ''])
def test_existing_service_opens_without_environment_or_state_checks(tmp_path, monkeypatch, old_state):
    state = tmp_path / ".system_generated"
    state.mkdir()
    (state / "server-state.json").write_text(old_state)
    (tmp_path / "RELEASE-MANIFEST.json").write_text("invalid manifest")
    opened = []
    monkeypatch.setattr(launcher, "existing_service_ready", lambda: True)
    monkeypatch.setattr(launcher, "open_browser", lambda: opened.append(True))
    monkeypatch.setattr(launcher, "prepare_python", lambda *_: pytest.fail("environment touched"))
    launcher.run_launcher(tmp_path)
    assert opened == [True]
    assert (state / "server-state.json").read_text() == old_state


def test_free_port_starts_despite_broken_old_state_and_manifest(tmp_path, monkeypatch):
    state = tmp_path / ".system_generated"
    state.mkdir()
    for name in ("server-state.json", "installed-release-manifest.json", "server.pid"):
        (state / name).write_text("invalid old record")
    (tmp_path / "RELEASE-MANIFEST.json").write_text("not JSON")
    events = []
    monkeypatch.setattr(launcher, "existing_service_ready", lambda: False)
    monkeypatch.setattr(launcher, "port_in_use", lambda: False)
    monkeypatch.setattr(launcher, "prepare_python", lambda root: (Path(sys.executable), None))
    monkeypatch.setattr(launcher, "ensure_dependencies", lambda *_: events.append("dependencies"))
    monkeypatch.setattr(launcher, "start_server", lambda *_: events.append("start"))
    launcher.run_launcher(tmp_path)
    assert events == ["dependencies", "start"]
    assert (state / "server.pid").read_text() == "invalid old record"


def test_foreign_port_reports_conflict_without_starting_or_stopping(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "existing_service_ready", lambda: False)
    monkeypatch.setattr(launcher, "port_in_use", lambda: True)
    monkeypatch.setattr(launcher, "start_server", lambda *_: pytest.fail("started"))
    with pytest.raises(launcher.LauncherError, match="8000"):
        launcher.run_launcher(tmp_path)


@pytest.mark.parametrize("ready,repo,expected", [
    (True, GITHUB_REPO, True), (False, GITHUB_REPO, False),
    (True, "other/app", False),
])
def test_existing_service_requires_usable_physicsbank_page(monkeypatch, ready, repo, expected):
    monkeypatch.setattr(launcher, "read_json", lambda route:
                        {"repo": repo} if route == "/api/version" else {"ready": ready})
    assert launcher.existing_service_ready() is expected


def test_second_launch_reuses_running_physicsbank_service(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "read_json", lambda route:
                        {"repo": GITHUB_REPO} if route == "/api/version" else {"ready": True})
    monkeypatch.setattr(launcher, "port_in_use", lambda: True)
    monkeypatch.setattr(launcher, "prepare_python", lambda *_: pytest.fail("environment touched"))
    opened = []
    monkeypatch.setattr(launcher, "open_browser", lambda: opened.append(True))

    launcher.run_launcher(tmp_path)

    assert opened == [True]


def test_new_service_readiness_does_not_depend_on_launcher_pid(monkeypatch):
    child = SimpleNamespace(poll=lambda: 0, returncode=0)
    monkeypatch.setattr(launcher, "read_json", lambda _: {"ready": True, "server_instance_id": "ours"})
    assert launcher.wait_until_ready(child, "ours") == (True, "ready")


def test_another_services_health_cannot_mask_start_failure(monkeypatch):
    child = SimpleNamespace(poll=lambda: 1, returncode=1)
    monkeypatch.setattr(launcher, "read_json", lambda _: {"ready": True, "server_instance_id": "other"})
    ready, detail = launcher.wait_until_ready(child, "ours")
    assert not ready
    assert "退出码 1" in detail


def test_redirector_exit_zero_allows_delegated_service_to_finish_starting(monkeypatch):
    child = SimpleNamespace(poll=lambda: 0, returncode=0)
    responses = iter([OSError("not listening yet"), {"ready": True, "server_instance_id": "ours"}])
    def read(_route):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(launcher, "read_json", read)
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    assert launcher.wait_until_ready(child, "ours") == (True, "ready")


def test_proxy_variables_do_not_affect_local_requests(monkeypatch):
    import urllib.request
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    seen = []
    original = urllib.request.build_opener
    def opener(*handlers):
        seen.extend(handlers)
        result = original(*handlers)
        result.open = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline"))
        return result
    monkeypatch.setattr(urllib.request, "build_opener", opener)
    assert not launcher.existing_service_ready()
    assert seen[0].proxies == {}


def test_lock_file_is_reusable_after_exception(tmp_path):
    with pytest.raises(ValueError):
        with launcher.launcher_lock(tmp_path):
            raise ValueError("interrupted")
    with launcher.launcher_lock(tmp_path, timeout=0):
        pass


@pytest.mark.parametrize("changed,imports_ok,installs", [
    (False, True, False), (True, True, True), (False, False, True),
])
def test_dependencies_install_only_when_needed(tmp_path, monkeypatch, changed, imports_ok, installs):
    monkeypatch.delenv("MATHBANK_PORTABLE_RUNTIME", raising=False)
    requirements = b"fastapi==1.0\n"
    (tmp_path / "requirements.txt").write_bytes(requirements)
    state = tmp_path / ".system_generated"
    state.mkdir()
    stamp = state / "requirements.sha256"
    stamp.write_text("old" if changed else hashlib.sha256(requirements).hexdigest())
    monkeypatch.setattr(launcher, "environment_works", lambda *_: imports_ok)
    commands = []
    monkeypatch.setattr(launcher, "run_checked", lambda command, *_: commands.append(command))
    launcher.ensure_dependencies(tmp_path, Path(sys.executable))
    assert bool(commands) is installs
    if installs:
        assert "install" in commands[0]
        assert stamp.read_text().strip() == hashlib.sha256(requirements).hexdigest()


def test_portable_missing_dependency_shows_import_error_without_pip(tmp_path, monkeypatch):
    monkeypatch.setenv("MATHBANK_PORTABLE_RUNTIME", "1")
    monkeypatch.setattr(launcher, "environment_works", lambda *_: False)
    commands = []
    def fail(command, root, message):
        commands.append(command)
        raise launcher.LauncherError(message)
    monkeypatch.setattr(launcher, "run_checked", fail)
    with pytest.raises(launcher.LauncherError, match="依赖不完整"):
        launcher.ensure_dependencies(tmp_path, Path(sys.executable))
    assert "pip" not in commands[0]


def test_mac_rebuild_failure_restores_existing_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    monkeypatch.setattr(launcher, "environment_works", lambda *_: False)
    (tmp_path / ".system_generated").mkdir()
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "keep.txt").write_text("old environment")
    def fail(*_args):
        venv.mkdir()
        raise launcher.LauncherError("create failed")
    monkeypatch.setattr(launcher, "run_checked", fail)
    with pytest.raises(launcher.LauncherError):
        launcher.prepare_python(tmp_path)
    assert (venv / "keep.txt").read_text() == "old environment"


def test_failure_keeps_service_log_and_does_not_kill_child(tmp_path, monkeypatch, capsys):
    (tmp_path / ".system_generated").mkdir()
    class Child:
        pid = 123
        def terminate(self):
            pytest.fail("terminated")
        def kill(self):
            pytest.fail("killed")
    def spawn(*args, **kwargs):
        kwargs["stdout"].write(b"ImportError: missing_package\n")
        return Child()
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    monkeypatch.setattr(launcher, "wait_until_ready", lambda *_: (False, "failed"))
    monkeypatch.setattr(launcher, "open_browser", lambda: pytest.fail("opened"))
    with pytest.raises(launcher.LauncherError):
        launcher.start_server(tmp_path, Path(sys.executable))
    assert "missing_package" in capsys.readouterr().out
    assert (tmp_path / ".system_generated/probe.log").read_text() == "failed"
