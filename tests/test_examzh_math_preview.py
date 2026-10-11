"""Exam-zh constants in shared previews, adapted from upstream 3252b72."""

from test_math_preview_regressions import run_preview_script


def test_examzh_constants_keep_upright_semantics_in_nested_formulas():
    run_preview_script(r'''
const options = {throwOnError: true, strict: 'error', trust: false};
const source = String.raw`\eu^{\iu\pi}+\upe^{\upi\pi}=\dfrac{\iu^2}{\eu}+i+e`;
const html = katex.renderToString(source, options);
assert(!html.includes('_fallback') && !html.includes('katex-error'));
assert(html.includes('<mi mathvariant="normal">i</mi>'));
assert(html.includes('<mi mathvariant="normal">e</mi>'));
assert(html.includes('<mi>i</mi>') && html.includes('<mi>e</mi>'));
assert(html.includes('mathnormal'));
for (const alias of [String.raw`\iu`, String.raw`\upi`]) {
    assert.equal(katex.renderToString(alias, options).split('katex-html')[1],
        katex.renderToString(String.raw`\mathrm{i}`, options).split('katex-html')[1]);
}
for (const alias of [String.raw`\eu`, String.raw`\upe`]) {
    assert.equal(katex.renderToString(alias, options).split('katex-html')[1],
        katex.renderToString(String.raw`\mathrm{e}`, options).split('katex-html')[1]);
}
for (const display of [false, true]) {
    katex.renderToString(source, {...options, displayMode: display});
}
''')


def test_examzh_constants_render_in_prose_choices_tables_and_display_math():
    run_preview_script(r'''
const sources = [
    String.raw`振动的复数表示 $z=2+3\iu$，相位因子 $\eu^{\iu\pi}$。`,
    String.raw`复数表示 z=2+3\upi；自然常数 \upe。`,
    String.raw`\begin{choices}\item $\iu$\item $\upi^2$\item $\eu$\item $\upe^{-1}$\end{choices}`,
    String.raw`\begin{tabular}{cc}$\iu$ & $\eu$ \\ $\upi$ & $\upe$\end{tabular}`,
    String.raw`\[\dfrac{\iu}{\eu}+\upi+\upe\]`,
];
for (const source of sources) {
    const formulas = parsedFormulas(preprocessFormulaForKaTeX(source));
    assert(formulas.length > 0, source);
    assert(formulas.join(' ').includes(String.raw`\iu`) || formulas.join(' ').includes(String.raw`\upi`));
}
const plain = '电流与电荷符号 $i+e$ 保持原样。';
assert.deepEqual(parsedFormulas(preprocessFormulaForKaTeX(plain)), ['i+e']);
''')


def test_examzh_constants_respect_command_boundaries_and_protected_literals():
    run_preview_script(r'''
for (const unknown of [String.raw`\iux`, String.raw`\upix`, String.raw`\eux`, String.raw`\upex`, String.raw`\du`]) {
    assert.throws(() => katex.renderToString(unknown, {throwOnError: true}), /Undefined control sequence/);
}
const protectedSource = '`$\\iu$ \\eu`\n\n'
    + String.raw`\begin{tikzpicture}\node {$\upi+\upe$};\end{tikzpicture}`
    + String.raw` ![常数](/static/uploads/iu_eu.png) [[MBM_iu_eu]] https://example.test/iu_eu`;
assert.equal(normalizeNakedMathForPreview(protectedSource), protectedSource);
const source = protectedSource + '\n\n' + String.raw`相位公式 $\eu^{\iu\pi}+1=0$。`;
assert.deepEqual(parsedFormulas(preprocessFormulaForKaTeX(source)), [String.raw`\eu^{\iu\pi}+1=0`]);
''')


def test_physics_decay_current_charge_units_vectors_and_circuit_literals_are_preserved():
    run_preview_script(r'''
const formulas = [
    String.raw`i(t)=I_0\eu^{-t/\tau}`,
    String.raw`e=1.60\times10^{-19}\,\mathrm{C}`,
    String.raw`\vec{F}=-2.00\,\mathrm{mN}\,\hat{x}`,
    String.raw`\tilde{I}=3.00\,\mathrm{mA}\,\eu^{\iu\omega t}`,
    String.raw`U=2.00\,\mathrm{kV},\ p=1.00\,\mathrm{MPa}`,
];
const circuit = String.raw`\begin{tikzpicture}\draw (0,0) to[R,l=$R$] (2,0) to[C,l=$C$] (2,-2);\end{tikzpicture}`;
const source = formulas.map(formula => '$' + formula + '$').join('\n\n') + '\n\n' + circuit;
assert.equal(normalizeNakedMathForPreview(circuit), circuit);
assert.deepEqual(parsedFormulas(preprocessFormulaForKaTeX(source)), formulas);
assert(preprocessFormulaForKaTeX(source).includes(circuit));
''')
