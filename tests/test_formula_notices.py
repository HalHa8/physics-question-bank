"""Import review text is metadata, never part of the mathematical expression."""
from mathbank.formula_notices import separate_formula_notices
import hashlib


def test_notice_moves_out_of_formula_and_keeps_actual_expression():
    questions = [{"content": r"求 $x^2+\text{[公式待核对]}$，见原页。", "answer_markdown": "$[公式待复核]$"}]
    separate_formula_notices(questions)
    q = questions[0]
    assert q["content"] == "求 $x^2+$，见原页。"
    assert q["answer_markdown"] == ""
    assert len(q["source_review"]["formula_notices"]) == 2
    assert q["source_review"]["formula_notice_required"] is True


def test_structure_only_note_does_not_claim_formula_is_wrong():
    questions = [{"content": "$x^2+1$[公式结构待核对]"}]
    separate_formula_notices(questions)
    assert questions[0]["content"] == "$x^2+1$"
    assert questions[0]["source_review"]["formula_notice_required"] is False
    assert "required" not in questions[0]["source_review"]


def test_physics_import_keeps_missing_formula_marker_and_exact_source_evidence():
    text = r"$I=2.0\,mA$，[公式结构待核对]，取向右为正，$\vec v=-3\,m/s$。"
    questions = [{"content": text, "answer_markdown": r"$\text{?}$[公式结构待核对]"}]
    original_answer = questions[0]["answer_markdown"]
    separate_formula_notices(questions, preserve_missing=True)
    question = questions[0]
    assert question["content"] == text
    assert question["answer_markdown"] == original_answer
    review = question["source_review"]
    assert review["formula_notice_required"] is review["required"] is True
    assert review["formula_notices"][0]["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    start, end = review["formula_notices"][0]["source_range"]
    assert text[start:end] == "[公式结构待核对]"


def test_notice_between_separate_formulas_never_consumes_their_delimiters():
    for left, right in (("$x$", "$y$"), ("$$x$$", "$$y$$"), (r"\(x\)", r"\(y\)"), (r"\[x\]", r"\[y\]")):
        questions = [{"content": left + "[公式待核对]" + right}]
        separate_formula_notices(questions)
        assert questions[0]["content"] == left + right


def test_confirmed_formula_does_not_reintroduce_warning():
    questions = [{"content": "$x$[公式待核对]", "source_review": {"required": False, "verified_by": "vision"}}]
    separate_formula_notices(questions)
    assert questions[0]["source_review"]["required"] is False
    assert questions[0]["source_review"]["formula_notice_required"] is False


def test_removing_notice_preserves_control_word_token_boundary():
    for notice in ("[公式待核对]", r"\text{[公式待核对]}"):
        questions = [{"content": r"$\alpha" + notice + "x$"}]
        separate_formula_notices(questions)
        assert questions[0]["content"] == r"$\alpha x$"


def test_literals_images_comments_and_math_are_preserved():
    text = r'''`[公式待核对]` ![公式待核对](/static/uploads/a.png)
https://example.org/[公式待核对]
<!-- [公式待核对] -->
\begin{tikzpicture}[公式待核对]\end{tikzpicture}
$\frac{x+1}{2}$'''
    questions = [{"content": text}]
    separate_formula_notices(questions)
    assert questions == [{"content": text}]
