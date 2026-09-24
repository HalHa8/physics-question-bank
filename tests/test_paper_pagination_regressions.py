"""Executable regressions for page sizing, callback ownership and drag targets.

Real-browser coverage is still needed for geometry, caret/IME and native drag.
These tests exercise the shipped JavaScript without adding a build dependency.
"""

from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "static/js/paper.js").read_text(encoding="utf-8")


def _section(start, end):
    start_index = SOURCE.index(start)
    return SOURCE[start_index:SOURCE.index(end, start_index)]


def _node(script):
    node = shutil.which("node")
    assert node, "Node.js is required for executable frontend regression tests"
    result = subprocess.run(
        [node, "-"], input=script, text=True, capture_output=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr


def test_expanded_page_and_scroll_do_not_inflate_a4_capacity():
    helpers = _section("function getPaperBlockOuterHeight(", "function createMeasuredA4Page(")
    helpers += _section("function getA4PageHeightLimits(", "function rebalanceA4PaperPages(")
    _node(helpers + r"""
const assert = require('node:assert/strict');
global.window = { getComputedStyle: element => element.style };
let pageTop = 100, contentTop = 450, footerTop = 1186, expanded = false;
const notice = {
  style: {marginTop: '0px', marginBottom: '10px'},
  getBoundingClientRect: () => ({height: 30})
};
const page = {
  style: {minHeight: '1123px', paddingTop: '48px', borderTopWidth: '1px', borderBottomWidth: '1px'},
  getBoundingClientRect: () => ({top: pageTop, height: expanded ? 1900 : 1123}),
  querySelector: () => expanded ? notice : null
};
const content = {getBoundingClientRect: () => ({top: contentTop})};
const footer = {
  style: {bottom: '20px'},
  getBoundingClientRect: () => ({top: footerTop, height: 16})
};
const original = getA4PageHeightLimits(page, content, footer);
assert.deepEqual(original, {firstPageLimit: 724, laterPageLimit: 1025});
expanded = true;
contentTop += 40; // The oversize notice adds 30px plus its bottom margin.
footerTop += 777;
assert.deepEqual(getA4PageHeightLimits(page, content, footer), original);
pageTop -= 400;
contentTop -= 400;
footerTop -= 400;
assert.deepEqual(getA4PageHeightLimits(page, content, footer), original);
contentTop += 90; // Three more title lines must reduce only the first-page space.
assert.deepEqual(getA4PageHeightLimits(page, content, footer), {
  firstPageLimit: original.firstPageLimit - 90, laterPageLimit: original.laterPageLimit
});
""")


def test_late_callbacks_keep_new_observer_and_pause_during_drag():
    setup = _section("let resizeObserver = null;", "\n        }\n\n        // 恢复更新前")
    _node(r"""
const assert = require('node:assert/strict');
global.window = {};
global.draggedItemData = null;
const observers = [], frames = [], fontCallbacks = [];
let rebalances = 0;
global.rebalanceA4PaperPages = () => { rebalances++; };
global.requestAnimationFrame = callback => { frames.push(callback); return frames.length; };
global.ResizeObserver = class {
  constructor(callback) {this.callback = callback; this.disconnected = false; observers.push(this);}
  observe() {}
  disconnect() {this.disconnected = true;}
};
global.document = {fonts: {ready: {then(callback) {
  fontCallbacks.push(callback); return {catch() {}};
}}}};
function sheet() {return {isConnected: true, querySelectorAll: () => [], querySelector: () => null};}
function install(sheet, meta = {}, totalCount = 1, totalScore = 5) {
""" + setup + r"""
}
const oldSheet = sheet();
install(oldSheet);
const oldCallback = window.scheduleActiveA4Repagination;
oldSheet.isConnected = false;
install(sheet());
const currentCallback = window.scheduleActiveA4Repagination;
oldCallback();
fontCallbacks[0]();
assert.equal(observers[0].disconnected, true);
assert.equal(observers[1].disconnected, false);
assert.equal(window.activeA4PaginationResizeObserver, observers[1]);
currentCallback(); currentCallback();
assert.equal(frames.length, 1, 'one frame must coalesce multiple size changes');
frames[0]();
assert.equal(rebalances, 1);
draggedItemData = {};
currentCallback();
assert.equal(frames.length, 1, 'placeholder changes must not repaginate mid-drag');
draggedItemData = null;
currentCallback();
frames[1]();
assert.equal(rebalances, 2);
// A queued callback from a replaced canvas must not measure the new canvas.
currentCallback();
install(sheet());
frames[2]();
assert.equal(rebalances, 2);
assert.equal(observers[2].disconnected, false);
""")


def test_drag_uses_question_ids_across_wrappers_pages_and_custom_types():
    helpers = _section("function reorderItemsWithinType(", "// Move Question Order within same question type")
    helpers += _section("function getPaperDragTargetPosition(", "window.onPaperCanvasDragStart =")
    _node(helpers + r"""
const assert = require('node:assert/strict');
const questionsMap = Object.fromEntries([1, 2, 3, 4].map(id => [id, {question_type: 'custom_long'}]));
questionsMap[9] = {question_type: 'single_choice'};
questionsMap[10] = {question_type: 'detailed_answer'};
global.window = {PaperStore: {questionsMap}};
function move(ids, from, target, after) {
  const cart = ids.map(id => ({id}));
  const position = getPaperDragTargetPosition(cart, questionsMap, 'custom_long', from, target, after);
  return reorderItemsWithinType(cart, 'custom_long', position.fromIndex, position.toIndex).map(item => item.id);
}
assert.deepEqual(move([1,2,3,4], 1, 4, true), [2,3,4,1]);
assert.deepEqual(move([1,2,3,4], 4, 2, false), [1,4,2,3]);
assert.deepEqual(move([1,2,3,4], 4, 1, true), [1,4,2,3]);
assert.deepEqual(move([1,2,3,4], 2, 3, false), [1,2,3,4]);
assert.deepEqual(move([1,9,2,3,10,4], 1, 4, true), [2,9,3,4,10,1]);
const cart = [1,9,2,3,10,4].map(id => ({id}));
assert.equal(getPaperDragTargetPosition(cart, questionsMap, 'custom_long', 1, 9, true), null);
assert.equal(getPaperDragTargetPosition(cart, questionsMap, 'custom_long', 1, 1, true), null);
assert.equal(getPaperDragTargetPosition(cart, questionsMap, 'custom_long', 1, 99, true), null);
""")


def test_drag_return_to_source_and_invalid_drop_cancel_stale_target():
    handlers = _section("function reorderItemsWithinType(", "// Move Question Order within same question type")
    handlers += _section("let draggedItemData = null;", "// Solution Space Handlers")
    _node("global.window = {};\n" + handlers + r"""
const assert = require('node:assert/strict');
global.saveCartToStorage = () => {};
global.renderPart3QuestionStream = () => {};
window.renderPaperCanvas = () => {};
const map = Object.fromEntries([1,2,3].map(id => [id, {question_type: 'single_choice'}]));
function wrapper() {
  return {
    children: [],
    insertBefore(node, anchor) {
      if (node.parentNode) node.parentNode.removeChild(node);
      const index = anchor ? this.children.indexOf(anchor) : this.children.length;
      this.children.splice(index, 0, node);
      node.parentNode = this;
    },
    removeChild(node) {
      this.children.splice(this.children.indexOf(node), 1);
      node.parentNode = null;
    }
  };
}
function card(id, type = 'single_choice') {
  const node = {
    dataset: {qid: String(id), qtype: type},
    isConnected: true,
    classList: {remove() {}},
    closest() {return this;},
    getBoundingClientRect: () => ({top: 100, height: 100})
  };
  wrapper().insertBefore(node, null);
  return node;
}
const source = card(1), target = card(3), other = card(4, 'detailed_answer');
const blank = {closest: () => null};
function begin() {
  window.PaperStore = {cart: [1,2,3].map(id => ({id})), questionsMap: map};
  draggedItemData = {qid: 1, qType: 'single_choice', element: source, target: null};
  dragPlaceholder = {contains(node) {return node === this;}, closest: () => null};
  source.parentNode.insertBefore(dragPlaceholder, source);
}
function event(node) {
  return {target: node, currentTarget: node, clientY: 175, preventDefault() {}, dataTransfer: {}};
}
function ids() {return window.PaperStore.cart.map(item => item.id);}
begin();
window.onPaperCanvasDragOver(event(target));
assert.equal(draggedItemData.target.qid, 3);
window.onPaperCanvasDragOver(event(source));
assert.equal(draggedItemData.target, null);
assert.equal(dragPlaceholder.parentNode, source.parentNode);
window.onPaperCanvasDrop(event(source));
assert.deepEqual(ids(), [1,2,3]);
// Even without a final dragover, the physical release target must be checked.
for (const invalidTarget of [source, blank, other]) {
  begin();
  window.onPaperCanvasDragOver(event(target));
  window.onPaperCanvasDrop(event(invalidTarget));
  assert.deepEqual(ids(), [1,2,3]);
}
begin();
window.onPaperCanvasDragOver(event(target));
window.onPaperCanvasDragOver(event(other));
assert.equal(draggedItemData.target, null);
assert.equal(dragPlaceholder.parentNode, source.parentNode);
window.onPaperCanvasDragEnd(event(source));
assert.deepEqual(ids(), [1,2,3]);
begin();
window.onPaperCanvasDragOver(event(target));
window.onPaperCanvasDrop(event(dragPlaceholder));
assert.deepEqual(ids(), [2,3,1]);
// Native dragend after an accepted drop must not apply the move twice.
window.onPaperCanvasDragEnd(event(source));
assert.deepEqual(ids(), [2,3,1]);
""")
