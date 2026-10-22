"""Read-only library navigation and aggregate statistics (no question payloads)."""

from collections import Counter
from dataclasses import dataclass
import re
from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import and_, false, func, or_
from sqlalchemy.orm import Session

from mathbank.application_state import RuntimeState
from mathbank.database import Question, QuestionKnowledgePoint, get_db


@dataclass(frozen=True)
class LibraryBrowseDependencies:
    state: RuntimeState
    get_current_curriculum: Callable


def classification_expression(metadata, status):
    """Use precisely the stored values used by the existing curriculum filters."""
    if status not in {'', 'unclassified', 'book_unassigned'}:
        raise HTTPException(400, '归类状态必须是 unclassified 或 book_unassigned')
    if not status:
        return None
    curriculum = metadata.get('curriculum', {})
    book = func.coalesce(Question.category_compulsory, '')
    chapter = func.coalesce(Question.category_chapter, '')
    valid_chapter = or_(false(), *(and_(book == name, chapter.in_(list(chapters)))
        for name, chapters in curriculum.items() if isinstance(chapters, dict)))
    if status == 'book_unassigned':
        return and_(book.in_(list(curriculum)), ~valid_chapter)
    types = [item['value'] for item in metadata.get('question_types', []) if item.get('value')]
    levels = [item['value'] for item in metadata.get('difficulties', []) if item.get('value')]
    return ~and_(valid_chapter, func.coalesce(Question.question_type, '').in_(types),
                 func.coalesce(Question.difficulty, '').in_(levels))


def get_library_overview(db: Session = Depends(get_db), *, dependencies: LibraryBrowseDependencies):
    """Aggregate the whole bank, independently of the current list filters.

    Legacy sub-knowledge rows are evidence only in v3 and are NOT curriculum
    positions. Counts intentionally match the current single-position API.
    """
    metadata = dependencies.state.METADATA_CACHE
    curriculum = dependencies.get_current_curriculum()
    rows = db.query(Question.category_compulsory, Question.category_chapter,
                    Question.category_knowledge, func.count(Question.id)).group_by(
                        Question.category_compulsory, Question.category_chapter,
                        Question.category_knowledge).all()
    books_count, chapters_count, sections_count = Counter(), Counter(), Counter()
    for book, chapter, section, count in rows:
        books_count[book] += count
        chapters_count[book, chapter] += count
        sections_count[book, chapter, section] += count
    books, covered, section_total = [], 0, 0
    for book, chapters in curriculum.items():
        if not isinstance(chapters, dict):
            continue
        children = []
        for chapter, sections in chapters.items():
            leaves = []
            for section in dict.fromkeys(sections if isinstance(sections, list) else []):
                count = sections_count[book, chapter, section]
                leaves.append({'name': section, 'count': count})
                covered += bool(count)
                section_total += 1
            children.append({'name': chapter, 'count': chapters_count[book, chapter], 'sections': leaves})
        books.append({'name': book, 'count': books_count[book], 'chapters': children,
                      'unassigned': books_count[book] - sum(item['count'] for item in children)})

    def distribution(column, configured=()):
        labels = {item['value']: item['label'] for item in configured}
        # Coalesce NULL and empty; do not merge distinct non-empty labels.
        value = func.coalesce(column, '')
        counts = dict(db.query(value, func.count(Question.id)).group_by(value).all())
        return [{'value': key, 'label': labels.get(key, key or '未填写'), 'count': count}
                for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]

    tags = Counter()
    untagged = 0
    # Stream only the tags column; never materialize stems, images or answers.
    for (raw,) in db.query(Question.tags).yield_per(500):
        values = {value.strip() for value in re.split('[,，]+', raw or '') if value.strip()}
        tags.update(values)
        untagged += not values
    tag_rows = [{'value': value, 'label': value, 'count': count}
                for value, count in sorted(tags.items(), key=lambda item: (-item[1], item[0]))]
    if untagged:
        tag_rows.append({'value': '', 'label': '未填写', 'count': untagged})
    confirmed = db.query(func.count(func.distinct(QuestionKnowledgePoint.point_code))).filter(
        QuestionKnowledgePoint.status == 'confirmed').scalar()
    pending = db.query(func.count(func.distinct(QuestionKnowledgePoint.question_id))).filter(
        QuestionKnowledgePoint.status == 'suggested').scalar()
    return {
        'total': sum(row[3] for row in rows),
        'unclassified': db.query(func.count(Question.id)).filter(classification_expression(
            {**metadata, 'curriculum': curriculum}, 'unclassified')).scalar(),
        'books': books,
        'coverage': {'covered_sections': covered, 'total_sections': section_total,
                     'confirmed_points': confirmed, 'pending_questions': pending},
        'dimensions': {'question_type': distribution(Question.question_type, metadata.get('question_types', [])),
                       'difficulty': distribution(Question.difficulty, metadata.get('difficulties', [])),
                       'source': distribution(Question.source), 'tag': tag_rows},
    }
