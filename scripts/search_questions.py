#!/usr/bin/env python3
"""Read PhysicsBank questions using the same display numbers as the question list."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

from mathbank.curriculums import DEFAULT_DIFFICULTIES, DEFAULT_QUESTION_TYPES
from mathbank.paths import DATABASE_FILE
from mathbank.question_assets import image_search_spans


DB_PATH = str(DATABASE_FILE)
TEXT_FIELDS = ("content", "answer_markdown", "review", "source", "tags")
IMAGE_FIELDS = {"content", "answer_markdown", "review"}
TYPE_LABELS = {option["value"]: option["label"] for option in DEFAULT_QUESTION_TYPES}
DIFFICULTY_LABELS = {"easy": "简单", "medium": "中等", "hard": "困难"}
DIFFICULTY_LABELS.update({option["value"]: option["label"] for option in DEFAULT_DIFFICULTIES})


def _connect():
    path = Path(DB_PATH)
    if not path.is_file():
        sys.exit(f"Error: Database not found at {path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def get_association_group(question_id):
    with closing(_connect()) as db:
        row = db.execute("SELECT association_group_id FROM questions WHERE id=?", (question_id,)).fetchone()
    return (row[0] or "").strip() or None if row else None


def _search_text(value):
    text = value or ""
    if "![" not in text and "\\includegraphics" not in text and "<img" not in text.lower():
        return text
    chars = list(text)
    for start, end in image_search_spans(text):
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _rules(includes, excludes):
    if len(includes) + len(excludes) > 8:
        raise ValueError("最多可用 8 条包含和排除条件")
    for exclude, values in ((False, includes), (True, excludes)):
        for value in values:
            field, sep, term = value.partition("=")
            field, term = (field.strip(), term.strip()) if sep else ("all", field.strip())
            if field not in (*TEXT_FIELDS, "all") or not 1 <= len(term) <= 64 or "\0" in term:
                raise ValueError("关键词条件需要有效字段和 1 至 64 字的关键词")
            yield exclude, TEXT_FIELDS if field == "all" else (field,), term


def _read(query=None, qtype=None, difficulty=None, limit=50, associated_to_id=None,
          rules=(), numbers=None, by_id=False):
    # Rank only keys, across the entire library, before applying filters.
    sql = """
        WITH ranked AS (SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS seq_num FROM questions)
        SELECT q.id, content, question_type, category_compulsory, category_chapter, category_knowledge,
               difficulty, source, answer_markdown, review, association_group_id, tags, ranked.seq_num
        FROM questions q JOIN ranked ON ranked.id=q.id WHERE 1=1
    """
    params = []
    if associated_to_id:
        sql += """ AND q.id != ? AND association_group_id != '' AND association_group_id =
                   (SELECT trim(association_group_id) FROM questions WHERE id=?)"""
        params.extend((associated_to_id, associated_to_id))
    if query:
        fields = ("category_compulsory", "category_chapter", "category_knowledge", "content", "source", "tags")
        sql += " AND (" + " OR ".join(f"{field} LIKE ?" for field in fields) + ")"
        params.extend([f"%{query}%"] * len(fields))
    for field, value in (("question_type", qtype), ("difficulty", difficulty)):
        if value:
            sql += f" AND {field}=?"
            params.append(value)
    for exclude, fields, term in rules:
        matches = []
        for field in fields:
            raw = f"instr({field}, ?) > 0"
            params.append(term)
            if field in IMAGE_FIELDS:
                raw = f"CASE WHEN {raw} THEN instr(search_text({field}), ?) > 0 ELSE 0 END"
                params.append(term)
            matches.append(raw)
        condition = " OR ".join(matches)
        sql += f" AND ({condition}) " + ("IS NOT TRUE" if exclude else "IS TRUE")
    if numbers:
        key = "q.id" if by_id else "ranked.seq_num"
        sql += f" AND {key} IN (" + ",".join("?" for _ in numbers) + ")"
        params.extend(numbers)
    sql += " ORDER BY q.id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with closing(_connect()) as db:
        db.create_function("search_text", 1, _search_text, deterministic=True)
        return db.execute(sql, params).fetchall()


def search_questions(query=None, qtype=None, difficulty=None, limit=50, with_answers=False, associated_to_id=None):
    """Keep the original twelve-column result for Python callers."""
    return [row[:-1] for row in _read(query, qtype, difficulty, limit, associated_to_id)]


def _numbers(groups, display):
    result = []
    for group in groups:
        for item in group.split(","):
            token = item.strip()
            if display:
                token = token.removeprefix("#")
            digits = token.lstrip("0")
            if not digits.isascii() or not digits.isdecimal() or len(digits) > 19 or int(digits) >= 2**63:
                raise ValueError("题号和 ID 须为正整数")
            number = int(digits)
            if number in result or len(result) >= 100:
                raise ValueError("一次最多可查 100 个不重复的题号或 ID")
            result.append(number)
    return result


def format_type(t):
    return TYPE_LABELS.get(t, t)


def format_difficulty(d):
    return DIFFICULTY_LABELS.get(d, d)


def main():
    parser = argparse.ArgumentParser(description="只读检索本地 PhysicsBank 物理题库")
    parser.add_argument("-q", "--query", help="按原有模糊匹配检索")
    parser.add_argument("-t", "--type", help="题型，如 experiment")
    parser.add_argument("-d", "--difficulty", help="难度，如 normal")
    parser.add_argument("-n", "--limit", type=int, help="最多返回题数，默认 50，-1 为全部")
    parser.add_argument("-a", "--with-answers", action="store_true", help="显示解析和评析")
    parser.add_argument("-r", "--related-to", type=int, help="按内部 ID 查询关联题")
    for option in ("--include", "--exclude"):
        parser.add_argument(option, action="append", default=[], metavar="[FIELD=]TEXT",
                            help="叠加字面条件，可选字段 all、content、answer_markdown、review、source、tags")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--seq-nums", action="append", help="网页题号，可用逗号分隔及重复传参")
    selection.add_argument("--ids", action="append", help="按内部 ID 取题")
    args = parser.parse_args()
    try:
        rules = list(_rules(args.include, args.exclude))
        numbers = _numbers(args.seq_nums or args.ids or [], bool(args.seq_nums))
        if numbers and any((args.query, args.type, args.difficulty, args.related_to is not None,
                            args.limit is not None, rules)):
            raise ValueError("按号取题不能同时指定搜索条件或数量上限")
    except ValueError as exc:
        parser.error(str(exc))
    limit = args.limit if args.limit is not None else 50
    results = _read(args.query, args.type, args.difficulty, None if numbers else limit,
                    args.related_to, rules, numbers, bool(args.ids))
    if numbers:
        rows = {row[0] if args.ids else row[-1]: row for row in results}
        missing = [str(number) for number in numbers if number not in rows]
        if missing:
            print(("未找到内部 ID " if args.ids else "未找到网页题号 ") + "、".join(missing))
        results = [rows[number] for number in numbers if number in rows]

    if not results:
        if args.related_to:
            print(f"### No associated/related questions found for ID: #{args.related_to} (or it does not belong to any association group)")
        else:
            print(f"### No questions found matching query: '{args.query or 'All'}'")
        return

    title_msg = f"## 关联题目检索结果 (与 ID: #{args.related_to} 关联的题目)" if args.related_to else f"## 题库检索结果 (共找到 {len(results)} 道符合条件的题目)"
    print(f"{title_msg}\n")
    
    for row in results:
        q_id, content, question_type, compulsory, chapter, knowledge, difficulty, source, answer, review, group_id, tags, seq_num = row
        
        print(f"### 题目 #{seq_num}")
        print(f"- 内部 ID: {q_id}")
        print(f"- **分类学段**: `{compulsory or '未分类'}`")
        print(f"- **章节知识点**: `{chapter or '无'}` -> `{knowledge or '无'}`")
        print(f"- **题型/难度**: {format_type(question_type)} | {format_difficulty(difficulty)}")
        if source:
            print(f"- **来源**: *{source}*")
        if group_id:
            print(f"- **关联组 ID**: `{group_id}`")
        if tags:
            print(f"- **自定义标签**: *{tags}*")
        
        print(f"\n#### 【题干】\n{content}\n")
        
        if args.with_answers:
            if answer:
                print(f"#### 【答案与解析】\n{answer}\n")
            if review:
                print(f"#### 【教师点评】\n{review}\n")
        else:
            print(f"> [!NOTE]\n> *答案与详细解析已隐藏。如需查看，请在查询命令中添加 `-a` 或 `--with-answers` 参数。*\n")
            
        print("---\n")

if __name__ == "__main__":
    main()
