"""Behavior and dependency boundaries for incremental backend extraction."""

import ast
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore

from fastapi.routing import APIRoute
import pytest

from mathbank import docx_import_service, pdf_import_service, web_assets, version_updates
from mathbank.document_import_context import DocumentImportDependencies
from mathbank.document_postprocess import post_process_questions
from mathbank.task_manager import TaskManager


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "tests/fixtures/backend_refactor_contract.json").read_text(encoding="utf-8"))
MODULES = ["document_text", "document_postprocess", "document_import_context",
           "pdf_import_service", "docx_import_service", "web_assets", "version_updates"]
DEPENDENCY_NAMES = {
    "tasks": "DOCUMENT_TASKS", "ocr_semaphore": "PDF_OCR_SEMAPHORE",
    "tmp_upload_dir": "TMP_UPLOAD_DIR", "upload_dir_rel": "UPLOAD_DIR_REL",
    "max_pdf_pages": "MAX_PDF_TASK_PAGES", "inspect_pdf": "inspect_and_extract_pdf",
    "ocr_page": "ocr_pdf_page_image", "parse_text": "parse_paper_text_internal",
    "postprocess": "post_process_pdf_parsed_questions",
    "delete_temp_assets": "_delete_task_temp_assets",
    "extract_docx": "extract_docx_markdown", "reconcile_math": "reconcile_visible_math",
}


def canonical(value):
    """Exclude optional empty AST fields added by newer Python versions."""
    if isinstance(value, ast.AST):
        return {"type": type(value).__name__, "fields": {
            name: canonical(item) for name, item in ast.iter_fields(value)
            if item is not None and item != []
        }}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


class RestoreDependencyNames(ast.NodeTransformer):
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "dependencies":
            return ast.Name(id=DEPENDENCY_NAMES[node.attr], ctx=node.ctx)
        return self.generic_visit(node)

    def visit_Name(self, node):
        old = {"tmp_upload_dir": "TMP_UPLOAD_DIR", "upload_dir_rel": "UPLOAD_DIR_REL",
               "normalize_fillin": "normalize_fillin_macro",
               "find_source_page": "find_source_page_by_overlap"}.get(node.id)
        return ast.Name(id=old, ctx=node.ctx) if old else node


@pytest.mark.parametrize("original,module,name", [
    ("run_pdf_parsing_task", "pdf_import_service", "run_pdf_parsing_task"),
    ("run_docx_parsing_task", "docx_import_service", "run_docx_parsing_task"),
    ("post_process_pdf_parsed_questions", "document_postprocess", "post_process_questions"),
    *[(name, "document_text", name) for name in [
        "normalize_fillin_macro", "extract_title_from_latex", "process_ocr_illustrations",
        "find_source_page_by_overlap", "parse_page_range"]],
    ("parse_version_tuple", "version_updates", "parse_version_tuple"),
])
def test_extracted_algorithm_matches_fixed_baseline(original, module, name):
    tree = ast.parse((ROOT / "mathbank" / (module + ".py")).read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    restored = [RestoreDependencyNames().visit(node) for node in function.body]
    encoded = json.dumps(canonical(restored), sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == CONTRACT["body_sha256"][original]


def test_all_public_routes_keep_their_names_and_methods():
    import main
    actual = [{"path": route.path, "method": method, "name": route.name}
              for route in main.app.routes if isinstance(route, APIRoute)
              for method in route.methods]
    assert sorted(actual, key=lambda row: (row["path"], row["method"])) == CONTRACT["routes"]


@pytest.mark.parametrize("module", MODULES)
def test_services_do_not_import_application_or_create_parallel_runtime(module):
    tree = ast.parse((ROOT / "mathbank" / (module + ".py")).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "main" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "main"
    # Real import check is performed below in a fresh interpreter as well.


def test_services_can_be_imported_without_starting_the_application(tmp_path):
    script = (
        "import sys,importlib;sys.path.insert(0," + repr(str(ROOT)) + ");"
        "modules=" + repr(MODULES) + ";"
        "[importlib.import_module('mathbank.'+name) for name in modules];"
        "assert 'main' not in sys.modules;"
        "print('services imported without application')"
    )
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["pdf", "docx"])
def test_legacy_entries_forward_options_and_share_current_runtime(monkeypatch, kind):
    import main
    service = pdf_import_service if kind == "pdf" else docx_import_service
    name = "run_" + kind + "_parsing_task"
    calls = []
    monkeypatch.setattr(service, name, lambda *args, **kwargs: calls.append((args, kwargs)))
    options = {"generate_answers": True}
    if kind == "pdf":
        options.update(page_range="2-3", pdf_strategy="layout_aware", pdf_verify_suspicions=True)
    else:
        options.update(docx_verify_suspicions=True)
    getattr(main, name)("task", b"source", "exam." + kind, **options)
    args, kwargs = calls[0]
    assert args[:4] == ("task", b"source", "exam." + kind, True)
    assert args[4:] == (("2-3", "layout_aware", True) if kind == "pdf" else (True,))
    deps = kwargs["dependencies"]
    assert deps.tasks is main.DOCUMENT_TASKS
    assert deps.ocr_semaphore is main.PDF_OCR_SEMAPHORE
    assert deps.parse_text is main.parse_paper_text_internal
    assert deps.reconcile_math is main.reconcile_visible_math
    assert deps.tmp_upload_dir == main.TMP_UPLOAD_DIR
    with pytest.raises(FrozenInstanceError):
        deps.max_pdf_pages = 1


@pytest.mark.parametrize("kind", ["pdf", "docx"])
def test_document_service_runs_without_application_globals(tmp_path, kind):
    tasks = TaskManager(max_workers=1)
    seen = []
    def parse(source, generate_answers, **kwargs):
        seen.append(generate_answers)
        return [{"content": "物体的速度为 $v=2\\,\\mathrm{m/s}$，求位移。", "answer_markdown": "原卷答案"}]
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected vision request in the native test")
    deps = DocumentImportDependencies(
        tasks=tasks, ocr_semaphore=BoundedSemaphore(4), tmp_upload_dir=tmp_path,
        upload_dir_rel="static/uploads", max_pdf_pages=80,
        inspect_pdf=lambda *a, **k: {"pages": [{"page_index": 0, "needs_ocr": False, "markdown": "1. 物体匀速运动。"}]},
        ocr_page=forbidden, parse_text=parse,
        postprocess=lambda *a, **k: post_process_questions(*a, **k, tmp_upload_dir=tmp_path, upload_dir_rel="static/uploads"),
        delete_temp_assets=lambda paths: 0,
        extract_docx=lambda *a, **k: {"success": True, "markdown": "1. 物体匀速运动。",
                                     "diagnostics": {}, "image_paths": []},
        reconcile_math=lambda *a, **k: {},
    )
    tasks.create("isolated", document_type=kind, temp_assets=[])
    try:
        if kind == "pdf":
            import pymupdf
            with pymupdf.open() as document:
                document.new_page(width=595, height=842)
                data = document.tobytes()
            pdf_import_service.run_pdf_parsing_task("isolated", data, "physics.pdf", True, dependencies=deps)
        else:
            docx_import_service.run_docx_parsing_task("isolated", b"stub", "physics.docx", True, dependencies=deps)
        result = tasks.snapshot("isolated")
        assert result["status"] == "completed", result.get("error")
        assert result["generate_answers"] is True
        assert seen == [False]  # Original answers only; no paid solving in the service.
        assert result["data"][0]["answer_markdown"]
        assert not (tmp_path / "isolated.pdf").exists()
    finally:
        tasks.shutdown(wait=True)


def test_web_assets_keep_cache_token_and_missing_file_contract(tmp_path):
    response = web_assets.build_index_response(
        static_dir=ROOT / "static", js_dir=ROOT / "static/js", css_dir=ROOT / "static/css",
        local_token="test-only-token", server_instance_id="test-only-instance",
    )
    html = response.body.decode()
    assert "test-only-token" in html and "test-only-instance" in html
    assert '/static/js/qa-data.js?v=' in html and '/static/js/qa.js?v=' in html
    assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert "local_token=test-only-token" in response.headers["set-cookie"]
    missing = web_assets.build_index_response(
        static_dir=tmp_path, js_dir=tmp_path, css_dir=tmp_path,
        local_token="unused", server_instance_id="unused",
    )
    assert missing.status_code == 404


def test_icon_fallback_keeps_media_type_and_headers(tmp_path):
    (tmp_path / "favicon.png").write_bytes(b"test-only-icon")
    response = web_assets.favicon_response(tmp_path)
    assert Path(response.path).name == "favicon.png"
    assert response.media_type == "image/png"
    assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert web_assets.apple_touch_icon_response(tmp_path).media_type == "image/png"
    assert web_assets.favicon_svg_response(tmp_path).status_code == 404


@pytest.mark.parametrize("status", [200, 404])
def test_version_lookup_keeps_physics_repository_and_warning_contract(tmp_path, status):
    calls = []
    class Reply:
        status_code = status
        def json(self):
            return {"tag_name": "v0.2.0", "assets": [
                {"name": "PhysicsBank-Windows-x64.zip", "browser_download_url": "https://example.invalid/app.zip", "size": 1048576}
            ]}
    def request(url, **kwargs):
        calls.append((url, kwargs))
        return Reply()
    result = version_updates.check_release_update(
        current_version="0.1.0", repo="HalHa8/physics-question-bank",
        project_root=tmp_path, request_get=request,
    )
    assert calls[0][0] == "https://api.github.com/repos/HalHa8/physics-question-bank/releases/latest"
    assert calls[0][1]["timeout"] == 5
    if status == 200:
        assert result["has_update"] is True and result["assets"]["Windows"]["size_mb"] == 1.0
    else:
        assert result["status"] == "warning" and result["has_update"] is False
