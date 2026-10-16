"""Real browser checks for plain image choices and paper-only scaling."""
import json
import os
import pytest
from test_preview_browser import browser

pytestmark = pytest.mark.skipif(os.environ.get("MATHBANK_TEST_BROWSER") != "1", reason="opt-in browser")


def test_plain_image_choices_scale_save_reload_and_mobile(browser, tmp_path):
    result = browser.evaluate(r"""
    (async () => {
        const paths = [];
        for (const label of ['S', 'A', 'B', 'C', 'D']) {
            const canvas = document.createElement('canvas');
            canvas.width = 600; canvas.height = 400;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 600, 400);
            ctx.strokeStyle = '#111'; ctx.lineWidth = 4;
            ctx.beginPath(); ctx.moveTo(70, 40); ctx.lineTo(70, 340); ctx.lineTo(550, 340); ctx.stroke();
            ctx.strokeStyle = '#ec4899'; ctx.beginPath(); ctx.moveTo(70, 90); ctx.lineTo(480, 340); ctx.stroke();
            ctx.fillStyle = '#111'; ctx.font = '30px serif'; ctx.fillText(label, 15, 40);
            const form = new FormData();
            form.set('file', await new Promise(resolve => canvas.toBlob(resolve)), label + '.png');
            const res = await fetch('/api/upload', {method:'POST', body:form});
            if (!res.ok) throw Error(await res.text());
            paths.push((await res.json()).file_path);
        }
        const content = '物块沿光滑斜面运动，选择正确图像。\n![](' + paths[0] + ')\n\n' +
            paths.slice(1).map((path, i) => '    ' + 'ABCD'[i] + '．\n![](' + path + ')').join('\n\n');
        const form = new FormData();
        form.set('content', content); form.set('question_type','single_choice');
        form.set('image_paths', JSON.stringify(paths)); form.set('difficulty','normal');
        const res = await fetch('/api/questions', {method:'POST', body:form});
        if (!res.ok) throw Error(await res.text());
        const q = (await res.json()).question;
        window.__scaleOriginal = {id:q.id, content:q.content, paths};
        MathBankBrowserChecks.seed(0, 0);
        PaperStore.questionsMap[q.id] = q;
        PaperStore.cart = [{id:q.id,score:5}];
        PaperStore.meta.title = '物理配图排版验收';
        PaperStore.meta.show_notice = false;
        renderPaperCanvas();
        return {id:q.id};
    })()
    """)
    browser.command("wait", "--fn", "[...document.querySelectorAll('.paper-q-item img')].filter(i=>i.complete&&i.naturalWidth).length === 5")
    browser.settle()
    geometry = r"""(() => {
        const block = document.querySelector('.paper-q-item');
        return {
            columns: block.querySelector('.choices-grid').dataset.choiceColumns,
            count: block.querySelectorAll('img').length,
            value: block.querySelector('input[type=range]').value,
            width: block.querySelector('.choices-content img').getBoundingClientRect().width,
            height: block.getBoundingClientRect().height,
            rows: [...block.querySelectorAll('.choices-content img')].map(i=>i.getBoundingClientRect().top),
            sources: [...block.querySelectorAll('.choices-content img')].map(i=>new URL(i.src).pathname),
            original: PaperStore.questionsMap[Number(block.dataset.qid)].content === __scaleOriginal.content
        };
    })()"""
    before = browser.evaluate(geometry)
    assert before["columns"] == "4", before
    assert before["count"] == 5 and before["value"] == "70"
    assert before["height"] < 450, before
    assert max(before["rows"]) - min(before["rows"]) < 1, before
    assert before["original"]
    assert before["sources"] == browser.evaluate("__scaleOriginal.paths.slice(1)")
    browser.command("screenshot", str(tmp_path / "paper-images-default.png"))
    assert browser.evaluate(r"""(() => {
        const input = document.querySelector('.paper-image-scale-control input');
        input.focus(); window.__originalScaleInput = input;
        input.value = '40'; input.dispatchEvent(new Event('input', {bubbles:true}));
        return document.activeElement === input;
    })()""")
    browser.settle()
    after = browser.evaluate(geometry)
    assert after["width"] == pytest.approx(before["width"] * 40 / 70, abs=1)
    assert browser.evaluate("document.querySelector('.paper-image-scale-control input') === __originalScaleInput")
    browser.evaluate("savePaperToDb().then(()=>true)")
    browser.settle()
    saved = browser.evaluate(r"""(async () => {
        const papers = (await (await fetch('/api/papers')).json()).data;
        const paper = papers.find(p=>p.title==='物理配图排版验收');
        const detail = (await (await fetch('/api/papers/'+paper.id)).json()).data;
        await loadSavedPaper(paper.id);
        return detail.questions[0].image_scale;
    })()""")
    assert saved == 40
    browser.settle()
    assert browser.evaluate(geometry)["value"] == "40"
    browser.command("set", "viewport", "375", "812")
    browser.evaluate("setPaperMobilePane('preview'); true")
    browser.settle()
    # Reflow must keep all images in their cells; controls remain keyboard usable.
    assert browser.evaluate(r"""[...document.querySelectorAll('#a4PaperPreviewSheet .choices-content img')].every(img=>{
        const a=img.getBoundingClientRect(), b=img.closest('.choices-content').getBoundingClientRect();
        return a.right<=b.right+1 && a.width>0;
    })""")
    browser.command("scrollintoview", "#a4PaperPreviewSheet .paper-image-scale-control")
    browser.settle()
    browser.command("screenshot", str(tmp_path / "paper-images-mobile.png"))
    original = browser.evaluate(f"(async()=> (await (await fetch('/api/questions/{result['id']}')).json()).content)()")
    assert original == browser.evaluate("__scaleOriginal.content")

    browser.command("set", "viewport", "1600", "1100")
    browser.evaluate(r"""(() => {
        const item = PaperStore.cart[0], q = PaperStore.questionsMap[item.id];
        q.question_type = 'experiment'; q.figure_align = 'center';
        q.figure_align_custom = true; q.figure_size = 'large';
        q.content = '实验装置如图。\n![](' + __scaleOriginal.paths[0] + ')';
        item.solution_space = 0.5; item.image_scale = 70;
        renderPaperCanvas(); return true;
    })()""")
    browser.settle()
    for value in (150, 20, 100):
        browser.evaluate(f"""(() => {{
            const input = document.querySelector('.paper-image-scale-control input');
            input.focus(); input.value = '{value}'; input.dispatchEvent(new Event('input', {{bubbles:true}}));
            return true;
        }})()""")
        browser.settle()
        assert browser.evaluate(r"""(() => {
            const zone = document.querySelector('.solution-space-zone');
            const img = zone.querySelector('img');
            return img.getBoundingClientRect().bottom <= zone.getBoundingClientRect().bottom + 1;
        })()""")
