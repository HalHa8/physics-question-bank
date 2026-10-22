"""Physics P content and pending evidence survive task retry without replay."""
import uuid

from mathbank.database import Question, QuestionCurriculum
from mathbank.knowledge_points import seed_catalog, normalize_question_points, replace_question_points
from mathbank.application_factory import create_application
from mathbank.application_state import RuntimeState
from test_library_transfer_tasks_api import tasks_api, _start_import, _wait  # noqa: F401
from test_library_transfer_api import transfer_api, _question_count  # noqa: F401


def test_physics_task_package_keeps_units_vectors_images_and_pending_points(tasks_api, monkeypatch):
    api = tasks_api
    monkeypatch.setattr(api.main, 'get_active_version_code', lambda: 'P')
    content = r'质量 $m=2.00\,\mathrm{kg}$，$\vec{v}=-3.00\,\mathrm{m/s}$；电流 $i=1.60\,\mathrm{mA}$。保持电路串联和电源极性。' + '\n![电路](/static/uploads/figure.png)'
    location = {'compulsory': '选择性必修第一册', 'chapter': '第一章 动量守恒定律', 'knowledge': '动量守恒定律'}
    with api.sessions() as db:
        seed_catalog(db)
        question = Question(content=content, question_type='experiment', answer_markdown=r'$p=-6.00\,\mathrm{kg\,m/s}$',
            category_compulsory=location['compulsory'], category_chapter=location['chapter'], category_knowledge=location['knowledge'])
        question.curriculum_mappings = [QuestionCurriculum(version_code='P', **location)]
        question.image_paths = ['/static/uploads/figure.png']
        db.add(question); db.flush()
        evidence = {'code': 'phy:momentum-conservation', 'role': 'main', 'status': 'suggested',
            'evidence_source': 'content', 'evidence': r'$\vec{v}=-3.00\,\mathrm{m/s}$', 'origin': 'ai_classification'}
        replace_question_points(question, normalize_question_points([evidence], db), db)
        db.commit(); question_id = question.id
    export_id = str(uuid.uuid4())
    exported = api.client.post('/api/library-transfer/tasks/export', headers=api.headers,
        json={'client_request_id': export_id, 'question_ids': [question_id]})
    assert exported.status_code == 202, exported.text
    assert _wait(api, export_id)['status'] == 'completed'
    download = api.client.get(f'/api/library-transfer/tasks/{export_id}/download')
    assert download.status_code == 200 and 'PhysicsBank-' in download.headers['content-disposition']
    task_id = str(uuid.uuid4())
    assert _start_import(api, download.content, task_id).status_code == 202
    result = _wait(api, task_id)
    assert result['status'] == 'completed', result
    assert _question_count(api) == 2
    assert _start_import(api, download.content, task_id).status_code == 200
    assert _question_count(api) == 2  # Same accepted intent never appends twice.
    with api.sessions() as db:
        imported = db.query(Question).filter(Question.id != question_id).one()
        assert imported.content.split('\n')[0] == content.split('\n')[0]
        assert imported.question_type == 'experiment' and imported.answer_markdown == r'$p=-6.00\,\mathrm{kg\,m/s}$'
        assert (imported.category_compulsory, imported.category_chapter, imported.category_knowledge) == tuple(location.values())
        point = imported.knowledge_points[0].to_dict()
        assert point['code'] == evidence['code'] and point['status'] == 'suggested'
        assert point['evidence'] == evidence['evidence']
        assert imported.image_paths[0].startswith('/static/uploads/shared_')
        assert (api.uploads / imported.image_paths[0].rsplit('/', 1)[1]).read_bytes() == (api.uploads / 'figure.png').read_bytes()


def test_sharing_manager_is_application_owned_and_factory_without_initialize_has_no_receipts(tmp_path):
    applications = [create_application(initialize=False, state=RuntimeState(IS_TESTING=True, UPLOAD_DIR=str(tmp_path / name / 'uploads')))
                    for name in ('first', 'second')]
    assert not list(tmp_path.iterdir())
    try:
        managers = []
        for name, app in zip(('first', 'second'), applications):
            assert app.state._LIBRARY_TRANSFER_TASKS is None
            app.legacy_namespace['SYSTEM_GENERATED_DIR'] = tmp_path / name
            manager = app.resolve('_library_transfer_tasks')()
            assert manager is app.state._LIBRARY_TRANSFER_TASKS and not manager.started
            managers.append(manager)
        assert managers[0] is not managers[1]
        assert managers[0].root != managers[1].root
    finally:
        for app in applications:
            if app.state._LIBRARY_TRANSFER_TASKS is not None:
                app.state._LIBRARY_TRANSFER_TASKS.close()
            app.state.DOCUMENT_TASKS.shutdown(wait=True)
            app.state.DATABASE_EXPORT_QUEUE.close()
