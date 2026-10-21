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
