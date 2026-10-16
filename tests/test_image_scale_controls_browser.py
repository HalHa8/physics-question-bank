"""Native pointer/keyboard checks; no production questions or AI services."""
import json
import os

import pytest
from test_preview_browser import browser

pytestmark = pytest.mark.skipif(os.environ.get('MATHBANK_TEST_BROWSER') != '1', reason='opt-in browser')


@pytest.fixture(scope='module')
def image_questions(browser):
    return browser.evaluate(r"""(async () => {
        const paths = [];
        for (const letter of ['S', 'A', 'B', 'C', 'D']) {
            const canvas = document.createElement('canvas');
            canvas.width = 600; canvas.height = 400;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 600, 400);
            ctx.strokeStyle = '#111'; ctx.lineWidth = 4;
            ctx.beginPath(); ctx.moveTo(70, 40); ctx.lineTo(70, 340); ctx.lineTo(550, 340); ctx.stroke();
            ctx.strokeStyle = '#ec4899'; ctx.beginPath(); ctx.moveTo(70, 90); ctx.lineTo(480, 340); ctx.stroke();
            ctx.fillStyle = '#111'; ctx.font = '30px serif'; ctx.fillText(letter, 15, 40);
            const form = new FormData();
            form.set('file', await new Promise(resolve => canvas.toBlob(resolve)), letter + '.png');
            const res = await fetch('/api/upload', {method:'POST', body:form});
            if (!res.ok) throw Error(await res.text());
            paths.push((await res.json()).file_path);
        }
        const content = '物块沿光滑斜面运动，选择正确图像。\n![](' + paths[0] + ')\n\n'
            + paths.slice(1).map((p, i) => 'ABCD'[i] + '．\n![](' + p + ')').join('\n\n');
        const questions = [];
        for (const source of [content, content + '\n', '不含插图的对照题。']) {
            const form = new FormData();
            form.set('content', source); form.set('question_type', 'single_choice');
            form.set('difficulty', 'normal');
            const res = await fetch('/api/questions', {method:'POST', body:form});
            if (!res.ok) throw Error(await res.text());
            questions.push((await res.json()).question);
        }
        return questions;
    })()""")


def slider_bounds(browser, selector):
    browser.command('scrollintoview', selector)
    browser.evaluate(f"document.querySelector({json.dumps(selector)}).focus(); true")
    browser.settle()
    return browser.evaluate(f"""(() => {{
        const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect();
        return {{x:r.x, y:r.y + r.height/2, width:r.width}};
    }})()""")


def pointer_drag(browser, bounds, start=0.385, end=0.85):
    browser.command('mouse', 'move', str(round(bounds['x'] + 8 + (bounds['width'] - 16) * start)), str(round(bounds['y'])))
    browser.command('mouse', 'down')
    browser.command('mouse', 'move', str(round(bounds['x'] + 8 + (bounds['width'] - 16) * end)), str(round(bounds['y'])), '--steps', '12', '--duration', '200')


def test_floating_slider_native_drag_does_not_sort(browser, image_questions, tmp_path):
    first, second, _ = image_questions
    browser.evaluate(f"""(() => {{
        MathBankBrowserChecks.seed(0, 0);
        const questions = {json.dumps(image_questions[:2])};
        questions.forEach(q => PaperStore.questionsMap[q.id] = q);
        PaperStore.cart = questions.map(q => ({{id:q.id, score:5, image_scale:70}}));
        PaperStore.meta.show_notice = false;
        renderPaperCanvas();
        window.__sliderDragStarts = 0;
        document.addEventListener('dragstart', () => window.__sliderDragStarts++, true);
        document.addEventListener('pointerdown', e => window.__sliderPointer = e.pointerId, true);
        return true;
    }})()""")
    browser.command('wait', '--fn', "[...document.querySelectorAll('.paper-q-item img')].every(i=>i.complete && i.naturalWidth)")
    browser.settle()
    selector = f'.paper-q-item[data-qid="{first["id"]}"] .paper-image-scale-control input'
    browser.command('mouse', 'move', '5', '5')
    before = browser.evaluate(r"""(() => {
        const card = document.querySelector('.paper-q-item'), control = card.querySelector('label');
        const height = card.offsetHeight;
        const hidden = getComputedStyle(control).opacity === '0';
        control.style.display = 'none'; const without = card.offsetHeight; control.style.display = '';
        return {height, without, hidden, position:getComputedStyle(control).position,
            width:card.querySelector('.choices-content img').getBoundingClientRect().width};
    })()""")
    assert before['hidden'] and before['position'] == 'absolute', before
    assert before['height'] == before['without'], before
    bounds = slider_bounds(browser, selector)
    assert browser.evaluate("getComputedStyle(document.querySelector('.paper-image-scale-control')).opacity") == '1'
    pointer_drag(browser, bounds)
    try:
        state = browser.evaluate(r"""(() => {
            const card = document.querySelector('.paper-q-item');
            return {draggable:card.draggable, drags:__sliderDragStarts,
                placeholder:!!document.querySelector('.paper-drag-placeholder'),
                ids:PaperStore.cart.map(q=>q.id), scale:PaperStore.cart[0].image_scale,
                width:card.querySelector('.choices-content img').getBoundingClientRect().width};
        })()""")
        assert state['drags'] == 0 and not state['placeholder'] and not state['draggable'], state
        assert state['ids'] == [first['id'], second['id']], state
        assert state['scale'] > 100 and state['width'] > before['width'], state
    finally:
        # Release outside the range: document-level cleanup must still run.
        browser.command('mouse', 'move', '10', '10')
        browser.command('mouse', 'up')
    browser.settle()
    assert browser.evaluate("document.querySelector('.paper-q-item').draggable")
    # Real keyboard input retains focus and doesn't reconstruct the range.
    browser.evaluate(f"window.__sliderNode = document.querySelector({json.dumps(selector)}); __sliderNode.focus(); true")
    browser.command('press', 'Home')
    browser.command('press', 'ArrowRight')
    browser.settle()
    assert browser.evaluate("document.activeElement === __sliderNode && __sliderNode.value === '25'")
    assert browser.evaluate("PaperStore.cart.map(q=>q.id)") == [first['id'], second['id']]
    for event in ('pointercancel', 'blur'):
        bounds = slider_bounds(browser, selector)
        pointer_drag(browser, bounds, start=0.04, end=0.5)
        browser.evaluate("window.dispatchEvent(new Event('blur')); true" if event == 'blur' else
                         "document.dispatchEvent(new PointerEvent('pointercancel',{pointerId:__sliderPointer})); true")
        browser.command('mouse', 'up')
        assert browser.evaluate("document.querySelector('.paper-q-item').draggable")
    browser.command('screenshot', str(tmp_path / 'floating-paper-slider.png'))
    # The native sorting path is still enabled after a slider gesture.
    assert browser.evaluate(f'MathBankBrowserChecks.drag({first["id"]}, {second["id"]})') == [second['id'], first['id']]
    assert all(q['overflow'] <= 2 for page in browser.evaluate('MathBankBrowserChecks.measure()') for q in page['questions'])


def test_bank_preview_grouping_scale_persistence_and_independence(browser, image_questions, tmp_path):
    first, second, plain = image_questions
    browser.evaluate("selectWorkspace('bank','题库管理'); loadQuestions(); true")
    browser.command('wait', '--fn', "document.getElementById('questionsList').getAttribute('aria-busy') !== 'true' && !questionDetailLoading")

    def select(question):
        browser.evaluate(f'selectQuestion({{id:{question["id"]}}}, {{silent:true}}); true')
        browser.command('wait', '--fn', f'EditorState.questionId === {question["id"]} && !questionDetailLoading')
        browser.settle()

    select(first)
    browser.command('wait', '--fn', "[...document.querySelectorAll('#paperContent img')].filter(i=>i.complete && i.naturalWidth).length === 5")
    browser.settle()
    geometry = r"""(() => {
        const host = document.getElementById('paperContent');
        const options = [...host.querySelectorAll('.choices-item')];
        return {value:host.querySelector('input[type=range]').value,
            columns:host.querySelector('.choices-grid').dataset.choiceColumns,
            labels:options.map(i=>i.querySelector('.choices-label').textContent),
            rows:options.map(i=>i.querySelector('img').getBoundingClientRect().top),
            widths:options.map(i=>i.querySelector('img').getBoundingClientRect().width),
            fits:options.every(i=>i.scrollWidth<=i.clientWidth+1),
            detached:options.some(i=>i.querySelector('img').parentElement.style.float==='right')};
    })()"""
    before = browser.evaluate(geometry)
    assert before['value'] == '70' and before['columns'] == '4', before
    assert before['labels'] == ['A.', 'B.', 'C.', 'D.'] and not before['detached'], before
    assert max(before['rows']) - min(before['rows']) < 1, before
    paper_scales = browser.evaluate('PaperStore.cart.map(q=>[q.id,q.image_scale])')
    bounds = slider_bounds(browser, '#paperContent .bank-image-scale-control input')
    pointer_drag(browser, bounds)
    browser.command('mouse', 'up')
    browser.settle()
    assert int(browser.evaluate(geometry)['value']) > 100
    browser.command('press', 'Home')
    for _ in range(3):
        browser.command('press', 'ArrowRight')
    browser.settle()
    after = browser.evaluate(geometry)
    assert after['value'] == '35' and after['fits'], after
    assert after['widths'] == pytest.approx([w / 2 for w in before['widths']], abs=1), after
    assert not browser.evaluate('isEditorModified()')
    assert browser.evaluate('PaperStore.cart.map(q=>[q.id,q.image_scale])') == paper_scales
    assert browser.evaluate("document.querySelector('#contentPreview .bank-image-scale-control input').value") == '35'
    browser.command('screenshot', str(tmp_path / 'bank-four-image-options.png'))
    select(second)
    assert browser.evaluate(geometry)['value'] == '70'
    select(plain)
    assert not browser.evaluate("!!document.querySelector('#paperContent .bank-image-scale-control')")
    select(first)
    assert browser.evaluate(geometry)['value'] == '35'
    # A page reload must restore only this local bank preference, not edit the question.
    url = browser.evaluate('location.href')
    browser.command('open', url)
    browser.command('wait', '--fn', "typeof selectQuestion === 'function' && typeof renderPaperCanvas === 'function'")
    browser.evaluate("selectWorkspace('bank','题库管理'); loadQuestions(); true")
    browser.command('wait', '--fn', "document.getElementById('questionsList').getAttribute('aria-busy') !== 'true' && !questionDetailLoading")
    select(first)
    assert browser.evaluate(geometry)['value'] == '35'
    saved = browser.evaluate(f"fetch('/api/questions/{first['id']}').then(r=>r.json())")
    assert all(saved.get(k) == first.get(k) for k in ('content', 'image_paths', 'image_layouts', 'figure_size', 'figure_align'))
    assert not browser.evaluate('isEditorModified()')
    browser.command('set', 'viewport', '375', '812')
    browser.evaluate('showBankDetail(); true')
    browser.settle()
    assert browser.evaluate(geometry)['fits']
    bounds = slider_bounds(browser, '#paperContent .bank-image-scale-control input')
    browser.command('press', 'End')
    browser.settle()
    assert browser.evaluate(geometry)['value'] == '150' and browser.evaluate(geometry)['fits']
    browser.command('screenshot', str(tmp_path / 'bank-mobile-image-options.png'))
    browser.command('set', 'viewport', '1600', '1100')
