"""Independent physics knowledge points, adapted from MathBank 3.0.

Textbook paths are recommendations, never replacements for authored locations
or free-form tags. Reads do not seed data or invoke AI. Only callers commit.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from functools import lru_cache

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from mathbank.curriculums import load_curriculum
from mathbank.paths import PROJECT_ROOT

MAX_QUESTION_POINTS = 64
METADATA_FIELDS = ('scope', 'evidence_source', 'evidence', 'reason', 'origin')
CATALOG_FILE = PROJECT_ROOT / "mathbank" / "resources" / "physics_knowledge_points.json"


def _text(value, field, maximum=200, *, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{field}格式无效或超过允许长度")
    value = value.strip()
    if not value and not allow_empty:
        raise ValueError(f"{field}不能为空")
    return value


def _aliases(value):
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("搜索别名必须是最多32项的列表")
    result = [_text(item, "搜索别名") for item in value]
    if len(set(result)) != len(result):
        raise ValueError("搜索别名重复")
    return result


def _normalize_path(path):
    if not isinstance(path, dict) or path.get("version_code", "P") != "P":
        raise ValueError("首版知识点只接受物理 P 教材映射")
    tree = load_curriculum("P")
    comp = _text(path.get("compulsory"), "册名", 100)
    chapter = _text(path.get("chapter"), "章节", 100)
    section = _text(path.get("knowledge", ""), "小节", 100, allow_empty=True)
    if comp not in tree or chapter not in tree[comp] or (section and section not in tree[comp][chapter]):
        raise ValueError("知识点教材映射不存在于物理 P 目录")
    return {"version_code": "P", "compulsory": comp, "chapter": chapter, "knowledge": section,
            "reference_section": section or chapter, "level": "leaf" if section else "chapter"}


@lru_cache(maxsize=1)
def resource_points():
    resource = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    if resource.get("schema_version") != "physicsbank-knowledge-points-v1":
        raise ValueError("物理知识点资源版本无效")
    sections = {}
    for comp, chapters in load_curriculum("P").items():
        for chapter, names in chapters.items():
            for name in names:
                sections.setdefault(name, []).append({"compulsory": comp, "chapter": chapter, "knowledge": name})
    result, codes = [], set()
    for item in resource["points"]:
        code = _text(item.get("code"), "知识点编码", 100)
        if not re.fullmatch(r"phy:[a-z0-9]+(?:-[a-z0-9]+)*", code) or code in codes:
            raise ValueError("物理知识点编码重复或无效")
        codes.add(code)
        paths = []
        for section in item.get("sections", []):
            matches = sections.get(section, [])
            if len(matches) != 1:
                raise ValueError("知识点小节映射缺失或存在歧义：" + str(section))
            path = _normalize_path(matches[0])
            if path in paths:
                raise ValueError("知识点教材映射重复")
            paths.append(path)
        name = _text(item.get("name"), "知识点名称")
        result.append({"code": code, "name": name, "original_name": name, "source": "physicsbank",
                       "aliases": _aliases(item.get("aliases", [])), "curriculum_paths": paths})
    if not result:
        raise ValueError("物理知识点资源为空")
    return result


def seed_catalog(db):
    """Insert missing identities/paths; preserve teacher names and aliases."""
    from mathbank.database import KnowledgePoint, KnowledgePointCurriculum
    existing = {point.code: point for point in db.query(KnowledgePoint).options(selectinload(KnowledgePoint.curriculum_paths)).all()}
    added = 0
    for definition in resource_points():
        point = existing.get(definition["code"])
        if point is None:
            point = KnowledgePoint(**{key: definition[key] for key in ("code", "name", "original_name", "source")})
            point.aliases = definition["aliases"]
            db.add(point)
            added += 1
        paths = [path.to_dict() for path in point.curriculum_paths]
        for path in definition["curriculum_paths"]:
            if path not in paths:
                point.curriculum_paths.append(KnowledgePointCurriculum(**path))
    db.flush()
    return {"added_points": added}


def list_catalog(db, q="", compulsory="", chapter="", knowledge="", limit=100, offset=0, *, version_code="P"):
    from mathbank.database import KnowledgePoint, KnowledgePointCurriculum
    if version_code != "P":
        raise ValueError("物理知识点只提供 P 教材映射")
    q = _text(q, "知识点搜索", 200, allow_empty=True)
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or not 0 <= offset <= 2**63 - 1:
        raise ValueError("知识点分页参数无效")
    query = db.query(KnowledgePoint).options(selectinload(KnowledgePoint.curriculum_paths))
    if q.startswith("#"):
        query = query.filter(KnowledgePoint.code == q[1:])
    elif q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        needle = "%" + escaped + "%"
        query = query.filter(or_(*(column.ilike(needle, escape="\\") for column in
                                  (KnowledgePoint.name, KnowledgePoint.original_name, KnowledgePoint._aliases, KnowledgePoint.code))))
    if compulsory or chapter or knowledge:
        conditions = [KnowledgePointCurriculum.version_code == "P"]
        for key, value in (("compulsory", compulsory), ("chapter", chapter), ("knowledge", knowledge)):
            if value:
                conditions.append(getattr(KnowledgePointCurriculum, key) == _text(value, "教材位置", 100))
        query = query.filter(KnowledgePoint.curriculum_paths.any(and_(*conditions)))
    total = query.count()
    return {"items": [point.to_dict() for point in query.order_by(KnowledgePoint.name, KnowledgePoint.code).offset(offset).limit(limit)],
            "total": total, "limit": limit, "offset": offset, "version_code": "P", "hierarchy": []}


def create_local_point(db, payload):
    from mathbank.database import KnowledgePoint, KnowledgePointCurriculum
    if not isinstance(payload, dict):
        raise ValueError("新增知识点必须是对象")
    if set(payload) - {"name", "aliases", "curriculum_paths", "paths", "expected_version_code"}:
        raise ValueError("新增知识点字段无效")
    name = _text(payload.get("name"), "知识点名称")
    aliases = _aliases(payload.get("aliases", []))
    names = {name.casefold(), *(alias.casefold() for alias in aliases)}
    # Reserve SQLite's writer before checking names.  The reservation spans
    # the caller's eventual commit/rollback, including across app processes;
    # another creator can only check again after this creator has committed.
    connection = db.connection()
    raw_connection = connection.connection.dbapi_connection
    if isinstance(raw_connection, sqlite3.Connection) and not raw_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    # Catalogue creation is rare and bounded; exact aliases require decoding
    # their JSON arrays.  Question searches below remain entirely indexed SQL.
    for existing in db.query(KnowledgePoint).all():
        existing_names = {existing.name.strip().casefold(), existing.original_name.strip().casefold(), *(alias.strip().casefold() for alias in existing.aliases)}
        if names & existing_names:
            raise ValueError(f"已有同名或同义知识点：{existing.name}（{existing.code}）")
    paths_value = payload.get("curriculum_paths", payload.get("paths", []))
    if not isinstance(paths_value, list) or len(paths_value) > 32:
        raise ValueError("知识点教材归属必须是最多32项的列表")
    paths = [_normalize_path(path) for path in paths_value]
    if len({tuple(path.values()) for path in paths}) != len(paths):
        raise ValueError("知识点教材归属重复")
    point = KnowledgePoint(code=f"local:{uuid.uuid4().hex}", name=name, original_name=name, source="local")
    point.aliases = aliases
    point.curriculum_paths = [KnowledgePointCurriculum(**path) for path in paths]
    db.add(point)
    db.flush()
    return point

def normalize_question_points(value, db):
    from mathbank.database import KnowledgePoint
    if isinstance(value, str):
        if len(value) > 2_000_000:
            raise ValueError("知识点标注超过允许长度")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("知识点标注不是有效 JSON") from exc
    if not isinstance(value, list) or len(value) > MAX_QUESTION_POINTS:
        raise ValueError("题目知识点必须是最多64项的列表")
    normalized = []
    codes = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("题目知识点必须是对象")
        code = _text(item.get("code"), "知识点编码", 100)
        if code in codes:
            raise ValueError(f"题目知识点重复：{code}")
        codes.add(code)
        role = item.get("role", "main")
        status = item.get("status", "confirmed")
        if not isinstance(role, str) or role not in {"main", "auxiliary"} or not isinstance(status, str) or status not in {"confirmed", "suggested"}:
            raise ValueError("知识点的主要/辅助角色或确认状态无效")
        row = {"code": code, "role": role, "status": status}
        for field in METADATA_FIELDS:
            metadata = item.get(field)
            try:
                encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False)
            except (ValueError, TypeError, RecursionError) as exc:
                raise ValueError(f"知识点{field}不是有效JSON值") from exc
            if len(encoded) > 32768:
                raise ValueError(f"知识点{field}超过允许长度")
            row[field] = metadata
        normalized.append(row)
    known = {row[0] for row in db.query(KnowledgePoint.code).filter(KnowledgePoint.code.in_(codes)).all()} if codes else set()
    if codes - known:
        raise ValueError("未知知识点编码：" + ", ".join(sorted(codes - known)))
    return normalized

def replace_question_points(question, normalized, db):
    """Replace explicit selections inside the caller's question transaction."""

    from mathbank.database import KnowledgePoint, QuestionKnowledgePoint
    existing = {row.point_code: row for row in question.knowledge_points}
    points = {row.code: row for row in db.query(KnowledgePoint).filter(KnowledgePoint.code.in_([item["code"] for item in normalized])).all()} if normalized else {}
    rows = []
    for position, item in enumerate(normalized):
        row = existing.get(item["code"]) or QuestionKnowledgePoint(point_code=item["code"])
        row.point = points[item["code"]]
        row.role, row.status, row.position = item["role"], item.get("status", "confirmed"), position
        for field in METADATA_FIELDS:
            setattr(row, field, json.dumps(item.get(field), ensure_ascii=False, allow_nan=False))
        rows.append(row)
    question.knowledge_points = rows

def apply_knowledge_point_filters(query, codes, match_mode="any", role_scope="all", status_scope="confirmed", unlabeled=False):
    """Apply exact ANY/ALL selections using indexed SQL, preserving other filters."""

    from mathbank.database import Question, QuestionKnowledgePoint
    if isinstance(codes, str):
        codes = codes.split(",") if codes else []
    if not isinstance(codes, (list, tuple)) or len(codes) > MAX_QUESTION_POINTS:
        raise ValueError("知识点筛选必须是最多64项编码的列表")
    codes = list(dict.fromkeys(_text(code, "知识点编码", 100) for code in codes))
    if not isinstance(match_mode, str) or match_mode not in {"any", "all"} or not isinstance(role_scope, str) or role_scope not in {"main", "all"} or not isinstance(status_scope, str) or status_scope not in {"confirmed", "all"}:
        raise ValueError("知识点筛选模式无效")
    if not isinstance(unlabeled, bool):
        raise ValueError("未标注筛选必须是布尔值")
    conditions = []
    if role_scope == "main":
        conditions.append(QuestionKnowledgePoint.role == "main")
    if status_scope == "confirmed":
        conditions.append(QuestionKnowledgePoint.status == "confirmed")
    if unlabeled:
        if codes:
            raise ValueError("未标注筛选不能同时选择知识点")
        unlabeled_conditions = [QuestionKnowledgePoint.status == "confirmed"] if status_scope == "confirmed" else []
        return query.filter(~Question.knowledge_points.any(and_(*unlabeled_conditions))) if unlabeled_conditions else query.filter(~Question.knowledge_points.any())
    if not codes:
        return query
    matches = select(QuestionKnowledgePoint.question_id).where(QuestionKnowledgePoint.point_code.in_(codes), *conditions)
    if match_mode == "all":
        matches = matches.group_by(QuestionKnowledgePoint.question_id).having(func.count(func.distinct(QuestionKnowledgePoint.point_code)) == len(codes))
    return query.filter(Question.id.in_(matches))

# Textbook P currently has a flat, authoritative section list; do not invent
# a mathematical-platform hierarchy or equate unrelated external identities.
def get_curriculum_ancestors(version_code="P"):
    return {}


def is_zxxk_catalog_code(code):
    """Recognize imported provenance only; never seed mathematical identities."""
    return isinstance(code, str) and re.fullmatch(r"zxxk:catalog:[1-9][0-9]*", code) is not None


def _resource_points():
    return resource_points()


_resource_points.cache_clear = resource_points.cache_clear
