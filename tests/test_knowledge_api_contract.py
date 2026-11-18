"""Audit precisely the additive API upgrade, not a blanket re-recorded schema."""

import hashlib
import json
from pathlib import Path

from mathbank.application_factory import create_application


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def test_old_operations_and_components_outside_knowledge_scope_are_unchanged():
    contract = json.loads((Path(__file__).parent / 'fixtures/backend_openapi_contract.json').read_text(encoding='utf-8'))
    application = create_application(initialize=False)
    try:
        schema = application.app.openapi()
        for path, methods in contract['unchanged_operations'].items():
            for method, digest in methods.items():
                assert _hash(schema['paths'][path][method]) == digest, (path, method)
        for name, digest in contract['unchanged_components'].items():
            assert _hash(schema['components']['schemas'][name]) == digest, name
        for path, methods in contract.get('audited_operations', {}).items():
            for method, audit in methods.items():
                assert _hash(schema['paths'][path][method]) == audit['sha256'], (path, method)
                assert audit['previous_sha256'] and audit['reason'] and audit['behavior_regressions']
        for name, audit in contract.get('audited_components', {}).items():
            assert _hash(schema['components']['schemas'][name]) == audit['sha256'], name
            assert audit['previous_sha256'] and audit['reason'] and audit['behavior_regressions']
        forms = schema['components']['schemas']
        for name in ('Body_import_library_transfer_api_library_transfer_import_post',
                     'Body_start_library_import_task_api_library_transfer_tasks_import_post'):
            assert 'confirm_repeat_sha256' in forms[name]['properties']
            assert 'confirm_repeat_sha256' not in forms[name].get('required', [])
        assert forms['Body_ai_classify_api_ai_classify_post']['required'] == ['content']
        assert forms['Body_ai_parse_paper_api_ai_parse_paper_post']['required'] == ['latex_content']
        for kind in ('pdf', 'docx'):
            form = forms[f'Body_upload_{kind}_task_api_upload_{kind}_task_post']
            assert form['required'] == ['file']
            assert form['properties'][f'{kind}_verify_suspicions']['default'] in (False, 'false')
            assert form['properties']['generate_answers']['default'] == 'false'
            assert 'client_request_id' not in form['required'] and 'paper_title' not in form['required']
        parameters = {item['name']: item for item in schema['paths']['/api/questions']['get']['parameters']}
        for name in ('knowledge_points', 'point_match', 'point_role', 'point_unlabeled'):
            assert parameters[name]['required'] is False
        for name in ('Body_create_question_api_questions_post', 'Body_update_question_api_questions__question_id__put'):
            form = schema['components']['schemas'][name]
            assert 'knowledge_points' in form['properties']
            assert 'knowledge_points' not in form.get('required', [])
        assert set(schema['paths']['/api/knowledge-points']) == {'get', 'post'}
    finally:
        application.state.DOCUMENT_TASKS.shutdown(wait=True)
