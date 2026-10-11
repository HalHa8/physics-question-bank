"""Source-only maintenance boundary adapted from upstream 550b319.

Only synthetic release fixtures are produced; no runtime is downloaded or
real portable package built. Source history and PhysicsBank assets remain.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from scripts import build_release
from test_release_hardening import _make_minimal_macos_tree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERNAL_TOOL_MODULE_PATHS = tuple(
    f"{package}/{name}.py"
    for package in ("mathbank", "scripts")
    for name in (
        "classification_proposals", "knowledge_backfill", "knowledge_backfill_apply",
        "association_batch", "question_exchange",
    )
)
NON_RUNTIME_RELEASE_SCRIPT_PATHS = (
    "scripts/migrate_word_math_private_chars.py", "scripts/build_release.py",
)
INTERNAL_TOOL_FORBIDDEN_MEMBERS = (
    *INTERNAL_TOOL_MODULE_PATHS, *NON_RUNTIME_RELEASE_SCRIPT_PATHS,
    "scripts/resources/classification_proposal.example.json",
    "scripts/resources/nested/protocol.json", "scripts/resources/",
    "MathBank/Knowledge_Backfill.py", "Scripts/Resources/protocol.json",
    "Scripts/Resources/", "Scripts/Migrate_Word_Math_Private_Chars.py",
    "Scripts/Build_Release.py",
)


def test_release_copy_excludes_source_tools_and_preserves_physics_runtime(tmp_path, monkeypatch):
    source, staged = tmp_path / "source", tmp_path / "staged"
    runtime_paths = (
        "scripts/__init__.py", "scripts/backup.py", "scripts/restore.py",
        "scripts/search_questions.py", "mathbank/backup.py", "mathbank/db_migrations.py",
        "mathbank/database.py", "mathbank/sync_helper.py",
        "mathbank/application_factory.py", "mathbank/application_state.py",
        "mathbank/api_routes.py", "mathbank/ocr_service.py",
        "mathbank/resources/classification_proposal.example.json",
        "mathbank/vendor/knowledge_backfill.py", "scripts/vendor/question_exchange.py",
        "templates/template.tex",
    )
    for relative_path in (
        *build_release.ROOT_FILE_ALLOWLIST, "启动题库系统.command",
        *(f"docs/images/{name}" for name in build_release.DOCS_IMAGE_ALLOWLIST),
        *runtime_paths, *INTERNAL_TOOL_MODULE_PATHS, *NON_RUNTIME_RELEASE_SCRIPT_PATHS,
        "scripts/resources/classification_proposal.schema.json",
        "scripts/resources/nested/protocol.json",
        "MathBank/Knowledge_Backfill.py", "Scripts/Resources/protocol.json",
    ):
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"pass\n")
    for relative_name in build_release.STATIC_ALLOWLIST:
        path = source / "static" / relative_name
        if relative_name in {"css", "js", "lib"}:
            path.mkdir(parents=True, exist_ok=True)
            (path / "runtime.txt").write_bytes(b"runtime asset\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"runtime asset\n")

    safe_modules = (
        "mathbank.paths", "mathbank.curriculums",
        "scripts.local_launcher", "scripts.windows_launcher", "scripts.release_overlay",
    )
    real_paths = ("mathbank/__init__.py", *(name.replace(".", "/") + ".py" for name in safe_modules))
    for relative_path in real_paths:
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, path)
    # Real physics curriculum, not the upstream mathematics-only smoke fixture.
    curriculum_path = "mathbank/resources/curriculums/P.json"
    (source / curriculum_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / curriculum_path, source / curriculum_path)

    monkeypatch.setattr(build_release, "BASE_DIR", str(source))
    build_release.copy_app_files(staged, "启动题库系统.command")
    for relative_path in (*INTERNAL_TOOL_MODULE_PATHS, *NON_RUNTIME_RELEASE_SCRIPT_PATHS):
        assert not (staged / relative_path).exists(), relative_path
    assert not (staged / "scripts/resources").exists()
    assert not (staged / "MathBank/Knowledge_Backfill.py").exists()
    assert not (staged / "Scripts/Resources").exists()
    for relative_path in (
        *runtime_paths, *real_paths, curriculum_path, *build_release.ROOT_FILE_ALLOWLIST,
        *(f"docs/images/{name}" for name in build_release.DOCS_IMAGE_ALLOWLIST),
    ):
        assert (staged / relative_path).read_bytes() == (source / relative_path).read_bytes()
    for relative_path in (
        "python/site-packages/vendor/knowledge_backfill.py",
        "python/site-packages/scripts/resources/protocol.json",
        "scripts/resources_other/protocol.json", "mathbank/question_exchange_runtime.py",
    ):
        assert build_release._release_path_violation(relative_path) is None

    smoke_code = '''
import importlib
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
for name in sys.argv[2:]:
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(root), name
from mathbank.curriculums import load_curriculum, DEFAULT_QUESTION_TYPES
assert "质点与参考系" in load_curriculum()["必修第一册"]["第一章 运动的描述"]
assert {item["value"] for item in DEFAULT_QUESTION_TYPES} >= {"experiment", "detailed_answer"}
'''
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", smoke_code, str(staged), *safe_modules],
        cwd=staged, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not list(staged.rglob("__pycache__"))


@pytest.mark.parametrize("forbidden_path", INTERNAL_TOOL_FORBIDDEN_MEMBERS)
def test_release_tree_rejects_internal_tools_and_empty_directories(tmp_path, forbidden_path):
    _make_minimal_macos_tree(tmp_path)
    path = tmp_path / forbidden_path
    if forbidden_path.endswith("/"):
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"must not ship\n")
    with pytest.raises(RuntimeError, match="forbidden artifacts"):
        build_release.assert_release_tree_clean(tmp_path, "macos")


@pytest.mark.parametrize("forbidden_path", INTERNAL_TOOL_FORBIDDEN_MEMBERS)
def test_finished_archive_rejects_internal_tools_and_empty_directories(tmp_path, forbidden_path):
    staging = tmp_path / "staging"
    _make_minimal_macos_tree(staging)
    archive_path = build_release._build_archive(
        staging, str(tmp_path / "PhysicsBank-macOS"), "macos", "启动题库系统.command",
    )
    with zipfile.ZipFile(archive_path, "a") as archive:
        archive.writestr(forbidden_path, b"" if forbidden_path.endswith("/") else b"must not ship\n")
    with pytest.raises(RuntimeError, match="forbidden artifacts"):
        build_release.verify_zip_archive(
            archive_path, {"RELEASE-MANIFEST.json", "main.py", "启动题库系统.command"},
        )


def test_release_source_validation_filters_non_runtime_tools(monkeypatch):
    commands = []
    monkeypatch.setattr(build_release.subprocess, "check_call", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(build_release.shutil, "which", lambda name: None)
    build_release.validate_release_source()
    compile_code = next(command[-1] for command in commands if "compile(p.read_bytes()" in command[-1])
    assert "if not _is_internal_tool_release_path(p)" in compile_code
    assert "from scripts.build_release import _is_internal_tool_release_path" in compile_code
