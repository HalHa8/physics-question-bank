"""Execute the complete preview preprocessing path and the bundled KaTeX parser."""

import json
from pathlib import Path
import shutil
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_preview_script(assertions):
    source = (PROJECT_ROOT / "static/js/editor.js").read_text(encoding="utf-8")
    start = source.index("function transformFillinMacro(clean)")
    marker = "window.preprocessFormulaForKaTeX = preprocessFormulaForKaTeX;"
    end = source.index(marker, start) + len(marker)
    katex_path = str(PROJECT_ROOT / "static/lib/katex/katex.min.js")
    script = (
        "global.window = {MathBankSafe: {safeImageUrl(v) { return v; }, escapeAttribute(v) { return v; }}};\n"
        + "const katex = require(" + json.dumps(katex_path) + ");\n"
        + source[start:end]
        + r'''
const assert = require('node:assert/strict');
function parsedFormulas(html) {
    const formulas = [];
    assert(!html.includes('MATH_PLACEHOLDER'), `placeholder leaked: ${html}`);
    replaceDelimitedMathForPreview(html, (whole, inner, opening) => {
        const formula = inner.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
        const rendered = katex.renderToString(formula, {
            throwOnError: true, displayMode: opening === '$$' || opening === '\[',
        });
        assert(rendered.includes('katex'), `KaTeX did not render ${formula}`);
        formulas.push(formula);
        return whole;
    });
    return formulas;
}
'''
        + assertions
    )
    node = shutil.which("node")
    assert node, "Node.js is required for executable preview regressions"
    result = subprocess.run(
        [node, "-"], input=script, cwd=PROJECT_ROOT, text=True,
        capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_tables_keep_existing_formulas_and_repair_only_naked_cell_math():
    run_preview_script(r'''
const proper = String.raw`\begin{tabular}{cc} $x_1$ & $y_1$ \\ $x_2$ & $y_2$ \end{tabular}`;
const html = preprocessFormulaForKaTeX(proper);
assert.equal((html.match(/<td\b/g) || []).length, 4);
assert.deepEqual(parsedFormulas(html), ['x_1', 'y_1', 'x_2', 'y_2']);

const mixed = String.raw`\begin{tabular}{cc} $\frac{1}{2}$ & y_1 \\ \multicolumn{2}{c}{$x<1$} \\ \multirow{2}{*}{$z^2$} & $a$ \\ & b_1 \end{tabular}`;
const mixedHtml = preprocessFormulaForKaTeX(mixed);
assert(mixedHtml.includes('colspan="2"'));
assert(mixedHtml.includes('rowspan="2"'));
assert.deepEqual(parsedFormulas(mixedHtml), [String.raw`\frac{1}{2}`, 'y_1', String.raw`x\lt 1`, 'z^2', 'a', 'b_1']);
''')


def test_standalone_math_uses_katex_compatible_display_environments():
    run_preview_script(r'''
const environments = [
    ['equation', 'x=1'], ['equation*', 'x=1'],
    ['align', String.raw`x&=1\\y&=2`], ['align*', String.raw`x&=1\\y&=2`],
    ['alignat', String.raw`{1}x&=1\\y&=2`], ['alignat*', String.raw`{1}x&=1\\y&=2`],
    ['gather', String.raw`x=1\\y=2`], ['gather*', String.raw`x=1\\y=2`],
    ['multline', String.raw`x+y+z\\=1`], ['multline*', String.raw`x+y+z\\=1`],
];
for (const [environment, body] of environments) {
    const source = '\\begin{' + environment + '}' + body + '\\end{' + environment + '}';
    const html = preprocessFormulaForKaTeX(source);
    assert(html.startsWith('$$') && html.endsWith('$$'), `not display math: ${html}`);
    assert.equal(parsedFormulas(html).length, 1);
    const normalized = normalizeNakedMathForPreview(source);
    assert.equal(normalizeNakedMathForPreview(normalized), normalized, `not idempotent: ${environment}`);
}
''')


def test_nested_math_existing_delimiters_typography_and_image_layouts_remain_intact():
    run_preview_script(r'''
const nested = String.raw`\begin{cases} x & x>0 \\ \begin{cases} y & y>0 \\ 0 & y=0 \end{cases} & x<0 \end{cases}`;
for (const source of [nested, '\\begin{equation}f(x)=' + nested + '\\end{equation}']) {
    assert.equal(parsedFormulas(preprocessFormulaForKaTeX(source)).length, 1);
}
const multiline = '$x^2+\ny^2=1$';
assert.equal(preprocessFormulaForKaTeX(multiline), multiline);
assert.equal(parsedFormulas(preprocessFormulaForKaTeX(multiline)).length, 1);
const upright = String.raw`已知向量 $\mathbf{a}$。`;
assert.equal(preprocessFormulaForKaTeX(upright), upright);
assert.equal(parsedFormulas(preprocessFormulaForKaTeX(upright)).length, 1);
const escaped = String.raw`价格 \$5，公式 $x+\text{\$5}$，以及 $y_1$。`;
assert.equal(preprocessFormulaForKaTeX(escaped), escaped);
assert.deepEqual(parsedFormulas(preprocessFormulaForKaTeX(escaped)), [String.raw`x+\text{\$5}`, 'y_1']);
assert.equal(parsedFormulas(preprocessFormulaForKaTeX('$a$$b$$c$')).length, 3);
assert(preprocessFormulaForKaTeX(String.raw`题干 \paren`).includes('exam-zh-paren-preview'));
const image = preprocessFormulaForKaTeX('图 ![](/static/uploads/figure.png)', {
    '/static/uploads/figure.png': {align: 'right', size: 'large'},
});
assert(image.includes('mb-inline-image-align-right'));
assert(image.includes('mb-inline-image-size-large'));
''')
