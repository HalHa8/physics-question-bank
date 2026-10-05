"""Offline FAQ content and real navigation checks; never use the personal database."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from test_preview_browser import browser


ROOT = Path(__file__).resolve().parents[1]


def test_qa_data_has_unique_traceable_entries_and_ships_with_scripts():
    node = shutil.which('node')
    assert node
    result = subprocess.run(
        [node, '-e', "global.window={};require('./static/js/qa-data.js');console.log(JSON.stringify(window.PhysicsBankQaData));"],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True,
    )
    data = json.loads(result.stdout)
    entries = data['entries']
    assert entries
    assert len({entry['id'] for entry in entries}) == len(entries)
    for entry in entries:
        assert set(entry) <= {'id', 'category', 'question', 'answer', 'keywords', 'sources', 'currentNote'}
        assert re.fullmatch(r'[a-z][a-z0-9-]*', entry['id'])
        assert entry['question'] and entry['category'] and entry['answer']
        assert all(isinstance(p, str) and p.strip() for p in entry['answer'])
        assert isinstance(entry['keywords'], list)
        assert entry['sources']
        for source in entry['sources']:
            assert set(source) == {'date', 'answerSeqs'}
            assert source['answerSeqs']
            assert all(isinstance(seq, int) and seq > 0 for seq in source['answerSeqs'])
            assert data['period']['start'] <= source['date'] <= data['period']['end']
    index = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    assert index.index('/static/js/qa-data.js') < index.index('/static/js/qa.js')
    route = (ROOT / 'main.py').read_text(encoding='utf-8')
    system = (ROOT / 'mathbank/system_routes.py').read_text(encoding='utf-8')
    assets = (ROOT / 'mathbank/web_assets.py').read_text(encoding='utf-8')
    assert 'create_application()' in route
    assert 'web_assets.build_index_response' in system
    assert '"qa-data.js"' in assets and '"qa.js"' in assets
    script = (ROOT / 'static/js/qa.js').read_text(encoding='utf-8')
    assert '.innerHTML' not in script and '.textContent' in script
    assert 'fetch(' not in script and 'localStorage' not in script



def test_qa_answers_match_physics_product_and_source_boundaries():
    node = shutil.which('node')
    result = subprocess.run(
        [node, '-e', "global.window={};require('./static/js/qa-data.js');console.log(JSON.stringify(window.PhysicsBankQaData));"],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True,
    )
    data = json.loads(result.stdout)
    entries = {entry['id']: entry for entry in data['entries']}
    assert len(entries) == 35
    assert len({entry['category'] for entry in entries.values()}) == 7
    assert data['origin']['project'] == 'MathBank'
    assert data['origin']['commit'] == '705b852454de08717940d49e7272c31b9b54a778'
    assert 'other-subjects' not in entries
    answers = lambda key: ' '.join(entries[key]['answer']) + entries[key].get('currentNote', '')
    assert 'HalHa8/physics-question-bank' in answers('download-release')
    assert 'Artifacts' in answers('download-release')
    assert '不要整体替换旧文件夹' in answers('upgrade-with-backup')
    assert '不会自动付费重试' in answers('import-failure')
    assert 'Word 公式转换器' in answers('formula-review-warning')
    assert '电路连接' in answers('pdf-images')
    assert '实验' in answers('custom-question-type') and '计算' in answers('custom-question-type')
    assert 'MathBank 的版本号' not in answers('preview-punctuation')
    assert '不是 PhysicsBank 的版本号' in answers('preview-punctuation')
    assert '独立目录与数据库' in answers('migrate-computer')
    index = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    assert 'qaSafeSharing' in index
    assert '尚未提供' in index
    assert 'qaSearchInput' in index and 'qaResetFilters' in index


@pytest.mark.skipif(os.environ.get('MATHBANK_TEST_BROWSER') != '1', reason='opt-in actual browser regression')
@pytest.mark.parametrize('viewport', [(1600, 1100), (375, 812)])
def test_qa_search_navigation_and_responsive_layout(browser, tmp_path, viewport):
    browser.command('set', 'viewport', *map(str, viewport))
    browser.evaluate("""(async () => {
        const form = new FormData();
        Object.entries({content:'QA 切换保留回归题',question_type:'calculation',difficulty:'normal'}).forEach(([key,value])=>form.set(key,value));
        const response = await fetch('/api/questions', {method:'POST',body:form}).then(r=>r.json());
        if (!response.question) throw new Error('Cannot seed disposable QA test question');
        const question = response.question;
        PaperStore.questionsMap[question.id] = question;
        addToCart(question.id, 8);
        updatePaperMeta('title','QA 切换保留的试卷信息');
        localStorage.setItem('mathbank_local_drafts',JSON.stringify([{id:'qa-test-draft',content:'QA 切换保留的草稿',isDraft:true}]));
        return true;
    })()""")
    before = browser.evaluate("JSON.stringify({cart:PaperStore.cart,meta:PaperStore.meta,drafts:localStorage.getItem('mathbank_local_drafts')})")
    browser.command('click', '#appNavQa')
    browser.command('wait', '--fn', "!document.getElementById('qaWorkspaceSection').classList.contains('hidden') && document.querySelectorAll('.qa-question').length > 0")
    initial = browser.evaluate("({total:PhysicsBankQaData.entries.length,shown:[...document.querySelectorAll('.qa-question')].filter(n=>!n.hidden).length,current:document.getElementById('appNavQa').getAttribute('aria-current')})")
    assert initial['total'] == initial['shown'] and initial['current'] == 'page'
    if not browser.evaluate("document.querySelector('.qa-question').open"):
        browser.command('click', '.qa-question:first-child summary')
    assert browser.evaluate("document.querySelector('.qa-question').open")
    browser.command('fill', '#qaSearchInput', 'api')
    api_matches = browser.evaluate("[...document.querySelectorAll('.qa-question')].filter(n=>!n.hidden).map(n=>n.id)")
    assert api_matches
    browser.command('fill', '#qaSearchInput', 'ＡＰＩ')
    assert browser.evaluate("[...document.querySelectorAll('.qa-question')].filter(n=>!n.hidden).map(n=>n.id)") == api_matches
    browser.command('fill', '#qaSearchInput', 'api key')
    assert browser.evaluate("[...document.querySelectorAll('.qa-question')].filter(n=>!n.hidden).length") <= len(api_matches)
    browser.command('fill', '#qaSearchInput', '<img src=x onerror=alert(1)>未匹配')
    assert browser.evaluate("!document.getElementById('qaEmptyState').hidden && !document.querySelector('#qaQuestionList img')")
    browser.command('click', '#qaResetFilters')
    assert browser.evaluate("document.querySelector('.qa-question').open")
    browser.command('click', '#qaCategories button:nth-child(2)')
    assert browser.evaluate("(() => {const category=document.querySelector('#qaCategories [aria-pressed=true]').dataset.category;const visible=[...document.querySelectorAll('.qa-question')].filter(n=>!n.hidden);return visible.length>0 && visible.every(n=>PhysicsBankQaData.entries.find(e=>'qa-'+e.id===n.id).category===category)})()")
    browser.command('click', '#qaResetFilters')
    browser.evaluate("openImportModal(); true")
    browser.command('wait', '--fn', "PaperStore.activeWorkspace === 'import'")
    browser.evaluate("closeImportModal(); true")
    assert browser.evaluate("PaperStore.activeWorkspace === 'qa' && !document.getElementById('qaWorkspaceSection').classList.contains('hidden')")
    assert browser.evaluate("JSON.stringify({cart:PaperStore.cart,meta:PaperStore.meta,drafts:localStorage.getItem('mathbank_local_drafts')})") == before
    layout = browser.evaluate("(() => {const qa=document.getElementById('qaWorkspaceSection');const buttons=[...document.querySelectorAll('#appNavPrimary button')].map(n=>n.getBoundingClientRect());return {overflow:qa.scrollWidth>qa.clientWidth+1,navCount:buttons.length,touch:buttons.every(r=>r.width>=44&&r.height>=44),inViewport:buttons.every(r=>r.left>=0&&r.right<=innerWidth+1)}})()")
    assert not layout['overflow'] and layout['navCount'] == 6 and layout['touch'] and layout['inViewport'], layout
    browser.command('screenshot', str(tmp_path / f'qa-{viewport[0]}-light.png'))
    browser.evaluate("document.documentElement.classList.add('dark');document.body.classList.add('dark');true")
    browser.command('wait', '--fn', "getComputedStyle(document.querySelector('#qaCategories [aria-pressed=true]')).color === getComputedStyle(document.getElementById('qaWorkspaceSection')).color && getComputedStyle(document.getElementById('qaResetFilters')).backgroundColor === getComputedStyle(document.querySelector('.qa-question')).backgroundColor")
    browser.command('screenshot', str(tmp_path / f'qa-{viewport[0]}-dark.png'))
    browser.evaluate("document.documentElement.classList.remove('dark');document.body.classList.remove('dark');selectWorkspace('dashboard','工作台');true")
    assert browser.evaluate("document.getElementById('qaWorkspaceSection').classList.contains('hidden')")
