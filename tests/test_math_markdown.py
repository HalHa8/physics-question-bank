import os
import shutil
import subprocess

import pytest

from mathbank.math_markdown import normalize_question_math_markdown


def test_wraps_vector_equations_without_guessing_vector_typography():
    source = (
        r"已知平面向量 \mathbf{a}, \mathbf{b} 不共线，"
        r"且 2\mathbf{a} + y\mathbf{b} = x\mathbf{a} - 3\mathbf{b}，则（ ）"
    )

    normalized = normalize_question_math_markdown(source)

    assert r"$\mathbf{a}, \mathbf{b}$ 不共线" in normalized
    assert (
        r"$2\mathbf{a} + y\mathbf{b} = "
        r"x\mathbf{a} - 3\mathbf{b}$"
    ) in normalized
    assert r"\boldsymbol" not in normalized


def test_wraps_subscripts_superscripts_relations_sets_and_geometry():
    source = (
        r"当 x \geqslant 0 时，且当 x < 0 时经过点 (4,8)，f(x_1) \leqslant f(x_2)，"
        r"且 x_1x_2 \neq 0，D(x_2) \subseteq D(x_1)；"
        r"f(x) 在区间 (0, +\infty) 单调递增．"
        r"C: \frac{x^2}{a^2} + \frac{y^2}{b^2} = 1 (a > b > 0)，"
        r"\triangle PQR 的面积"
    )

    normalized = normalize_question_math_markdown(source)

    for expected in (
        r"$x \geqslant 0$",
        r"$x < 0$",
        r"$(4,8)$",
        r"$f(x_1) \leqslant f(x_2)$",
        r"$x_1x_2 \neq 0$",
        r"$D(x_2) \subseteq D(x_1)$",
        r"$f(x)$",
        r"$(0, +\infty)$",
        r"$C: \frac{x^2}{a^2} + \frac{y^2}{b^2} = 1 (a > b > 0)$",
        r"$\triangle PQR$",
    ):
        assert expected in normalized

    assert normalize_question_math_markdown("经过点 (4,8)，且 x < 0 时") == (
        "经过点 $(4,8)$，且 $x < 0$ 时"
    )


def test_preserves_existing_math_images_locks_and_structural_commands():
    source = (
        "已有 $x_1+y^2$。\n"
        "\\begin{choices}\n"
        "\\item x = 1\n"
        "\\item \\frac{1}{2}\n"
        "\\end{choices}\n"
        "[[MBM_SCOPE_0001]] ![图](/static/uploads/a_1.png) \\fillin"
    )

    normalized = normalize_question_math_markdown(source)

    assert "$x_1+y^2$" in normalized
    assert "$$x_1+y^2$$" not in normalized
    assert "\\begin{choices}" in normalized
    assert "\\item $x = 1$" in normalized
    assert "\\item $\\frac{1}{2}$" in normalized
    assert "\\end{choices}" in normalized
    assert "[[MBM_SCOPE_0001]]" in normalized
    assert "![图](/static/uploads/a_1.png)" in normalized
    assert "\\fillin" in normalized


def test_protects_multiline_math_complete_environments_tables_and_text_macros():
    multiline_math = "$x^2 +\ny^2 = 1$"
    cases = "\\begin{cases} x=1 \\\\ y=2 \\end{cases}"
    table = "\\begin{tabular}{cc} x_1 & y_1 \\\\ x_2 & y_2 \\end{tabular}"
    source = f"已有 {multiline_math}。\n{cases}\n{table}\n题干 \\paren"

    normalized = normalize_question_math_markdown(source)

    assert multiline_math in normalized
    assert f"${cases}$" in normalized
    assert "$\\begin{cases} $" not in normalized
    assert table in normalized
    assert "$\\begin{tabular}" not in normalized
    assert "题干 \\paren" in normalized
    assert "$\\paren$" not in normalized


def test_preserves_illustration_protocol_marker_until_ocr_cleanup():
    source = "已知三角形 ABC\n[ILLUSTRATION_BOX: 10, 20, 90, 80]"

    normalized = normalize_question_math_markdown(source)

    assert normalized.endswith("[ILLUSTRATION_BOX: 10, 20, 90, 80]")
    assert "$[ILLUSTRATION_BOX" not in normalized


@pytest.mark.parametrize("environment", [
    "equation", "equation*", "align", "align*", "alignat", "alignat*",
    "gather", "gather*", "multline", "multline*", "displaymath", "math",
])
def test_standalone_math_remains_valid_export_source(environment):
    body = r"{1} x &= 1" if environment.startswith("alignat") else "x=1"
    source = rf"\begin{{{environment}}}{body}\end{{{environment}}}"

    assert normalize_question_math_markdown(source) == source
    assert normalize_question_math_markdown(normalize_question_math_markdown(source)) == source


def test_balanced_nested_environments_are_not_split_at_the_first_end():
    cases = (
        r"\begin{cases} x & x>0 \\ "
        r"\begin{cases} y & y>0 \\ 0 & y=0 \end{cases} & x<0 \end{cases}"
    )
    equation = r"\begin{equation} f(x)=" + cases + r"\end{equation}"
    table = r"\begin{tabular}{c} \begin{tabular}{c}$x_1$\end{tabular}\end{tabular}"

    assert normalize_question_math_markdown(cases) == "$" + cases + "$"
    assert normalize_question_math_markdown(equation) == equation
    assert normalize_question_math_markdown(table) == table


def test_escaped_dollars_do_not_change_the_neighboring_math_boundaries():
    source = r"价格 \$5，原式 $x+\text{\$5}$，另有 y_1=2。"

    assert normalize_question_math_markdown(source) == (
        r"价格 \$5，原式 $x+\text{\$5}$，另有 $y_1=2$。"
    )
    assert normalize_question_math_markdown(r"已有 $a$$b$$c$。") == r"已有 $a$$b$$c$。"


@pytest.mark.skipif(
    os.environ.get("MATHBANK_TEST_MATH_NATIVE") != "1" or not shutil.which("xelatex"),
    reason="Set MATHBANK_TEST_MATH_NATIVE=1 with XeLaTeX installed",
)
def test_normalized_standalone_environments_compile_after_export_cleanup(tmp_path):
    from mathbank.paper_helper import clean_content_for_latex

    sources = [
        r"\begin{equation}x=1\end{equation}",
        r"\begin{equation*}f(x)=\begin{cases}x&x>0\\-x&x\leq0\end{cases}\end{equation*}",
        r"\begin{align}x&=1\\y&=2\end{align}",
        r"\begin{align*}x&=1\\y&=2\end{align*}",
        r"\begin{alignat}{1}x&=1\\y&=2\end{alignat}",
        r"\begin{gather}x=1\\y=2\end{gather}",
        r"\begin{gather*}x=1\\y=2\end{gather*}",
        r"\begin{multline}x+y+z\\=1\end{multline}",
        r"\begin{multline*}x+y+z\\=1\end{multline*}",
    ]
    exported = [clean_content_for_latex(normalize_question_math_markdown(source)) for source in sources]
    tex_path = tmp_path / "normalized-environments.tex"
    tex_path.write_text(
        "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n"
        + "\n\n".join(exported) + "\n\\end{document}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("xelatex"), "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr
    assert tex_path.with_suffix(".pdf").is_file()


def test_does_not_wrap_plain_chinese_or_ordinary_english_words():
    source = (
        "这是一段普通中文，MathBank keeps prose readable。\n"
        "\\begin{tabular}{cc}\\toprule 名称 & 数值 \\\\ \\bottomrule\\end{tabular}"
    )

    assert normalize_question_math_markdown(source) == source


def test_parse_paper_postprocesses_future_imports_without_touching_database():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from main import parse_paper_text_internal

    provider = SimpleNamespace(
        api_key="test-key",
        api_base="https://example.invalid/v1/",
        model_name="test-model",
        provider_label="test provider",
        credential_label="TEST_API_KEY",
        provider_code="test",
        reasoning_effort=None,
    )
    response = MagicMock()
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": r'''{
                    "questions": [{
                        "content": "已知向量 \\mathbf{a}，当 x_1^2 \\geqslant 0 时",
                        "answer_markdown": "[EXTRACTED_ORIGINAL]由 y^2 = x_1 得"
                    }]
                }'''
            }
        }]
    }

    with patch("main.resolve_text_provider", return_value=provider), patch(
        "main.post_chat_completion", return_value=response
    ), patch("main.get_current_curriculum", return_value={}):
        questions = parse_paper_text_internal("原始试卷文本", True)

    assert questions[0]["content"] == (
        r"已知向量 $\mathbf{a}$，当 $x_1^2 \geqslant 0$ 时"
    )
    assert questions[0]["answer_markdown"] == r"由 $y^2 = x_1$ 得"
