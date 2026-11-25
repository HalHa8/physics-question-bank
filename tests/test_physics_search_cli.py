"""Offline PhysicsBank CLI regressions using a synthetic library."""
import hashlib
import sqlite3
import sys

import pytest

from scripts import search_questions as cli


@pytest.fixture
def library(tmp_path, monkeypatch):
    path = tmp_path / "physics #题.db"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE questions(id INTEGER PRIMARY KEY, content TEXT,
                   question_type TEXT, category_compulsory TEXT, category_chapter TEXT,
                   category_knowledge TEXT, difficulty TEXT, source TEXT, answer_markdown TEXT,
                   review TEXT, association_group_id TEXT, tags TEXT)""")
        for qid, content, source in [
            (4, "拉力 2.0 N 100%_ ![电路](/static/uploads/模拟卷.png)", None),
            (8, "拉力 2.0 N 100%_", "模拟卷"),
            (15, "拉力 2.0 N 100%_", "真题"),
            (16, "拉力 2.0 n 100%_", "真题"),
        ]:
            db.execute("INSERT INTO questions VALUES (?,?,'experiment','','','','normal',?,"
                       "'方向向右',NULL,'group1','力')", (qid, content, source))
    before = hashlib.sha256(path.read_bytes()).digest()
    monkeypatch.setattr(cli, "DB_PATH", str(path))
    yield
    assert hashlib.sha256(path.read_bytes()).digest() == before


def run(args, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["search_questions", *args])
    cli.main()
    return capsys.readouterr().out


def test_cli_filtered_web_numbers_and_literal_quantities(library, monkeypatch, capsys):
    args = ["--include", "content=2.0 N", "--include", "content=100%_", "--exclude", "模拟卷",
            "--include", "answer_markdown=方向向右", "-t", "experiment", "-d", "normal"]
    text = run(args, monkeypatch, capsys)
    assert [line for line in text.splitlines() if line.startswith("### ")] == ["### 题目 #3", "### 题目 #1"]
    assert "方向向右" not in text and "实验题 | 常规题" in text
    assert "### 题目 #3" in run([*args, "-n", "1"], monkeypatch, capsys)
    assert "### 题目 #1" not in run([*args, "-n", "1"], monkeypatch, capsys)
    assert len(cli.search_questions(associated_to_id=4)[0]) == 12


def test_cli_lookup_keeps_requested_order_and_reports_missing(library, monkeypatch, capsys):
    text = run(["--seq-nums", "#3,15", "--seq-nums", "1", "-a"], monkeypatch, capsys)
    assert "未找到网页题号 15" in text and "方向向右" in text
    assert text.index("### 题目 #3") < text.index("### 题目 #1")
    assert "### 题目 #2" in run(["--ids", "8"], monkeypatch, capsys)


def test_search_projection_preserves_visible_and_literal_text():
    src = '<img title="src=visible" srcset="foo.png 1x, bar.png 2x" alt="电路"> '
    text = cli._search_text(src + r'![力](模拟卷.png) \includegraphics{hidden.png} ' + chr(96) + '![例](code.png)' + chr(96))
    assert all(term in text for term in ("src=visible", "电路", "力", "code.png"))
    assert all(term not in text for term in ("foo.png", "bar.png", "模拟卷.png", "hidden.png"))


@pytest.mark.parametrize("args", [
    ["--include", "id=1"], ["--exclude", "source=  "], ["--include", "x"] * 9,
    ["--seq-nums", "0"], ["--seq-nums", "1,#1"], ["--seq-nums", "2", "--include", "电路"],
    ["--seq-nums", "#2", "--ids", "2"], ["--ids", "9223372036854775808"],
])
def test_invalid_filters_are_rejected_before_opening_db(args, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["search_questions", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
