"""Real offline UI with synthetic questions, source-only copy and empty DB."""

import json

import pytest

from test_preview_browser import browser, pytestmark  # noqa: F401

MAIN = 'phy:momentum-conservation'
AUX = 'phy:work-energy-theorem'


def _fresh(browser, width=1600):
    browser.command('open', browser.evaluate('location.href'))
    browser.command('set', 'viewport', str(width), '1100')
    browser.command('wait', '--fn', "typeof window.PhysicsKnowledgePoints === 'object' && typeof window.selectQuestion === 'function'")
    browser.evaluate("selectWorkspace('bank', '题库研讨工作台'); true")


def _question(browser, label, points):
    return browser.evaluate("""(async () => {
        const form = new FormData();
        form.set('content', %s);
        form.set('question_type','detailed_answer'); form.set('difficulty','normal');
        form.set('category_compulsory','选择性必修第一册');
        form.set('category_chapter','第一章 动量守恒定律'); form.set('category_knowledge','动量守恒定律');
        form.set('tags','物理保真,碰撞'); form.set('knowledge_points', %s);
        const response=await fetch('/api/questions',{method:'POST',body:form});
        const data=await response.json(); if(!response.ok)throw new Error(JSON.stringify(data));
        return data.question.id;
    })()""" % (json.dumps(label + r' $\vec{v}=-2.00\,\mathrm{m/s}$，电流 $i=1.60\,\mathrm{mA}$。'), json.dumps(json.dumps(points))))


def _edit(browser, qid):
    browser.evaluate('selectQuestion({id:' + str(qid) + '}); true')
    browser.command('wait', '--fn', f"EditorState.questionId==={qid} && !questionDetailLoading && !isEditorModified()")
    browser.command('click', '#editQuestionFromPreviewBtn')
    browser.command('wait', '--fn', "!document.getElementById('editorSection').classList.contains('hidden')")
    browser.command('click', '[data-editor-panel-target="classification"]')


def _choose(browser, context, word, code):
    kind = 'edit' if context == 'editor' else 'bank'
    host = '#editKnowledgePointPicker' if kind == 'edit' else '#bankKnowledgePointPicker'
    popup = '#mb-kp-picker-' + kind
    if not browser.evaluate('document.querySelector(' + json.dumps(popup) + ').open'):
        browser.command('scrollintoview', host + ' .mb-kp-toggle')
        browser.command('click', host + ' .mb-kp-toggle')
    browser.command('fill', popup + ' .mb-kp-tools input', word)
    selector = f'{popup} .mb-kp-option[data-code="{code}"]'
    browser.command('wait', '--fn', '!!document.querySelector(' + json.dumps(selector) + ')')
    browser.command('scrollintoview', selector)
    browser.settle()
    browser.command('click', selector)


def _role(browser, role):
    browser.command('press', 'Escape')
    browser.command('click', '#editKnowledgePointPicker .mb-kp-selected button:last-child')
    browser.command('select', '#editKnowledgePointPicker .mb-kp-menu select', role)
    browser.command('click', '#editKnowledgePointPicker .mb-kp-menu > button:last-of-type')


@pytest.mark.parametrize('width', [1600, 375])
def test_manual_points_save_reload_draft_and_exact_filters(browser, tmp_path, width):
    _fresh(browser, width)
    qid = _question(browser, '知识点综合题' + str(width), [{'code': MAIN}])
    other = _question(browser, '另一物理题' + str(width), [{'code': MAIN}])
    _edit(browser, qid)
    original = browser.evaluate(f"fetch('/api/questions/{qid}').then(r=>r.json())")
    _choose(browser, 'editor', '动能定理', AUX)
    _role(browser, 'auxiliary')
    assert browser.evaluate('isEditorModified()')
    assert browser.evaluate('KnowledgePointState.snapshot().map(({code,role,status})=>({code,role,status}))') == [
        {'code': MAIN, 'role': 'main', 'status': 'confirmed'},
        {'code': AUX, 'role': 'auxiliary', 'status': 'confirmed'},
    ]
    # Similar synthetic questions may legitimately trigger the existing local
    # duplicate review. Handle that user decision, never bypass the safeguard.
    browser.evaluate('window.__kpSaveDone=null; saveQuestion(true).then(value=>window.__kpSaveDone=value); true')
    browser.command('wait', '--fn', "window.__kpSaveDone!==null || document.getElementById('duplicateReviewIndependentBtn').offsetParent!==null")
    if browser.evaluate("document.getElementById('duplicateReviewIndependentBtn').offsetParent!==null"):
        browser.command('click', '#duplicateReviewIndependentBtn')
    browser.command('wait', '--fn', 'window.__kpSaveDone!==null')
    assert browser.evaluate('window.__kpSaveDone') is True
    browser.command('wait', '--fn', '!isQuestionSaveInFlight() && !isEditorModified()')
    stored = browser.evaluate(f"fetch('/api/questions/{qid}').then(r=>r.json())")
    for field in ('content', 'tags', 'category_compulsory', 'category_chapter', 'category_knowledge'):
        assert stored[field] == original[field]
    assert [point['role'] for point in stored['knowledge_points']] == ['main', 'auxiliary']
    browser.evaluate("openQuestionEditorModal('classification');true")
    browser.settle()
    assert browser.evaluate("document.querySelectorAll('#editKnowledgePointPicker .mb-kp-selected button').length===2")
    assert browser.evaluate("[...document.querySelectorAll('#editKnowledgePointPicker .mb-kp-selected button')].every(n=>n.getBoundingClientRect().height>=" + str(43 if width==375 else 27) + ")")
    assert browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    browser.command('screenshot', str(tmp_path / f'knowledge-editor-{width}.png'))
    browser.command('click', '#editorSection .question-editor-close')
    _fresh(browser, width)
    _edit(browser, qid)
    assert browser.evaluate('KnowledgePointState.snapshot()[1].role') == 'auxiliary'
    assert not browser.evaluate('isEditorModified()')
    browser.command('click', '#editorSection .question-editor-close')
    if width == 375:
        browser.command('click', '.bank-detail-back')
    browser.command('click', '.bank-filter-toggle')
    _choose(browser, 'filter', '动量守恒', MAIN)
    _choose(browser, 'filter', '动能定理', AUX)
    browser.command('select', '#mb-kp-picker-bank select[aria-label="匹配方式"]', 'all')
    browser.command('select', '#mb-kp-picker-bank select[aria-label="考查作用"]', 'all')
    browser.command('wait', '--fn', f"!!document.querySelector('#questionsList [data-id=\"{qid}\"]') && !document.querySelector('#questionsList [data-id=\"{other}\"]')")
    browser.command('select', '#mb-kp-picker-bank select[aria-label="考查作用"]', 'main')
    browser.command('press', 'Escape')
    browser.command('wait', '--fn', "document.getElementById('questionsList').textContent.includes('未找到匹配题目')")
    browser.command('click', '#clearBankFiltersBtn')
    browser.command('wait', '--fn', f"!!document.querySelector('#questionsList [data-id=\"{other}\"]')")
    assert browser.evaluate('PhysicsKnowledgePoints.filterCount()') == 0
    _edit(browser, qid)
    browser.evaluate("document.getElementById('editContent').value+=' 草稿'; saveCurrentToDrafts(); true")
    draft = browser.evaluate('getLocalStorageDrafts()[0]')
    assert [point['code'] for point in draft['knowledge_points']] == [MAIN, AUX]
    browser.evaluate('selectDraft(' + json.dumps(draft) + '); true')
    assert browser.evaluate('KnowledgePointState.snapshot()[1].role') == 'auxiliary'
    assert not browser.evaluate('isEditorModified()')


def test_personal_alias_is_text_only_and_late_catalogue_cannot_cross_questions(browser):
    _fresh(browser)
    qid = _question(browser, '自建知识点与会话测试', [])
    _edit(browser, qid)
    browser.command('click', '#editKnowledgePointPicker .mb-kp-create summary')
    name = '<img src=x onerror=alert(1)>个人点'
    browser.command('fill', '#editKnowledgePointPicker .mb-kp-create input.glass-input', name)
    browser.command('fill', '#editKnowledgePointPicker .mb-kp-create textarea', '个人检索别名')
    browser.command('click', '#editKnowledgePointPicker .mb-kp-create > button')
    browser.command('wait', '--fn', 'KnowledgePointState.snapshot().length===1')
    assert browser.evaluate("document.querySelector('#editKnowledgePointPicker .mb-kp-selected button').textContent") == name
    assert browser.evaluate("document.querySelectorAll('#editKnowledgePointPicker .mb-kp-selected img').length") == 0
    assert browser.evaluate("fetch('/api/knowledge-points?q=个人检索别名').then(r=>r.json()).then(d=>d.total)") == 1
    # A late create response must not select a point in another editor session.
    browser.evaluate("""window.__kpFetch=window.fetch; window.fetch=(url,options)=>
        String(url)==='/api/knowledge-points' && options?.method==='POST'
        ? new Promise(resolve=>{window.__kpLate=()=>resolve(new Response(JSON.stringify({code:'local:late',name:'错误串题',aliases:[],curriculum_paths:[]}),{status:200}));})
        : window.__kpFetch(url,options); true""")
    browser.command('fill', '#editKnowledgePointPicker .mb-kp-create input.glass-input', '迟到创建')
    browser.command('click', '#editKnowledgePointPicker .mb-kp-create > button')
    browser.command('wait', '--fn', "typeof window.__kpLate === 'function'")
    browser.evaluate("EditorState.reset(); KnowledgePointState.reset(); window.__kpLate(); true")
    browser.settle()
    assert browser.evaluate('KnowledgePointState.snapshot()') == []
    browser.evaluate('window.fetch=window.__kpFetch; true')



def test_late_save_preserves_newer_point_role_as_unsaved_edit(browser):
    _fresh(browser)
    qid = _question(browser, '保存快照专用物理题', [{'code': MAIN}])
    _edit(browser, qid)
    _choose(browser, 'editor', '动能定理', AUX)
    browser.evaluate("""window.__kpOriginalFetch=window.fetch;
    window.fetch=async(url,options)=>{
        const response=await window.__kpOriginalFetch(url,options);
        if(String(url)==='/api/questions/%s' && options && options.method==='PUT')
            await new Promise(resolve=>{window.__kpRelease=resolve;});
        return response;
    }; window.__kpSaveDone=null; saveQuestion(true).then(value=>window.__kpSaveDone=value); true""" % qid)
    browser.command('wait', '--fn', "typeof window.__kpRelease==='function' || document.getElementById('duplicateReviewIndependentBtn').offsetParent!==null")
    if browser.evaluate("document.getElementById('duplicateReviewIndependentBtn').offsetParent!==null"):
        browser.command('click', '#duplicateReviewIndependentBtn')
    browser.command('wait', '--fn', "typeof window.__kpRelease==='function'")
    # The duplicate-review dialog remains modal until the response is accepted.
    # Exercise a newer controller edit without clicking through that safeguard.
    browser.evaluate("KnowledgePointState.setRole('" + AUX + "','auxiliary');true")
    browser.evaluate('window.__kpRelease(); true')
    browser.command('wait', '--fn', 'window.__kpSaveDone!==null && !isQuestionSaveInFlight()')
    assert browser.evaluate('window.__kpSaveDone') is True
    assert browser.evaluate('KnowledgePointState.snapshot()[1].role') == 'auxiliary'
    assert browser.evaluate('isEditorModified()')
    assert browser.evaluate(f"fetch('/api/questions/{qid}').then(r=>r.json()).then(q=>q.knowledge_points[1].role)") == 'main'
    browser.evaluate('window.fetch=window.__kpOriginalFetch; true')
