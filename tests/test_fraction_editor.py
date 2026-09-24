"""Execute the shipped formatting action against real editor session/dirty state."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fraction_editor_script():
    api = (ROOT / "static/js/api.js").read_text(encoding="utf-8")
    editor = (ROOT / "static/js/editor.js").read_text(encoding="utf-8")
    action_end = "window.normalizeEditorFractions = normalizeEditorFractions;"
    sources = [
        api[api.index("const EditorState ="):api.index("// Global variables")],
        editor[
            editor.index("async function normalizeEditorFractions("):
            editor.index(action_end) + len(action_end)
        ],
        editor[
            editor.index("function backupEditorState"):
            editor.index("// Custom Premium Confirmation Modal")
        ],
    ]
    setup = r"""
const assert = require('node:assert/strict');
const window = {};
let originalQuestionState = null;
const uploadedImages = [];
const TikzState = {contentAssets: [], answerAssets: []};
const FigureLayoutState = {align: 'right', size: 'auto', customAlign: false, imageLayouts: {}};
const source = String.raw`求 $\frac{x+1}{x-1}$`;
const formatted = String.raw`求 $\dfrac{x+1}{x-1}$`;
const initial = {
  editContent: source, editAnswerMarkdown: source, editReview: '',
  editQType: 'single_choice', editDifficulty: 'medium', editSource: '',
  editCompulsory: '', editChapter: '', editKnowledge: '',
  editRelatedQuestion: '', editTags: ''
};
class Input extends EventTarget {
  constructor(value) {
    super();
    this.value = value;
    this.events = [];
    this.addEventListener('input', event => {
      this.events.push({value: this.value, bubbles: event.bubbles});
    });
  }
}
const elements = Object.fromEntries(Object.entries(initial).map(([id, value]) => [id, new Input(value)]));
const document = {getElementById: id => elements[id] || null};
const toasts = [];
const showToast = (message, level) => toasts.push({message, level});
let feedbackCount = 0;
const refreshEditorFeedback = () => { feedbackCount += 1; };
const requests = [];
const fetch = (url, options) => new Promise((resolve, reject) => {
  requests.push({url, options, resolve, reject});
});
const response = (text = formatted, ok = true) => ({ok, json: async () => ({text})});
function makeButton() {
  return {
    disabled: false,
    attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; }
  };
}
function clean(id = 17) {
  EditorState.useQuestion({id});
  for (const [key, value] of Object.entries(initial)) {
    elements[key].value = value;
    elements[key].events.length = 0;
  }
  backupEditorState(id);
  feedbackCount = 0;
  toasts.length = 0;
}
function type(target, value) {
  elements[target].value = value;
  elements[target].dispatchEvent(new Event('input', {bubbles: true}));
}
function assertReleased(button) {
  assert.equal(button.disabled, false, 'button must be usable after completion');
  assert.equal(button.attributes['aria-busy'], undefined);
}
"""
    checks = r"""
const scenarios = {
  async success() {
    for (const target of ['editContent', 'editAnswerMarkdown']) {
      clean();
      assert.equal(isEditorModified(), false);
      const baseline = structuredClone(originalQuestionState);
      const button = makeButton();
      const pending = normalizeEditorFractions(target, button);
      assert.equal(button.disabled, true);
      assert.equal(button.attributes['aria-busy'], 'true');
      const request = requests.at(-1);
      assert.equal(request.url, '/api/format/fractions');
      assert.equal(request.options.method, 'POST');
      assert.equal(request.options.body.get('text'), source);
      request.resolve(response());
      await pending;
      assert.equal(elements[target].value, formatted);
      assert.deepEqual(elements[target].events, [{value: formatted, bubbles: true}]);
      const other = target === 'editContent' ? 'editAnswerMarkdown' : 'editContent';
      assert.equal(elements[other].value, source);
      assert.deepEqual(originalQuestionState, baseline, 'formatting is not a save');
      assert.equal(isEditorModified(), true, 'formatted text must remain unsaved');
      assert.ok(feedbackCount > 0);
      assertReleased(button);
    }
  },
  async typing() {
    for (const restoreOriginal of [false, true]) {
      clean();
      const baseline = structuredClone(originalQuestionState);
      const button = makeButton();
      const pending = normalizeEditorFractions('editContent', button);
      type('editContent', source + ' + new input');
      if (restoreOriginal) type('editContent', source);
      const current = elements.editContent.value;
      const events = [...elements.editContent.events];
      requests.at(-1).resolve(response());
      await pending;
      assert.equal(elements.editContent.value, current, 'later input must win, even after undo');
      assert.deepEqual(elements.editContent.events, events, 'stale result must emit no input event');
      assert.deepEqual(originalQuestionState, baseline);
      assert.equal(isEditorModified(), !restoreOriginal);
      assertReleased(button);
    }
  },
  async question_switch() {
    for (const returnToOriginal of [false, true]) {
      clean();
      const button = makeButton();
      const pending = normalizeEditorFractions('editContent', button);
      clean(23);
      if (returnToOriginal) clean(17);
      const baseline = structuredClone(originalQuestionState);
      requests.at(-1).resolve(response());
      await pending;
      assert.equal(elements.editContent.value, source, 'old session response must be ignored');
      assert.equal(elements.editContent.events.length, 0);
      assert.deepEqual(originalQuestionState, baseline);
      assert.equal(isEditorModified(), false);
      assertReleased(button);
    }
  },
  async failure() {
    for (const failure of ['http', 'network', 'invalid_result']) {
      clean();
      type('editReview', 'unsaved teacher note');
      const baseline = structuredClone(originalQuestionState);
      const button = makeButton();
      const pending = normalizeEditorFractions('editAnswerMarkdown', button);
      const request = requests.at(-1);
      if (failure === 'network') request.reject(new Error('offline'));
      else request.resolve(response(failure === 'invalid_result' ? null : formatted, failure !== 'http'));
      await pending;
      assert.equal(elements.editAnswerMarkdown.value, source);
      assert.equal(elements.editAnswerMarkdown.events.length, 0);
      assert.equal(elements.editReview.value, 'unsaved teacher note');
      assert.deepEqual(originalQuestionState, baseline);
      assert.equal(isEditorModified(), true);
      assert.equal(toasts.at(-1).level, 'error');
      assertReleased(button);
      const retry = normalizeEditorFractions('editAnswerMarkdown', button);
      requests.at(-1).resolve(response());
      await retry;
      assert.equal(elements.editAnswerMarkdown.value, formatted, 'failure must permit retry');
      assert.equal(elements.editReview.value, 'unsaved teacher note');
      assert.deepEqual(originalQuestionState, baseline);
      assertReleased(button);
    }
  },
  async duplicate_click() {
    clean();
    const button = makeButton();
    const before = requests.length;
    const first = normalizeEditorFractions('editContent', button);
    const second = normalizeEditorFractions('editContent', button);
    assert.equal(requests.length, before + 1, 'double click must send only one request');
    requests.at(-1).resolve(response());
    await Promise.all([first, second]);
    assert.equal(elements.editContent.value, formatted);
    assert.equal(elements.editContent.events.length, 1);
    assertReleased(button);
  }
};
"""
    return setup + "\n".join(sources) + checks


@pytest.mark.parametrize(
    "scenario", ["success", "typing", "question_switch", "failure", "duplicate_click"]
)
def test_fraction_editor_handles_async_results(fraction_editor_script, scenario):
    node = shutil.which("node")
    assert node, "Node.js is required for executable frontend regression"
    run = (
        "let completed = false;"
        f"scenarios[{json.dumps(scenario)}]().then(() => {{ completed = true; }}).catch(error => {{"
        "console.error(error); process.exitCode = 1;});"
        "process.on('beforeExit', () => { if (!completed) {"
        "console.error('Scenario did not finish'); process.exitCode = 1; }});"
    )
    result = subprocess.run(
        [node, "-"],
        input=fraction_editor_script + run,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
