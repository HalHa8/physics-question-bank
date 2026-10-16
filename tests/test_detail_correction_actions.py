"""Executable detail shortcuts: no automatic solve/save, session-safe diagnostics."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def detail_action_script():
    api = (ROOT / "static/js/api.js").read_text(encoding="utf-8")
    editor = (ROOT / "static/js/editor.js").read_text(encoding="utf-8")
    sources = [
        api[api.index("const EditorState ="):api.index("// Global variables")],
        editor[editor.index("function backupEditorState"):editor.index("// Custom Premium Confirmation Modal")],
        editor[editor.index("function generateMissingEditorAnswer("):editor.index("function setupRealtimePreviews()")],
    ]
    setup = r"""
const assert = require('node:assert/strict');
const window = {};
let originalQuestionState = null;
const uploadedImages = [];
const TikzState = {contentAssets: [], answerAssets: []};
const FigureLayoutState = {align: 'right', size: 'auto', customAlign: false, imageLayouts: {}};
const initial = {
  editContent: String.raw`物体所受合力 $\unknownForce{F}$`, editAnswerMarkdown: '', editReview: '',
  editQType: 'calculation', editDifficulty: 'medium', editSource: '教师题目',
  editCompulsory: '', editChapter: '', editKnowledge: '', editRelatedQuestion: '', editTags: ''
};
class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {};
    this.dataset = {}; this.listeners = {}; this.value = ''; this.disabled = false;
    this.className = ''; this._text = ''; this.style = {};
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      remove: name => {this.className = this.className.split(/\s+/).filter(x => x !== name).join(' ');},
      add: name => {this.className += ' ' + name;}
    };
  }
  set textContent(value) { this._text = value; this.children = []; }
  get textContent() { return this._text + this.children.map(x => x.textContent).join(''); }
  set innerHTML(value) {
    assert.equal(value, '', 'untrusted diagnostic/action content must not use HTML injection');
    this._text = ''; this.children = [];
  }
  append(...children) { for (const child of children) {child.parent = this; this.children.push(child);} }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(x => x !== this); }
  getAttribute(name) { return this.attributes[name] || null; }
  setAttribute(name, value) { this.attributes[name] = value; }
  querySelectorAll(selector) {
    const all = this.children.flatMap(child => [child, ...child.querySelectorAll('*')]);
    return selector === '*' ? all : all.filter(child => selector.startsWith('.')
      ? child.classList.contains(selector.slice(1)) : child.tagName === selector.toUpperCase());
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  async click() { if (!this.disabled && this.listeners.click) await this.listeners.click(); }
  focus() { focused = this; }
  setSelectionRange(start, end) { this.selection = [start, end]; }
  scrollIntoView() { this.scrolled = true; }
}
const elements = Object.fromEntries(Object.keys(initial).map(id => [id, new Element('textarea')]));
for (const id of ['editorSection', 'aiSolveBtn', 'answerSourceTools']) elements[id] = new Element();
const document = {getElementById: id => elements[id] || null, createElement: tag => new Element(tag)};
let focused, requests = 0, blocked = false, opened = [], tabs = [], toasts = [], frames = [], copied = [];
let clipboardFailure = false;
const navigator = {clipboard: {async writeText(text) {if (clipboardFailure) throw new Error('denied'); copied.push(text);}}};
const requestAnimationFrame = handler => {frames.push(handler);};
function flushFrames() { const pending = frames; frames = []; pending.forEach(handler => handler()); }
function showToast(message, level) {toasts.push({message, level});}
function openQuestionEditorModal(panel) {
  if (blocked) return;
  opened.push(panel); elements.editorSection.classList.remove('hidden');
  requestAnimationFrame(() => {focused = 'modal heading';});
}
function switchWorkflowTab(tab) {tabs.push(tab);}
function switchContentTab(tab) {tabs.push(tab);}
function triggerAISolve() {requests++; elements.aiSolveBtn.disabled = true;}
function clean({draft = false} = {}) {
  for (const [key, value] of Object.entries(initial)) elements[key].value = value;
  if (draft) EditorState.useDraft({id: 'draft-12'});
  else EditorState.useQuestion({id: 71, seq_num: 6});
  backupEditorState(draft ? null : 71, draft ? 'draft-12' : null);
  elements.editorSection.className = 'hidden'; elements.aiSolveBtn.disabled = false;
  elements.answerSourceTools.open = false;
  requests = 0; blocked = false; opened = []; tabs = []; toasts = []; frames = []; copied = []; focused = null;
  clipboardFailure = false;
}
function errorNode(fragment = String.raw`\unknownForce{F}`, message = 'KaTeX parse error: undefined command') {
  const node = new Element(); node.className = 'katex-error'; node.textContent = fragment;
  node.setAttribute('title', message); return node;
}
"""
    checks = r"""
const scenarios = {
  async explicit_solve_keeps_draft() {
    for (const draft of [false, true]) {
      clean({draft});
      const before = structuredClone(originalQuestionState);
      elements.editReview.value = '未保存的教师备注';
      const host = new Element();
      renderMissingEditorAnswer(host);
      assert.equal(requests, 0, 'rendering an empty answer must never call AI');
      assert.ok(host.textContent.includes('可能产生费用'));
      assert.ok(host.textContent.includes('单位'));
      await host.querySelector('button').click();
      assert.equal(requests, 1);
      assert.deepEqual(opened, ['answer']);
      assert.deepEqual(tabs, ['ai']);
      assert.equal(elements.answerSourceTools.open, true);
      assert.equal(elements.editAnswerMarkdown.value, '');
      assert.equal(elements.editReview.value, '未保存的教师备注');
      assert.deepEqual(originalQuestionState, before, 'shortcut must not save or reset dirty baseline');
      assert.equal(isEditorModified(), true);
      assert.equal(EditorState.draftId, draft ? 'draft-12' : null);
      await host.querySelector('button').click();
      assert.equal(requests, 1, 'second click must not restart paid solve');
    }
  },
  async guarded_shortcut() {
    for (const reason of ['changed_question', 'changed_draft', 'answer_added', 'no_content', 'blocked_modal']) {
      clean();
      const host = new Element(); renderMissingEditorAnswer(host);
      if (reason === 'changed_question') EditorState.useQuestion({id: 72});
      if (reason === 'changed_draft') EditorState.useDraft({id: 'draft-other'});
      if (reason === 'answer_added') elements.editAnswerMarkdown.value = '教师已写好的解析';
      if (reason === 'no_content') elements.editContent.value = '';
      if (reason === 'blocked_modal') blocked = true;
      const before = structuredClone(originalQuestionState);
      await host.querySelector('button').click();
      assert.equal(requests, 0, reason);
      assert.deepEqual(originalQuestionState, before);
      if (reason === 'answer_added') assert.equal(elements.editAnswerMarkdown.value, '教师已写好的解析');
    }
    for (const missing of ['editContent', 'editAnswerMarkdown', 'aiSolveBtn', 'editorSection']) {
      clean();
      const absent = elements[missing]; delete elements[missing];
      // The production modal helper also declines to open without its host.
      if (missing === 'editorSection') blocked = true;
      generateMissingEditorAnswer(EditorState.snapshot());
      assert.equal(requests, 0, `missing ${missing} must not start a request`);
      elements[missing] = absent;
    }
    renderMissingEditorAnswer(null);
  },
  async diagnostics_are_local_and_safe() {
    clean();
    const host = new Element();
    const fragment = '<img src=x onerror=alert(1)>';
    host.append(errorNode(fragment, '<script>bad</script>'));
    const before = structuredClone(originalQuestionState);
    renderEditorFormulaDiagnostics(host, 'editContent');
    const details = host.querySelector('details');
    assert.ok(details.textContent.includes('题目 #6 · 题干有 1 处'));
    assert.ok(details.textContent.includes(fragment));
    assert.equal(details.querySelectorAll('img').length, 0);
    assert.equal(details.querySelectorAll('script').length, 0);
    assert.ok(details.textContent.includes('不等同于 PDF'));
    assert.equal(requests, 0);
    await details.querySelectorAll('button').at(-1).click();
    assert.ok(copied[0].includes('题目 #6'));
    assert.ok(copied[0].includes(fragment));
    assert.ok(copied[0].includes('<script>bad</script>'));
    assert.deepEqual(originalQuestionState, before);
    assert.equal(isEditorModified(), false);
    renderEditorFormulaDiagnostics(host, 'editContent');
    assert.equal(host.querySelectorAll('details').length, 1, 're-render must replace diagnostics');
    host.querySelector('.katex-error').remove();
    renderEditorFormulaDiagnostics(host, 'editContent');
    assert.equal(host.querySelectorAll('details').length, 0, 'fixed formulas must clear the issue');
  },
  async locate_source_and_reject_stale() {
    for (const target of ['editContent', 'editAnswerMarkdown']) {
      for (const stale of ['none', 'typed', 'switched', 'switched_during_focus']) {
        clean(); elements[target].value = initial.editContent;
        const fragment = String.raw`\unknownForce{F}`;
        const source = elements[target].value;
        const host = new Element(); host.append(errorNode(fragment));
        renderEditorFormulaDiagnostics(host, target);
        if (stale === 'typed') elements[target].value += '教师修正';
        if (stale === 'switched') EditorState.useQuestion({id: 72});
        await host.querySelector('button').click();
        if (stale === 'switched_during_focus') EditorState.useQuestion({id: 72});
        flushFrames();
        if (stale === 'none') {
          assert.equal(focused, elements[target]);
          assert.deepEqual(elements[target].selection, [source.indexOf(fragment), source.indexOf(fragment) + fragment.length]);
          assert.equal(elements[target].value, source);
          assert.equal(opened[0], target === 'editContent' ? 'content' : 'answer');
        } else assert.notEqual(focused, elements[target], 'stale diagnostics must not select a different source');
      }
    }
  },
  async bounded_and_clipboard_failure() {
    clean({draft: true});
    const host = new Element();
    for (let i = 0; i < 12; i++) host.append(errorNode(`bad ${i}`));
    renderEditorFormulaDiagnostics(host, 'editAnswerMarkdown');
    const details = host.querySelector('details');
    assert.ok(details.textContent.includes('当前草稿 · 解析有 12 处'));
    assert.equal(details.querySelectorAll('pre').length, 10);
    await details.querySelectorAll('button').at(-1).click();
    assert.ok(copied[0].includes('12. 片段：bad 11'));
    clipboardFailure = true;
    await details.querySelectorAll('button').at(-1).click();
    assert.equal(details.open, true);
    assert.ok(toasts.at(-1).message.includes('手动复制'));
  }
};
"""
    return setup + "\n".join(sources) + checks


@pytest.mark.parametrize("scenario", [
    "explicit_solve_keeps_draft", "guarded_shortcut", "diagnostics_are_local_and_safe",
    "locate_source_and_reject_stale", "bounded_and_clipboard_failure",
])
def test_detail_correction_actions_execute(detail_action_script, scenario):
    node = shutil.which("node")
    assert node, "Node.js is required for executable frontend regression"
    run = f"scenarios[{json.dumps(scenario)}]().catch(error => {{ console.error(error); process.exitCode = 1; }});"
    result = subprocess.run([node, "-"], input=detail_action_script + run,
                            text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_formula_diagnostics_recheck_real_bundled_katex_output():
    """Build DOM query adapters from real KaTeX output, not fabricated errors."""
    from test_math_preview_regressions import run_preview_script

    source = (ROOT / "static/js/editor.js").read_text(encoding="utf-8")
    collector = source[source.index("function collectEditorFormulaErrors("):
                       source.index("function locateEditorFormulaIssue(")]
    run_preview_script(collector + r"""
function decodeEntities(value) {
    return value.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, entity => ({
        '&amp;':'&', '&lt;':'<', '&gt;':'>', '&quot;':'"', '&#x27;':"'", '&#39;':"'"
    })[entity]);
}
function realRenderedHost(source, {displayMode = false} = {}) {
    const html = katex.renderToString(source, {throwOnError: false, trust: false, displayMode});
    const annotationMatch = html.match(/<annotation encoding="application\/x-tex">([\s\S]*?)<\/annotation>/);
    const colors = [...html.matchAll(/<mstyle\b[^>]*mathcolor="([^"]+)"/g)].map(match => ({
        getAttribute: name => name === 'mathcolor' ? match[1] : null
    }));
    const errorMatch = html.match(/<span class="katex-error" title="([^"]*)"[^>]*>([\s\S]*?)<\/span>/);
    const actualErrors = errorMatch ? [{
        textContent: decodeEntities(errorMatch[2]),
        getAttribute: name => name === 'title' ? decodeEntities(errorMatch[1]) : null
    }] : [];
    const formula = {
        querySelectorAll: selector => {assert.equal(selector, 'mstyle[mathcolor]'); return colors;},
        querySelector: selector => {
            assert.equal(selector, 'annotation[encoding="application/x-tex"]');
            return annotationMatch ? {textContent: decodeEntities(annotationMatch[1])} : null;
        },
        closest: selector => {assert.equal(selector, '.katex-display'); return displayMode ? {} : null;}
    };
    return {html, actualErrors, querySelectorAll: selector => selector === '.katex-error'
        ? actualErrors : annotationMatch ? [formula] : []};
}
const badSource = String.raw`\notARealPhysicsCommand{v}`;
const bad = realRenderedHost(badSource);
assert.equal(bad.actualErrors.length, 0, 'this regression must exercise the non-katex-error path');
assert.ok(bad.html.includes('<mstyle mathcolor="#cc0000">'));
const issues = collectEditorFormulaErrors(bad);
assert.equal(issues.length, 1);
assert.equal(issues[0].fragment, badSource, 'annotation must preserve the source for editing');
assert.ok(issues[0].message.includes('Undefined control sequence'));

// Legitimate author-specified error-colored notation must pass strict recheck,
// including the same custom symbols registered for normal PhysicsBank preview.
for (const source of [String.raw`\color{red}{v}`, String.raw`\color{#cc0000}{v}`,
    String.raw`\color{#cc0000}{\celsius}`, String.raw`\color{#cc0000}{\wideparen{AB}}`,
    String.raw`\color{#cc0000}{\parallelogram ABCD}`, String.raw`F=ma`]) {
    assert.deepEqual(collectEditorFormulaErrors(realRenderedHost(source, {displayMode:true})), [], source);
}
const originalRender = katex.renderToString;
let recheckOptions;
katex.renderToString = (source, options) => {recheckOptions = options; return originalRender(source, options);};
collectEditorFormulaErrors(bad);
katex.renderToString = originalRender;
assert.equal(recheckOptions.throwOnError, true);
assert.equal(recheckOptions.trust, false);

const structural = realRenderedHost(String.raw`\frac{1}{`);
assert.equal(structural.actualErrors.length, 1);
assert.equal(collectEditorFormulaErrors(structural).length, 1);
// Both exposure paths for an identical fragment must remain one diagnostic.
bad.actualErrors.push({textContent: badSource, getAttribute: () => issues[0].message});
assert.equal(collectEditorFormulaErrors(bad).length, 1);
""")
