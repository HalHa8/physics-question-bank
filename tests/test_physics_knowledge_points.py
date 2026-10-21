"""Manual independent physics points: no live database, assets or model calls."""

import json
import sqlite3
from contextlib import closing

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from mathbank import database, db_migrations
from mathbank.backup import create_full_backup, restore_full_backup, verify_full_backup
from mathbank.database import KnowledgePoint, Question, QuestionKnowledgePoint
from mathbank.knowledge_points import (
    apply_knowledge_point_filters, create_local_point, list_catalog,
    normalize_question_points, replace_question_points, resource_points, seed_catalog,
)

MAIN = 'phy:momentum-conservation'
AUX = 'phy:work-energy-theorem'
FORM = {"content": r"碰撞后滑行，$\vec{v}=-2.00\,\mathrm{m/s}$，电流 $i=1.60\,\mathrm{mA}$。",
        "question_type": "detailed_answer", "difficulty": "normal",
        "category_compulsory": "自定义册", "category_chapter": "教师自编综合章",
        "category_knowledge": "保留的旧小节", "tags": "碰撞,分阶段分析", "image_paths": "[]"}


@pytest.fixture
def catalog(db_session):
    seed_catalog(db_session)
    db_session.commit()
    return db_session


def test_physics_catalogue_identity_mapping_and_manual_names(catalog):
    definitions = resource_points()
    assert len(definitions) == 80
    assert len({item['code'] for item in definitions}) == 80
    assert all(item['code'].startswith('phy:') and item['source'] == 'physicsbank' for item in definitions)
    assert all(path['version_code'] == 'P' for item in definitions for path in item['curriculum_paths'])
    point = catalog.get(KnowledgePoint, MAIN)
    point.name = '老师自定义显示名'
    point.aliases = ['动量守恒']
    catalog.commit()
    assert seed_catalog(catalog) == {'added_points': 0}
    catalog.commit()
    assert point.name == '老师自定义显示名' and point.aliases == ['动量守恒']
    assert point.original_name == '动量守恒定律'
    assert list_catalog(catalog, q='动量守恒')['total'] == 1
    assert list_catalog(catalog, q='#' + MAIN)['items'][0]['code'] == MAIN
    assert list_catalog(catalog, q='%', limit=5)['total'] == 0


def test_catalogue_paths_do_not_limit_cross_chapter_question_labels(catalog):
    located = list_catalog(catalog, compulsory='选择性必修第一册', chapter='第一章 动量守恒定律')
    assert MAIN in {point['code'] for point in located['items']}
    assert AUX not in {point['code'] for point in located['items']}
    question = Question(**{key: value for key, value in FORM.items() if key != 'image_paths'})
    catalog.add(question)
    replace_question_points(question, normalize_question_points([{'code': MAIN}, {'code': AUX, 'role': 'auxiliary'}], catalog), catalog)
    catalog.commit()
    assert question.category_knowledge == FORM['category_knowledge']
    assert len(question.knowledge_points) == 2
    assert question.tags == FORM['tags'] and question.content == FORM['content']
    assert list(question.to_summary_dict()['knowledge_points'][0]) == ['code', 'name', 'role', 'status']


@pytest.mark.parametrize('value', ['{', None, {}, ['x'], [{'code': 'unknown'}], [{'code': MAIN}, {'code': MAIN}],
                                  [{'code': MAIN, 'role': 'wrong'}], [{'code': MAIN, 'status': 'invalid'}], [{}], [True]])
def test_malformed_manual_labels_fail_without_writes(catalog, value):
    with pytest.raises(ValueError):
        normalize_question_points(value, catalog)
    assert catalog.query(QuestionKnowledgePoint).count() == 0


def test_new_local_point_is_stable_and_not_a_mathematical_platform_identity(catalog):
    point = create_local_point(catalog, {'name': '带电粒子复合场分阶段运动', 'aliases': ['复合场分阶段']})
    code = point.code
    catalog.commit()
    assert code.startswith('local:') and list_catalog(catalog, q='复合场分阶段')['items'][0]['code'] == code
    assert seed_catalog(catalog)['added_points'] == 0
    assert catalog.get(KnowledgePoint, code).aliases == ['复合场分阶段']
    with pytest.raises(ValueError, match='同名'):
        create_local_point(catalog, {'name': point.name})
    with pytest.raises(ValueError):
        create_local_point(catalog, {'name': '非法映射', 'curriculum_paths': [{'version_code': 'A'}]})


def test_indexed_any_all_roles_and_unlabeled_filters(catalog):
    ids = []
    for index, points in enumerate(([{'code': MAIN}], [{'code': MAIN}, {'code': AUX, 'role': 'auxiliary'}], [])):
        question = Question(content='物理综合题' + str(index), question_type='experiment', tags='原标签')
        catalog.add(question)
        replace_question_points(question, normalize_question_points(points, catalog), catalog)
        catalog.flush()
        ids.append(question.id)
    catalog.commit()
    query = catalog.query(Question)
    assert {q.id for q in apply_knowledge_point_filters(query, [MAIN, AUX], 'any')} == set(ids[:2])
    assert [q.id for q in apply_knowledge_point_filters(query, [MAIN, AUX], 'all')] == [ids[1]]
    assert not apply_knowledge_point_filters(query, [MAIN, AUX], 'all', 'main').all()
    assert [q.id for q in apply_knowledge_point_filters(query, [], unlabeled=True)] == [ids[2]]
    with pytest.raises(ValueError):
        apply_knowledge_point_filters(query, [MAIN], unlabeled=True)
    catalog.delete(catalog.get(Question, ids[1]))
    catalog.commit()
    assert catalog.query(QuestionKnowledgePoint).count() == 1


def test_manual_api_roundtrip_old_client_preservation_and_atomic_validation(client, catalog):
    from main import LOCAL_TOKEN
    headers = {'X-Local-Token': LOCAL_TOKEN}
    assert client.get('/api/knowledge-points?q=动量').json()['version_code'] == 'P'
    assert client.post('/api/knowledge-points', json={'name': '未授权'}).status_code == 403
    added = client.post('/api/knowledge-points', json={'name': '测试专用知识点', 'aliases': ['测试别名']}, headers=headers)
    assert added.status_code == 200
    assert client.get('/api/knowledge-points?q=测试别名').json()['total'] == 1
    payload = {**FORM, 'knowledge_points': json.dumps([{'code': MAIN}, {'code': AUX, 'role': 'auxiliary'}])}
    created = client.post('/api/questions', data=payload, headers=headers)
    assert created.status_code == 200, created.text
    qid = created.json()['question']['id']
    detail = client.get(f'/api/questions/{qid}').json()
    assert [p['code'] for p in detail['knowledge_points']] == [MAIN, AUX]
    for key in ('content', 'tags', 'category_compulsory', 'category_chapter', 'category_knowledge'):
        assert detail[key] == FORM[key]
    bad = client.put(f'/api/questions/{qid}', data={**FORM, 'content': '不应保存', 'knowledge_points': '[{"code":"not-real"}]'}, headers=headers)
    assert bad.status_code == 400
    assert client.get(f'/api/questions/{qid}').json() == detail
    assert client.put(f'/api/questions/{qid}', data=FORM, headers=headers).status_code == 200
    assert len(client.get(f'/api/questions/{qid}').json()['knowledge_points']) == 2
    found = client.get('/api/questions', params={'knowledge_points': MAIN + ',' + AUX, 'point_match': 'all', 'page': 1}).json()
    assert found['total'] == 1 and found['items'][0]['id'] == qid
    assert client.get('/api/questions?point_match=invalid').status_code == 400
    assert client.put(f'/api/questions/{qid}', data={**FORM, 'knowledge_points': '[]'}, headers=headers).status_code == 200
    assert client.get(f'/api/questions/{qid}').json()['knowledge_points'] == []


def _v10_engine(tmp_path):
    path = tmp_path / 'synthetic-v10.db'
    engine = create_engine('sqlite:///' + path.as_posix())
    database.Base.metadata.create_all(engine)
    with Session(engine) as session:
        question = Question(content=FORM['content'], tags=FORM['tags'], category_knowledge=FORM['category_knowledge'])
        session.add(question)
        session.commit()
    with engine.begin() as connection:
        for table in ('question_knowledge_points', 'knowledge_point_curriculums', 'knowledge_points'):
            connection.exec_driver_sql('DROP TABLE ' + table)
        connection.exec_driver_sql('PRAGMA user_version=10')
    return path, engine


def test_v10_migration_backup_first_preserves_every_old_question_column(tmp_path, monkeypatch):
    monkeypatch.setattr(db_migrations, 'SCHEMA_SNAPSHOT_DIR', tmp_path / 'schema-backups')
    path, engine = _v10_engine(tmp_path)
    try:
        with engine.connect() as conn:
            before = conn.exec_driver_sql('SELECT * FROM questions').all()
        result = db_migrations.migrate_database(engine)
        assert result['from_version'] == 10 and result['to_version'] == db_migrations.LATEST_SCHEMA_VERSION
        with closing(sqlite3.connect(result['backup'])) as backup:
            assert backup.execute('PRAGMA user_version').fetchone()[0] == 10
            assert 'knowledge_points' not in {row[0] for row in backup.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT * FROM questions').all() == before
            assert conn.exec_driver_sql('SELECT COUNT(*) FROM question_knowledge_points').scalar_one() == 0
        assert db_migrations.migrate_database(engine)['backup'] is None
    finally:
        engine.dispose()


def test_migration_failure_rolls_back_tables_and_version(tmp_path, monkeypatch):
    monkeypatch.setattr(db_migrations, 'SCHEMA_SNAPSHOT_DIR', tmp_path / 'schema-backups')
    _, engine = _v10_engine(tmp_path)
    def fail(_connection):
        raise RuntimeError('controlled knowledge schema validation failure')
    monkeypatch.setattr(db_migrations, '_validate_knowledge_point_schema', fail)
    try:
        with pytest.raises(RuntimeError, match='controlled knowledge'):
            db_migrations.migrate_database(engine)
        assert db_migrations.schema_version(engine) == 10
        assert not db_migrations.KNOWLEDGE_POINT_TABLES.intersection(inspect(engine).get_table_names())
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT content FROM questions').scalar_one() == FORM['content']
    finally:
        engine.dispose()


def test_full_backup_restore_keeps_custom_points_roles_and_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr(db_migrations, 'SCHEMA_SNAPSHOT_DIR', tmp_path / 'schema-backups')
    path, engine = _v10_engine(tmp_path)
    uploads = tmp_path / 'uploads'; uploads.mkdir()
    try:
        db_migrations.migrate_database(engine)
        with Session(engine) as session:
            seed_catalog(session)
            point = create_local_point(session, {'name': '教师自建点', 'aliases': ['个人简称']})
            code = point.code
            question = session.query(Question).one()
            replace_question_points(question, [{'code': MAIN, 'role': 'main'}, {'code': code, 'role': 'auxiliary'}], session)
            session.commit()
    finally:
        engine.dispose()
    archive = create_full_backup(output_dir=tmp_path / 'snapshots', database_path=path, uploads_dir=uploads,
                                 metadata_path=tmp_path / 'metadata.json', retention=None)
    manifest = verify_full_backup(archive)
    assert manifest['database']['row_counts']['knowledge_points'] == 81
    assert manifest['database']['row_counts']['question_knowledge_points'] == 2
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute('UPDATE knowledge_points SET aliases=? WHERE code=?', ('[]', code))
    restore_full_backup(archive, database_path=path, uploads_dir=uploads, metadata_path=tmp_path / 'metadata.json',
                        safety_backup_dir=tmp_path / 'safety', runtime_lock_path=tmp_path / 'runtime.lock')
    restored_engine = create_engine('sqlite:///' + path.as_posix())
    try:
        with Session(restored_engine) as session:
            question = session.query(Question).one()
            assert [p['role'] for p in question.to_dict()['knowledge_points']] == ['main', 'auxiliary']
            assert session.get(KnowledgePoint, code).aliases == ['个人简称']
            assert question.content == FORM['content']
    finally:
        restored_engine.dispose()
