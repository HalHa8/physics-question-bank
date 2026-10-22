"""Physics-specific acceptance for the adapted 3.0 capabilities, no live AI."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mathbank import database, db_migrations, prompts
from mathbank.application_factory import create_application
from mathbank.application_state import RuntimeState
from mathbank.document_postprocess import post_process_questions
from mathbank.knowledge_points import seed_catalog, replace_question_points, normalize_question_points
from mathbank.library_transfer import export_library_zip, import_library_zip
from mathbank.question_references import sync_question_source_labels, sync_question_references, reference_payloads


POINT = 'phy:momentum-conservation'
PHYSICS = r'质量 $m=2.00\,\mathrm{kg}$，$\vec{v}=-3.00\,\mathrm{m/s}$；电流 $i=1.60\,\mathrm{mA}$，保持电路串联，见例1.2。'


@pytest.mark.parametrize('model_form,content,expected,origin', [
    ('experiment', r'测量电源电动势，填表并分析误差：\fillin', 'experiment', 'ai'),
    ('experiment', r'判断正确选项\begin{choices}\item A\item B\end{choices}', 'choice', 'structure'),
    ('short_answer', '解释超重现象，不要求数值计算。', 'short_answer', 'ai'),
    ('detailed_answer', '求动量变化与平均作用力。', 'detailed_answer', 'ai'),
])
def test_physics_classification_preserves_experiments_with_blanks_and_choice_confirmation(model_form, content, expected, origin):
    provider = SimpleNamespace(api_key='test-only', api_base='https://example.invalid/v1',
        model_name='fake', credential_label='fixture', reasoning_effort=None, provider_code='test')
    response = MagicMock()
    response.json.return_value = {'choices': [{'message': {'content': json.dumps({
        'compulsory': '必修第一册', 'chapter': '第四章 运动和力的关系', 'knowledge': '',
        'question_form': model_form, 'knowledge_points': []})}}]}
    with patch('main.resolve_text_provider', return_value=provider), patch('main.post_chat_completion', return_value=response) as post, patch(
        'main.get_current_curriculum', return_value={'必修第一册': {'第四章 运动和力的关系': []}}), patch(
        'main.get_active_version_code', return_value='P'):
        from main import ai_classify
        result = ai_classify(content)
    assert result['question_form'] == expected and result['question_form_source'] == origin
    assert 'question_type' not in result
    assert post.call_count == 1


@contextmanager
def isolated(path):
    engine = create_engine(f'sqlite:///{path}')
    try:
        database.Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(f'PRAGMA user_version={db_migrations.LATEST_SCHEMA_VERSION}')
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_physics_package_roundtrip_preserves_native_points_units_images_and_local_names(tmp_path):
    source_uploads = tmp_path / 'source-images'
    source_uploads.mkdir()
    Image.new('RGB', (17, 13), 'blue').save(source_uploads / 'circuit.png')
    package = tmp_path / 'physics.zip'
    with isolated(tmp_path / 'source.db') as source:
        seed_catalog(source)
        first = database.Question(content=PHYSICS + '\n![电路](/static/uploads/circuit.png)',
            question_type='experiment', tags='有效数字,电路拓扑', source='自编物理实验 | 例1.1',
            category_compulsory='选择性必修第一册', category_chapter='第一章 动量守恒定律',
            category_knowledge='动量守恒定律', answer_markdown=r'$p=-6.00\,\mathrm{kg\,m/s}$')
        first.image_paths = ['/static/uploads/circuit.png']
        second = database.Question(content='作为交叉引用的原始实验题', source='自编物理实验 | 例1.2')
        source.add_all([first, second]); source.flush()
        evidence = {'code': POINT, 'role': 'main', 'status': 'suggested',
                    'evidence_source': 'content', 'evidence': r'$\vec{v}=-3.00\,\mathrm{m/s}$',
                    'origin': 'ai_classification', 'scope': ['(1)']}
        replace_question_points(first, normalize_question_points([evidence], source), source)
        for question in (first, second):
            sync_question_source_labels(source, question)
            sync_question_references(source, question)
        source.commit()
        summary = export_library_zip(source, package, uploads_dir=source_uploads, active_version='P')
        assert summary == {'question_count': 2, 'image_count': 1}
    with isolated(tmp_path / 'receiving.db') as receiving:
        seed_catalog(receiving)
        point = receiving.get(database.KnowledgePoint, POINT)
        point.name = '教师自己的动量专题名'
        receiving.commit()
        result = import_library_zip(receiving, package, uploads_dir=tmp_path / 'receiving-images', active_version='P')
        imported = receiving.get(database.Question, result['id_map'][1])
        assert imported.content.startswith(PHYSICS)
        assert imported.question_type == 'experiment' and imported.tags == '有效数字,电路拓扑'
        assert imported.answer_markdown == r'$p=-6.00\,\mathrm{kg\,m/s}$'
        assert imported.category_knowledge == '动量守恒定律'
        relation = imported.knowledge_points[0].to_dict()
        assert relation['code'] == POINT and relation['status'] == 'suggested'
        assert relation['evidence'] == evidence['evidence'] and relation['scope'] == ['(1)']
        assert receiving.get(database.KnowledgePoint, POINT).name == '教师自己的动量专题名'
        refs = reference_payloads(receiving, [imported])[imported.id]
        assert refs[0]['target_question_id'] == result['id_map'][2]
        assert len(list((tmp_path / 'receiving-images').rglob('*.png'))) == 1


def test_preserved_physics_source_branch_never_rewrites_units_signs_or_literal_code(tmp_path):
    original = {'content': PHYSICS + r' 代码 `print(\n)`',
                'answer_markdown': r'保留单位 $\mathrm{mN}$ 而不是 $\mathrm{MN}$。',
                'referenced_images': []}
    before = deepcopy(original)
    result = post_process_questions([original], '物理保真', source_body_preserved=True,
                                    tmp_upload_dir=tmp_path, upload_dir_rel='static/uploads')[0]
    for field in ('content', 'answer_markdown'):
        assert result[field] == before[field]


@pytest.mark.parametrize('prompt', [prompts.build_pdf_page_vision_prompt({'page_index': 0}),
                                  prompts.build_pdf_region_vision_prompt([])])
def test_pdf_prompts_keep_physics_specific_evidence_not_math_only_defaults(prompt):
    assert all(word in prompt for word in ('物理', '单位大小写', '矢量方向', '正负号', '有效数字', '坐标轴', '电路拓扑'))
    assert '你执行数学试卷' not in prompts.PDF_STRUCTURED_OUTPUT_INSTRUCTIONS


def test_disabled_pdf_experiments_and_separate_runtimes_stay_disabled(tmp_path):
    application = create_application(initialize=False, state=RuntimeState(IS_TESTING=True, UPLOAD_DIR=str(tmp_path)))
    try:
        assert application.state.PDF_CLOUD_ONLY is True
        assert application.state.DOCUMENT_PROJECTS is None
        assert not application.state.DATABASE_EXPORT_QUEUE.started
        assert not list(tmp_path.iterdir())
        assert application.resolve('_document_project_service')() is None
    finally:
        application.state.DOCUMENT_TASKS.shutdown(wait=True)


def test_v11_physics_upgrade_keeps_every_authored_column_and_backs_up_first(tmp_path, monkeypatch):
    path = tmp_path / 'physics-v11.db'
    with isolated(path) as session:
        session.add(database.Question(content=PHYSICS, tags='原有自定义标签', question_type='experiment'))
        session.commit()
    new_tables = ('question_sub_knowledge', 'question_source_labels', 'question_references', 'document_import_receipts')
    with sqlite3.connect(path) as connection:
        for table in new_tables:
            connection.execute('DROP TABLE ' + table)
        connection.execute('PRAGMA user_version=11')
        before = connection.execute('SELECT * FROM questions').fetchall()
    monkeypatch.setattr(db_migrations, 'SCHEMA_SNAPSHOT_DIR', tmp_path / 'snapshots')
    engine = create_engine(f'sqlite:///{path}')
    try:
        result = db_migrations.migrate_database(engine)
        with sqlite3.connect(result['backup']) as snapshot:
            assert snapshot.execute('PRAGMA user_version').fetchone()[0] == 11
            assert snapshot.execute('SELECT * FROM questions').fetchall() == before
        with engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT * FROM questions').all() == before
            for table in new_tables:
                assert connection.exec_driver_sql('SELECT COUNT(*) FROM ' + table).scalar_one() == 0
        assert db_migrations.migrate_database(engine)['backup'] is None
    finally:
        engine.dispose()
