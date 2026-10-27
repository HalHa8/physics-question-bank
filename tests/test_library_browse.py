"""Library counts and filters share the v3 single-position classification contract."""

import copy
import json

import pytest
from sqlalchemy import event

from mathbank.database import KnowledgePoint, Question, QuestionCurriculum, QuestionKnowledgePoint, QuestionSubKnowledge


@pytest.fixture
def library(client, db_session, monkeypatch):
    import main
    metadata = {'curriculum_version': 'P', 'curriculum': {
        '甲册': {'第一章': ['同名小节', '未覆盖'], '第二章': ['同名小节']},
        '乙册': {'第一章': ['同名小节']}},
        'question_types': [{'value': 'experiment', 'label': '实验题'}, {'value': 'custom', 'label': '自定义题型'}],
        'difficulties': [{'value': 'normal', 'label': '基础题'}]}
    monkeypatch.setattr(main, 'METADATA_CACHE', metadata)

    def add(**values):
        values = {'content': 'synthetic private stem', 'category_compulsory': '甲册',
                  'category_chapter': '第一章', 'category_knowledge': '同名小节',
                  'question_type': 'experiment', 'difficulty': 'normal', **values}
        row = Question(**values)
        db_session.add(row); db_session.commit()
        return row
    return client, db_session, metadata, add


def overview(client):
    response = client.get('/api/library/overview')
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_counts_and_read_only(library):
    client, db, metadata, _ = library
    original = copy.deepcopy(metadata)
    statements = []
    def record(_conn, _cursor, sql, *_):
        statements.append(sql)
    event.listen(db.bind, 'before_cursor_execute', record)
    try:
        data = overview(client)
    finally:
        event.remove(db.bind, 'before_cursor_execute', record)
    assert data['total'] == data['unclassified'] == 0
    assert data['coverage'] == dict(covered_sections=0, total_sections=4, confirmed_points=0, pending_questions=0)
    assert all(not rows for rows in data['dimensions'].values())
    assert metadata == original
    assert not any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in statements)
    assert not any('questions.content' in sql for sql in statements)


@pytest.mark.parametrize('changes,expected', [
    ({}, 0), ({'category_knowledge': ''}, 0), ({'category_knowledge': '旧小节'}, 0),
    ({'category_compulsory': ''}, 1), ({'category_compulsory': '已删除教材'}, 1),
    ({'category_chapter': ''}, 1), ({'category_chapter': '失效章节'}, 1),
    ({'question_type': ''}, 1), ({'question_type': '旧题型'}, 1),
    ({'difficulty': ''}, 1), ({'difficulty': '旧难度'}, 1),
    ({'question_type': 'custom'}, 0),
])
def test_unclassified_validates_values_not_only_presence(library, changes, expected):
    client, _, _, add = library
    item = add(**changes)
    data = overview(client)
    result = client.get('/api/questions', params={'page': 1, 'classification_status': 'unclassified'}).json()
    assert data['unclassified'] == result['total'] == expected
    assert [row['id'] for row in result['items']] == ([item.id] if expected else [])


def test_path_counts_match_paginated_filters_and_ignore_legacy_evidence(library):
    client, db, _, add = library
    first = add()
    add(category_compulsory='乙册')
    add(category_chapter='第二章')
    add(category_chapter='已删章节')
    add(category_knowledge='')
    mirror = QuestionCurriculum(question_id=first.id, version_code='P', compulsory='甲册', chapter='第一章', knowledge='同名小节')
    mirror.sub_knowledge_rows.append(QuestionSubKnowledge(compulsory='甲册', chapter='第一章', knowledge='未覆盖', position=0))
    db.add(mirror); db.commit()
    data = overview(client)
    assert data['coverage']['covered_sections'] == 3
    assert data['books'][0]['unassigned'] == 1
    for book in data['books']:
        paths = [({'compulsory': book['name']}, book['count'])]
        paths.append(({'compulsory': book['name'], 'classification_status': 'book_unassigned'}, book['unassigned']))
        for chapter in book['chapters']:
            paths.append(({'compulsory': book['name'], 'chapter': chapter['name']}, chapter['count']))
            for section in chapter['sections']:
                paths.append(({'compulsory': book['name'], 'chapter': chapter['name'], 'knowledge': section['name']}, section['count']))
        for params, expected in paths:
            result = client.get('/api/questions', params={'page': 1, 'page_size': 1, **params}).json()
            assert result['total'] == expected, params
    assert data['books'][0]['chapters'][0]['sections'][1]['count'] == 0


def test_filter_composes_and_recounts_edits_without_total_change(library):
    client, db, metadata, add = library
    first = add(category_chapter='', content='检索命中')
    add(category_chapter='', question_type='custom')
    params = {'page': 1, 'classification_status': 'unclassified', 'qtype': 'experiment', 'q': '检索命中'}
    result = client.get('/api/questions', params=params).json()
    assert result['total'] == 1 and result['items'][0]['id'] == first.id
    first.category_chapter = '第一章'; db.commit()
    assert overview(client)['unclassified'] == 1
    assert client.get('/api/questions', params=params).json()['total'] == 0
    metadata['question_types'] = [item for item in metadata['question_types'] if item['value'] != 'experiment']
    assert overview(client)['unclassified'] == 2
    assert client.get('/api/questions', params={'classification_status': 'oops'}).status_code == 400


def test_statistics_distinct_tags_sources_and_confirmed_codes(library):
    client, db, _, add = library
    one = add(tags='力， 力,运动', source='<img src=x onerror=alert(1)>')
    two = add(tags='力', source='试卷乙', question_type='custom')
    three = add(tags='', source='')
    for code in ['local:a', 'local:b']:
        db.add(KnowledgePoint(code=code, name='同名知识点', original_name='同名知识点', source='local'))
    db.flush()
    db.add_all([
        QuestionKnowledgePoint(question_id=one.id, point_code='local:a', role='main', status='confirmed'),
        QuestionKnowledgePoint(question_id=two.id, point_code='local:a', role='auxiliary', status='confirmed'),
        QuestionKnowledgePoint(question_id=one.id, point_code='local:b', role='auxiliary', status='suggested'),
        QuestionKnowledgePoint(question_id=three.id, point_code='local:b', role='main', status='confirmed'),
    ]); db.commit()
    data = overview(client)
    assert data['coverage']['confirmed_points'] == 2
    assert data['coverage']['pending_questions'] == 1
    assert {x['value']: x['count'] for x in data['dimensions']['tag']} == {'力': 2, '运动': 1, '': 1}
    assert sum(x['count'] for x in data['dimensions']['source']) == 3
    assert data['dimensions']['question_type'][1]['label'] == '自定义题型'
    assert 'synthetic private stem' not in json.dumps(data)
    assert 'content' not in json.dumps(data)


def test_null_metadata_and_bounded_aggregate_queries(library):
    client, db, _, add = library
    item = add()
    item.question_type = None
    item.category_compulsory = None
    db.commit()
    statements = []
    def record(_conn, _cursor, sql, *_):
        statements.append(sql)
    event.listen(db.bind, 'before_cursor_execute', record)
    try:
        data = overview(client)
    finally:
        event.remove(db.bind, 'before_cursor_execute', record)
    assert data['unclassified'] == 1
    assert len(statements) <= 10
    assert not any('questions.content' in sql or 'questions.answer_markdown' in sql for sql in statements)


@pytest.mark.parametrize('section', ['', None, '第一章', '旧小节', '另一章的小节'])
def test_section_unassigned_counts_and_filter_are_read_only(library, section):
    client, db, _, add = library
    item = add(category_knowledge=section, content='待细分合成题')
    if section is None:  # ORM insert defaults otherwise turn None into an empty string.
        item.category_knowledge = None
        db.commit()
    add(category_knowledge='同名小节')
    add(category_chapter='已失效章节', category_knowledge='')
    add(category_compulsory='乙册', category_knowledge='')
    data = overview(client)
    assert data['section_unassigned'] == 2
    chapter = data['books'][0]['chapters'][0]
    assert chapter['count'] == 2 and chapter['section_unassigned'] == 1
    assert chapter['count'] == chapter['section_unassigned'] + sum(s['count'] for s in chapter['sections'])
    params = {'page': 1, 'compulsory': '甲册', 'chapter': '第一章',
              'classification_status': 'section_unassigned', 'qtype': 'experiment', 'q': '待细分'}
    result = client.get('/api/questions', params=params).json()
    assert result['total'] == 1 and result['items'][0]['id'] == item.id
    db.refresh(item)
    assert item.category_knowledge == section
    item.category_knowledge = '同名小节'
    db.commit()
    assert overview(client)['section_unassigned'] == 1
    assert client.get('/api/questions', params=params).json()['total'] == 0


def test_section_status_uses_full_path_and_handles_empty_chapter(library):
    client, db, metadata, add = library
    metadata['curriculum']['甲册']['空章'] = []
    add(category_chapter='空章', category_knowledge='')
    add(category_chapter='第二章', category_knowledge='未覆盖')  # Exists only in 第一章.
    add(category_compulsory='无效教材', category_knowledge='')
    result = client.get('/api/questions', params={'classification_status': 'section_unassigned'}).json()
    assert len(result) == overview(client)['section_unassigned'] == 2
