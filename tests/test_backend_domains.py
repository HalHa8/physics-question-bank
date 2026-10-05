"""All-stage extraction acceptance: semantics, dependency boundaries and state."""

import ast
import copy
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from mathbank.application_bindings import install_legacy_facade
from mathbank.application_factory import create_application, initialize_runtime
from mathbank.application_state import RuntimeState
from mathbank.domain_registry import DOMAINS


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'tests/fixtures/backend_domain_contract.json').read_text(encoding='utf-8'))
API_CONTRACT = json.loads((ROOT / 'tests/fixtures/backend_openapi_contract.json').read_text(encoding='utf-8'))
MODULES = sorted(set(CONTRACT['functions'].values()))


def canonical(value):
    if isinstance(value, bytes):
        return {'bytes': value.hex()}
    if isinstance(value, ast.AST):
        return {'type': type(value).__name__, 'fields': {
            name: canonical(item) for name, item in ast.iter_fields(value)
            if item is not None and item != []
        }}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


class RestoreNames(ast.NodeTransformer):
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == 'dependencies':
            return ast.Name(id=node.attr, ctx=node.ctx)
        if (isinstance(node.value, ast.Attribute) and node.value.attr == 'state'
                and isinstance(node.value.value, ast.Name) and node.value.value.id == 'dependencies'):
            return ast.Name(id=node.attr, ctx=node.ctx)
        return self.generic_visit(node)


@pytest.mark.parametrize('name,module', sorted(CONTRACT['functions'].items()))
def test_each_extracted_function_keeps_its_original_algorithm(name, module):
    tree = ast.parse((ROOT / 'mathbank' / (module + '.py')).read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    body = [RestoreNames().visit(copy.deepcopy(n)) for n in function.body]
    encoded = json.dumps(canonical(body), sort_keys=True, separators=(',', ':')).encode()
    assert hashlib.sha256(encoded).hexdigest() == CONTRACT['body_sha256'][name]


@pytest.mark.parametrize('module', MODULES)
def test_domain_has_no_application_import_or_hidden_state(module):
    tree = ast.parse((ROOT / 'mathbank' / (module + '.py')).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Global)
        if isinstance(node, ast.Import):
            assert all(alias.name not in ('main', 'mathbank.application_factory') for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module not in ('main', 'mathbank.application_factory')
    for node in tree.body:
        assert isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Expr))
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant)  # Only a module docstring.


def test_importing_all_domains_does_not_start_server_or_write_files(tmp_path):
    names = MODULES + ['application_factory', 'application_imports', 'application_bindings', 'api_routes']
    script = ("import sys,importlib;sys.path.insert(0," + repr(str(ROOT)) + ");"
              "[importlib.import_module('mathbank.'+name) for name in " + repr(names) + "];"
              "assert 'main' not in sys.modules")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    result = subprocess.run([sys.executable, '-c', script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []


def test_http_request_and_response_schema_matches_before_refactor():
    import main
    schema = main.app.openapi()
    encoded = json.dumps(schema, sort_keys=True, separators=(',', ':')).encode()
    assert len(schema['paths']) == API_CONTRACT['paths']
    assert hashlib.sha256(encoded).hexdigest() == API_CONTRACT['openapi_sha256']


def test_main_is_only_a_compatibility_composition_entry():
    tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
    assert not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in tree.body)
    assert len((ROOT / 'main.py').read_text(encoding='utf-8').splitlines()) < 80


def test_two_applications_keep_runtime_and_legacy_overrides_isolated(tmp_path):
    first = create_application(initialize=False, state=RuntimeState(IS_TESTING=True, UPLOAD_DIR=str(tmp_path / 'one')))
    second = create_application(initialize=False, state=RuntimeState(IS_TESTING=True, UPLOAD_DIR=str(tmp_path / 'two')))
    entry = ModuleType('isolated_legacy_entry')
    install_legacy_facade(entry, first)
    try:
        entry.METADATA_CACHE = {'curriculum': {'第一套': {}}}
        second.state.METADATA_CACHE = {'curriculum': {'第二套': {}}}
        assert entry.get_current_curriculum() == {'第一套': {}}
        assert second.resolve('get_current_curriculum')() == {'第二套': {}}
        assert first.state.DOCUMENT_TASKS is not second.state.DOCUMENT_TASKS
        assert first.state.PDF_OCR_SEMAPHORE is not second.state.PDF_OCR_SEMAPHORE
        original = entry.UPLOAD_DIR
        with patch.object(entry, 'UPLOAD_DIR', str(tmp_path / 'outer')):
            with patch.object(entry, 'UPLOAD_DIR', str(tmp_path / 'inner')):
                assert first.state.UPLOAD_DIR == str(tmp_path / 'inner')
            assert entry.UPLOAD_DIR == str(tmp_path / 'outer')
        assert entry.UPLOAD_DIR == original
        with patch.object(entry, 'get_current_curriculum', return_value={'override': {}}):
            assert first.resolve('get_current_curriculum')() == {'override': {}}
            assert second.resolve('get_current_curriculum')() == {'第二套': {}}
        assert entry.get_current_curriculum() == {'第一套': {}}
        for module, contract, _names in DOMAINS:
            deps = first.dependencies(contract)
            assert deps.state is first.state
            assert module.__dict__.get('app') is None
            assert 'state' in {field.name for field in fields(contract)}
        assert list(tmp_path.iterdir()) == []
    finally:
        first.state.DOCUMENT_TASKS.shutdown(wait=True)
        second.state.DOCUMENT_TASKS.shutdown(wait=True)


def test_failed_bootstrap_releases_its_lock_and_tasks_before_database_errors(monkeypatch, tmp_path):
    from mathbank import application_factory as factory
    calls = []
    class Lock:
        def close(self):
            calls.append('close')
    class Tasks:
        def shutdown(self, *, wait):
            calls.append(('tasks', wait))
    app = create_application(initialize=False, state=RuntimeState(IS_TESTING=False, UPLOAD_DIR=str(tmp_path)))
    real_tasks = app.state.DOCUMENT_TASKS
    app.state.DOCUMENT_TASKS = Tasks()
    monkeypatch.setattr(factory.defaults, 'load_dotenv', lambda *a: None)
    monkeypatch.setattr(factory.defaults, 'harden_private_path', lambda *a: None)
    monkeypatch.setattr(factory.defaults, 'acquire_runtime_lock', lambda: calls.append('lock') or Lock())
    monkeypatch.setattr(factory.atexit, 'register', lambda *a: None)
    def fail_db():
        calls.append('database')
        raise RuntimeError('controlled database failure')
    monkeypatch.setattr(factory.defaults, 'init_db', fail_db)
    try:
        with pytest.raises(RuntimeError, match='controlled database failure'):
            initialize_runtime(app)
        assert calls == ['lock', 'database', ('tasks', False), 'close']
    finally:
        real_tasks.shutdown(wait=True)


def test_instance_identity_is_derived_after_loading_environment(monkeypatch, tmp_path):
    from mathbank import application_factory as factory
    app = create_application(initialize=False, state=RuntimeState(IS_TESTING=True, UPLOAD_DIR=str(tmp_path)))
    launch_id = '7' * 32
    monkeypatch.delenv('MATHBANK_LAUNCH_ID', raising=False)
    monkeypatch.setattr(factory.defaults, 'load_dotenv', lambda *a: monkeypatch.setenv('MATHBANK_LAUNCH_ID', launch_id))
    monkeypatch.setattr(factory.defaults, 'harden_private_path', lambda *a: None)
    monkeypatch.setattr(factory.defaults, 'init_db', lambda: None)
    app.services.update(load_or_create_local_token=lambda: 'test-only-token',
                        load_or_init_metadata=lambda: None, print_startup_diagnostics=lambda: None)
    try:
        initialize_runtime(app)
        assert app.state.SERVER_INSTANCE_ID == launch_id
        assert app.resolve('get_version_info')()['server_instance_id'] == launch_id
    finally:
        app.state.DOCUMENT_TASKS.shutdown(wait=True)


def test_denied_restore_lock_stops_before_database_and_releases_tasks(monkeypatch, tmp_path):
    from mathbank import application_factory as factory
    calls = []
    app = create_application(initialize=False, state=RuntimeState(IS_TESTING=False, UPLOAD_DIR=str(tmp_path)))
    monkeypatch.setattr(factory.defaults, 'load_dotenv', lambda *a: None)
    monkeypatch.setattr(factory.defaults, 'harden_private_path', lambda *a: None)
    def denied_lock():
        calls.append('lock')
        raise RuntimeError('restore in progress')
    monkeypatch.setattr(factory.defaults, 'acquire_runtime_lock', denied_lock)
    monkeypatch.setattr(factory.defaults, 'init_db', lambda: pytest.fail('Database accessed before lock'))
    real_shutdown = app.state.DOCUMENT_TASKS.shutdown
    monkeypatch.setattr(app.state.DOCUMENT_TASKS, 'shutdown', lambda **kwargs: calls.append('tasks') or real_shutdown(**kwargs))
    with pytest.raises(RuntimeError, match='restore in progress'):
        initialize_runtime(app)
    assert calls == ['lock', 'tasks']
