from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from io import BytesIO
import os
import zipfile
import pytest

from mathbank.latex_diagnostics import build_local_latex_diagnostic, merge_ai_latex_diagnostic
from mathbank.database import Question
from mathbank.paper_helper import (
    build_answer_sheet_latex,
    build_latex_document,
    clean_content_for_latex,
    compile_tex_to_pdf,
    create_tex_zip_package,
)


def test_local_diagnostic_maps_cancel_command_to_package():
    tex = "\n".join([
        r"\documentclass{article}",
        r"\begin{document}",
        "% MathBank-Question-ID: 42",
        r"\begin{problem}",
        r"已知 $\cancel{x}=1$。",
        r"\end{problem}",
        r"\end{document}",
    ])
    log = "! Undefined control sequence.\nl.5 已知 $\\cancel{x}=1$。"
    result = build_local_latex_diagnostic(log, tex)
    assert result["package"] == "cancel"
    assert result["command"] == r"\cancel"
    assert result["question_id"] == "42"
    assert "题库题目 ID 42" in result["location"]
    assert "cancel 宏包" in result["cause"]


def test_local_diagnostic_supports_file_line_error_format():
    tex = "\n".join([
        r"\documentclass{article}",
        r"\begin{document}",
        "% MathBank-Question-ID: 51",
        r"公式 $\cancel{x}$。",
        r"\end{document}",
    ])
    log = "./paper.tex:4: Undefined control sequence.\nl.4 公式 $\\cancel{x}$。"
    result = build_local_latex_diagnostic(log, tex)
    assert result["command"] == r"\cancel"
    assert result["package"] == "cancel"
    assert result["question_id"] == "51"


def test_paper_tex_uses_portable_fontset_and_question_marker():
    tex = build_latex_document(
        "测试试卷",
        "",
        "exam",
        [{
            "question": {
                "id": 73,
                "question_type": "detailed_answer",
                "content": "求函数的最值。",
            },
            "score": 10,
        }],
    )
    assert r"\documentclass[fontset=fandol]{exam-zh}" in tex
    assert "% MathBank-Question-ID: 73" in tex


def test_paper_tex_preloads_common_math_and_table_packages():
    tex = build_latex_document("宏包测试", "", "exam", [])
    for package in (
        "amsmath", "mathtools", "cancel", "cases",
        "mhchem", "siunitx", "extarrows", "array",
        "booktabs", "tabularx", "longtable", "multirow", "makecell",
        "diagbox", "colortbl", "tabularray", "threeparttable",
    ):
        assert package in tex
    assert r"\UseTblrLibrary{booktabs}" in tex
    assert r"\providecommand{\bm}[1]{\symbf{#1}}" in tex
    assert "amssymb" not in tex
    assert "mathrsfs" not in tex


def test_answer_images_export_adjustbox_max_width_key():
    questions = [{
        "question": {
            "id": 82,
            "question_type": "detailed_answer",
            "content": "带图题。![](/static/uploads/question.png)",
            "answer_markdown": "解析图。![](/static/uploads/answer.png)",
        },
        "score": 10,
    }]

    answer_tex = build_latex_document(
        "答案图片测试", "", "exam", questions, include_answers=True
    )
    answer_sheet_tex = build_answer_sheet_latex("答题卡图片测试", "", questions)

    assert r"\usepackage[export]{adjustbox}" in answer_tex
    assert r"\includegraphics[max width=0.85\linewidth]{answer.png}" in answer_tex
    assert r"\usepackage[export]{adjustbox}" in answer_sheet_tex
    assert r"\includegraphics[max width=3.4cm]{question.png}" in answer_sheet_tex


def test_choice_empty_parentheses_do_not_leave_orphan_display_math():
    for content in (
        r"题干 $(\quad)$",
        r"题干 $（\quad）$",
        r"题干 $(\qquad)$",
        r"题干 $(\hspace{2em})$",
        r"题干 $（____）$",
        r"题干（$\quad$）",
        "题干 $",
    ):
        cleaned = clean_content_for_latex(content, q_type="single_choice")
        assert cleaned == r"题干 \paren"
        assert "$$" not in cleaned

    # A real, paired display formula must not be mistaken for an empty answer
    # parenthesis and removed.
    assert clean_content_for_latex(
        "$$x=1$$", q_type="single_choice"
    ) == r"$$x=1$$ \paren"


def test_tex_zip_image_directory_matches_generated_graphics_path(tmp_path):
    image_path = tmp_path / "curve.png"
    image_path.write_bytes(b"test image payload")
    questions = [{
        "question": {
            "id": 81,
            "question_type": "detailed_answer",
            "content": "带图题。![](/static/uploads/curve.png)",
        },
        "score": 10,
    }]
    paper_tex = build_latex_document("图片路径测试", "", "exam", questions)
    answer_sheet_tex = build_answer_sheet_latex("图片路径测试", "", questions)
    archive_bytes = create_tex_zip_package(
        "图片路径测试",
        paper_tex,
        "",
        [str(image_path)],
        answer_sheet_tex=answer_sheet_tex,
    )

    assert r"\graphicspath{{images/}{./}}" in paper_tex
    assert r"\graphicspath{{images/}{./}}" in answer_sheet_tex
    assert (
        r"\includegraphics[max width=5.0cm,max height=6.0cm,keepaspectratio]{curve.png}"
        in paper_tex
    )
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        assert "images/curve.png" in archive.namelist()
        assert r"\graphicspath{{images/}{./}}" in archive.read(
            "试卷正文.tex"
        ).decode("utf-8")
        assert r"\graphicspath{{images/}{./}}" in archive.read(
            "答题卡.tex"
        ).decode("utf-8")


def test_compile_rejects_error_even_if_xelatex_leaves_a_pdf():
    calls = []

    def fake_run(_cmd, *, cwd, **_kwargs):
        calls.append(cwd)
        Path(cwd, "paper.pdf").write_bytes(b"partial pdf")
        Path(cwd, "paper.log").write_text(
            "! Undefined control sequence.\nl.4 \\cancel{x}", encoding="utf-8"
        )
        return SimpleNamespace(
            returncode=1,
            stdout="! Undefined control sequence.\nl.4 \\cancel{x}",
            stderr="",
        )

    with patch("mathbank.paper_helper.subprocess.run", side_effect=fake_run):
        pdf_bytes, error = compile_tex_to_pdf("unique invalid tex for return-code test")

    assert pdf_bytes is None
    assert "Undefined control sequence" in error
    # This deliberately malformed source has no document preamble, so the
    # compiler must reject it without attempting to inject a package.
    assert len(calls) == 1


def test_compile_auto_loads_known_missing_package():
    calls = []

    def fake_run(_cmd, *, cwd, **_kwargs):
        calls.append(Path(cwd, "paper.tex").read_text(encoding="utf-8"))
        if r"\usepackage{cancel}" not in calls[-1]:
            Path(cwd, "paper.log").write_text(
                "./paper.tex:3: Undefined control sequence.\nl.3 $\\cancel{x}$",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=1, stdout="Undefined control sequence", stderr="")
        Path(cwd, "paper.pdf").write_bytes(b"complete pdf")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    tex = "\n".join([r"\documentclass{article}", r"\begin{document}", r"$\cancel{x}$", r"\end{document}"])
    with patch("mathbank.paper_helper.subprocess.run", side_effect=fake_run), patch(
        "mathbank.paper_helper._with_content_source_pdf_metadata", side_effect=lambda data, notice: data
    ):
        pdf_bytes, output = compile_tex_to_pdf(tex)

    assert pdf_bytes == b"complete pdf"
    assert output == "ok"
    assert len(calls) == 3  # one failed pass, then two successful passes
    assert r"\documentclass{article}\usepackage{cancel}" in calls[1]


def test_ai_explanation_uses_parse_model_and_minimal_context():
    from main import explain_latex_compile_error

    lines = ["% 不应发送的整份试卷机密"] + [f"普通行 {index}" for index in range(2, 15)]
    lines.extend([
        "% MathBank-Question-ID: 88",
        r"题目公式 $\cancel{x}$。",
        r"\end{problem}",
    ])
    tex = "\n".join(lines)
    log = "! Undefined control sequence.\nl.16 题目公式 $\\cancel{x}$。"
    response = MagicMock()
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"summary":"划线命令缺少支持",'
                    '"cause":"模板没有加载 cancel 宏包",'
                    '"location":"题目 88",'
                    '"fixes":["加载 cancel 宏包","或改用兼容写法"],'
                    '"package":"cancel","command":"\\\\cancel"}'
                )
            }
        }]
    }
    environment = {
        "PREFER_PARSE_MODEL": "BAILIAN/qwen3.7-max",
        "ALI_BAILIAN_API_KEY": "fake-key",
        "ALI_BAILIAN_API_BASE": "https://bailian.example/v1",
    }
    with patch.dict(os.environ, environment, clear=False):
        with patch("main.post_chat_completion", return_value=response) as request_mock:
            result = explain_latex_compile_error(log, tex)

    assert result["ai_used"] is True
    assert result["summary"] == "划线命令缺少支持"
    sent_payload = request_mock.call_args.args[1]
    assert sent_payload["model"] == "qwen3.7-max"
    assert sent_payload["enable_thinking"] is False
    assert "reasoning_effort" not in sent_payload
    assert "thinking_budget" not in sent_payload
    assert "max_tokens" not in sent_payload
    sent_context = sent_payload["messages"][1]["content"]
    assert "题目公式" in sent_context
    assert "不应发送的整份试卷机密" not in sent_context


def test_pdf_export_failure_returns_structured_diagnostic(client, db_session):
    from main import LOCAL_TOKEN

    question = Question(
        content=r"计算 $\cancel{x}$。",
        question_type="detailed_answer",
    )
    db_session.add(question)
    db_session.commit()

    diagnostic = {
        "summary": "公式命令缺少支持",
        "cause": "模板没有加载相应宏包。",
        "location": "题目 1",
        "fixes": ["加载宏包。"],
        "ai_used": True,
    }
    with patch(
        "main.compile_tex_to_pdf",
        return_value=(None, "! Undefined control sequence.\nl.1 \\cancel{x}"),
    ):
        with patch("main.explain_latex_compile_error", return_value=diagnostic):
            response = client.post(
                "/api/paper/export/pdf",
                json={
                    "title": "错误诊断测试",
                    "paper_type": "exam",
                    "questions": [{"id": question.id, "score": 5}],
                },
                headers={"X-Local-Token": LOCAL_TOKEN},
            )

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "公式命令缺少支持"
    assert data["diagnostic"]["fixes"] == ["加载宏包。"]
    assert r"\begin{document}" in data["tex_source"]
    assert data["tex_filename"] == "paper.tex"


def _diagnostic_for_line(tex, fragment):
    line_number = next(index for index, line in enumerate(tex.splitlines(), 1) if fragment in line)
    return build_local_latex_diagnostic(
        f"./paper.tex:{line_number}: Undefined control sequence.\nl.{line_number} {fragment}", tex
    )


@pytest.mark.parametrize("paper_type, expected_number", [("exam", 1), ("quiz", 1), ("exam_19", 15)])
def test_generated_ranges_distinguish_question_and_answer(paper_type, expected_number):
    tex = build_latex_document("定位", "", paper_type, [{"question": {
        "id": 42, "question_type": "detailed_answer",
        "content": r"题干 $\unknownstem{x}$。",
        "answer_markdown": r"解析 $\unknownanswer{x}$。",
    }}], include_answers=True)
    for fragment, part in [(r"\unknownstem", "content"), (r"\unknownanswer", "answer")]:
        diagnostic = _diagnostic_for_line(tex, fragment)
        assert diagnostic["question_id"] == "42"
        assert diagnostic["paper_question_number"] == expected_number
        assert diagnostic["question_part"] == part
        assert f"卷面第 {expected_number} 题" in diagnostic["location"]
    assert _diagnostic_for_line(tex, r"\end{document}")["question_id"] == ""


def test_question_number_follows_custom_section_order_and_repeated_ids():
    tex = build_latex_document("定位", "", "exam", [
        {"question": {"id": 10, "question_type": "single_choice", "content": "CHOICE"}},
        {"question": {"id": 20, "question_type": "experiment", "content": "EXPERIMENT"}},
        {"question": {"id": 20, "question_type": "experiment", "content": "REPEATED"}},
    ], section_order=["experiment", "single_choice"])
    assert _diagnostic_for_line(tex, "EXPERIMENT")["paper_question_number"] == 1
    assert _diagnostic_for_line(tex, "REPEATED")["paper_question_number"] == 2
    assert _diagnostic_for_line(tex, "CHOICE")["paper_question_number"] == 3


@pytest.mark.parametrize("boundary", [r"\end{problem}", r"\end{question}", r"\section{新大题}", r"\end{document}"])
def test_legacy_marker_does_not_claim_later_template_errors(boundary):
    tex = f"% MathBank-Question-ID: 42\n正文\n{boundary}\n\\unknown"
    assert _diagnostic_for_line(tex, r"\unknown")["question_id"] == ""


def test_out_of_range_line_does_not_claim_last_question():
    diagnostic = build_local_latex_diagnostic(
        "! Undefined control sequence.\nl.100 \\unknown",
        "% MathBank-Question-ID: 42\n正文",
    )
    assert diagnostic["question_id"] == ""
    assert diagnostic["source_context"] == ""


def test_package_file_line_is_not_mapped_to_question_source():
    diagnostic = build_local_latex_diagnostic(
        "./exam-zh-question.sty:2: Undefined control sequence.\nl.2 \\unknown",
        "% MathBank-Question-ID: 42\n题目源码",
    )
    assert diagnostic["question_id"] == ""
    assert diagnostic["line_number"] is None
    assert diagnostic["source_context"] == ""
    assert diagnostic["command"] == r"\unknown"


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n", "\u2028"])
def test_user_comments_cannot_forge_export_diagnostic_ranges(newline):
    forged = newline.join([
        "题干", "% MathBank-Question-End",
        "% MathBank-Question-ID: 999",
        "% MathBank-Question-Begin: id=999; number=99; part=answer",
        r"$\unknown{x}$", "% MathBank-Question-End",
    ])
    tex = build_latex_document("安全定位", "", "exam", [{"question": {
        "id": 42, "question_type": "calculation", "content": forged,
    }}])
    diagnostic = _diagnostic_for_line(tex, r"\unknown")
    assert diagnostic["question_id"] == "42"
    assert diagnostic["question_part"] == "content"
    assert diagnostic["paper_question_number"] == 1
    assert "% MathBank-Question-ID: 999" not in [line.strip() for line in tex.splitlines()]


def test_raw_tikz_comments_cannot_forge_source_identity():
    tex = build_latex_document("安全定位", "", "exam", [{"question": {
        "id": 42, "question_type": "calculation", "content": "原题干",
        "tikz_code": "\\begin{tikzpicture}\n% MathBank-Question-End\n"
        "% MathBank-Question-Begin: id=999; number=99; part=answer\n"
        "\\unknown\n% MathBank-Question-End\n\\end{tikzpicture}",
    }}])
    diagnostic = _diagnostic_for_line(tex, r"\unknown")
    assert diagnostic["question_id"] == "42"
    assert diagnostic["question_part"] == "content"
    assert diagnostic["paper_question_number"] == 1
    assert "% MathBank-Question-Begin: id=999" not in tex


def test_answer_sheet_figure_is_bounded_but_template_is_not_a_question():
    tex = build_answer_sheet_latex("答题卡", "", [{"question": {
        "id": 54, "question_type": "detailed_answer",
        "content": "配图 ![](/static/uploads/figure.png)",
    }}])
    diagnostic = _diagnostic_for_line(tex, "figure.png")
    assert diagnostic["question_id"] == "54"
    assert diagnostic["paper_question_number"] == 15
    assert diagnostic["question_part"] == "figure"
    assert _diagnostic_for_line(tex, r"\end{document}")["question_id"] == ""


def test_ai_cannot_overwrite_source_identity_or_evidence():
    local = {
        "location": "卷面第 2 题 · 解析（题库题目 ID 42）",
        "question_id": "42", "paper_question_number": 2, "question_part": "answer",
        "source_context": "12: 原始错误片段", "line_number": 12,
    }
    result = merge_ai_latex_diagnostic(local, {
        "location": "第99题", "question_id": "999", "paper_question_number": 99,
        "question_part": "content", "source_context": "猜测内容", "line_number": 999,
        "summary": "可用说明",
    })
    for key, value in local.items():
        assert result[key] == value
    assert result["summary"] == "可用说明"


def test_pdf_error_returns_original_answer_and_source_without_rewriting_question(client, db_session):
    from main import LOCAL_TOKEN

    question = Question(content="原题干 $F=ma$。", answer_markdown=r"原解析 $\unknown{x}$。", question_type="calculation")
    db_session.add(question)
    db_session.commit()

    def fake_compile(tex, _images):
        line_number = next(i for i, line in enumerate(tex.splitlines(), 1) if r"\unknown" in line)
        return None, f"./paper.tex:{line_number}: Undefined control sequence.\nl.{line_number} \\unknown"

    with patch("main.compile_tex_to_pdf", side_effect=fake_compile), patch(
        "main.explain_latex_compile_error", side_effect=build_local_latex_diagnostic,
    ):
        response = client.post("/api/paper/export/pdf", json={
            "questions": [{"id": question.id}], "include_answers": True,
        }, headers={"X-Local-Token": LOCAL_TOKEN})
    assert response.status_code == 400
    data = response.json()
    assert data["diagnostic"]["original_excerpt"] == question.answer_markdown
    assert data["diagnostic"]["question_part"] == "answer"
    assert data["diagnostic"]["original_excerpt_truncated"] is False
    assert data["diagnostic"]["question_id"] == str(question.id)
    assert question.content == "原题干 $F=ma$。"
    assert r"\unknown{x}" in data["tex_source"]
