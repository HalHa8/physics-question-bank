"""Chapter subdivision and list/detail identity, using synthetic data and mocked AI."""
import json
import os
import pytest
from test_preview_browser import browser  # noqa: F401

pytestmark = pytest.mark.skipif(os.environ.get('MATHBANK_TEST_BROWSER') != '1', reason='opt-in browser')


@pytest.fixture(scope='module')
def trial(browser):
    browser.evaluate("selectWorkspace('bank','题库管理'); true")
    browser.command('wait', '--fn', '!!Object.keys(categoryTree).length')
    data = browser.evaluate(r"""(async () => {
        const book=Object.keys(categoryTree)[0], chapters=Object.keys(categoryTree[book]);
        const chapter=chapters[0], other=chapters[1], section=categoryTree[book][chapter][0];
        const ids=[];
        for(const [i,chap,sect] of [[0,chapter,chapter],[1,chapter,section],[2,other,'']]) {
            const form=new FormData();
            for(const [key,value] of Object.entries({content:'分类同步合成题 '+i,question_type:'single_choice',
                difficulty:'normal',category_compulsory:book,category_chapter:chap,category_knowledge:sect}))form.set(key,value);
            const response=await fetch('/api/questions',{method:'POST',body:form});
            const result=await response.json();if(!response.ok)throw Error(JSON.stringify(result));ids.push(result.question.id);
        }
        return {book,chapter,other,section,ids};
    })()""")
    yield data


@pytest.fixture
def bank(browser, trial):
    browser.command('reload')
    browser.command('wait', '--fn', "typeof selectQuestion==='function' && !!Object.keys(categoryTree).length")
    browser.command('set', 'viewport', '1600', '1100')
    browser.evaluate("window.__trial="+json.dumps(trial, ensure_ascii=False)+"; selectWorkspace('bank','题库管理'); true")
    browser.command('wait', '--fn', "document.getElementById('questionsList').getAttribute('aria-busy')!=='true' && !questionDetailLoading")
    return browser


def choose(browser, qid):
    browser.command('click', f'#questionsList .question-card[data-id="{qid}"]')
    browser.command('wait', '--fn', f"EditorState.questionId==={qid}&&!questionDetailLoading&&document.getElementById('previewSection').dataset.detailState==='ready'")


@pytest.mark.parametrize('width,dark', [(1600, False), (375, True)])
def test_subdivision_drawer_filters_and_detail_follow(bank, trial, width, dark):
    b=bank
    b.command('set','viewport',str(width),'1000')
    b.evaluate(f"document.documentElement.classList.toggle('dark',{str(dark).lower()});true")
    b.command('click','#libraryTreeToggle')
    b.command('wait','--fn',"document.querySelectorAll('#libraryTree button').length>10")
    assert b.evaluate(r"""(() => {
        const nodes=[...document.querySelectorAll('#libraryTree button')];
        const entry=nodes.find(x=>x.dataset.path===JSON.stringify([[__trial.book,__trial.chapter],'section_unassigned']));
        entry.closest('details').open=true;entry.closest('details').parentElement.open=true;
        return entry.textContent==='待细分到小节1' && nodes.some(x=>x.textContent.startsWith('本册全部题目'))
            && nodes.some(x=>x.textContent.startsWith('本章全部题目'));
    })()""")
    b.settle()
    b.command('screenshot',str(b.root/f'subdivision-tree-{width}.png'))
    b.evaluate("[...document.querySelectorAll('#libraryTree button')].find(x=>x.dataset.path===JSON.stringify([[__trial.book,__trial.chapter],'section_unassigned'])).click();true")
    b.command('wait','--fn',"document.querySelectorAll('#questionsList .question-card').length===1&&!questionDetailLoading&&EditorState.questionId===__trial.ids[0]")
    assert b.evaluate("document.getElementById('filterClassification').value==='section_unassigned' && document.getElementById('bankClassificationStatus').textContent==='待细分到小节'")
    if width<600:
        b.evaluate('showBankDetail();true')
    b.settle()
    b.command('screenshot',str(b.root/f'subdivision-detail-{width}.png'))
    assert b.evaluate("document.documentElement.scrollWidth<=innerWidth+1 && document.getElementById('reclassifyQuestionBtn').getBoundingClientRect().height>=44")


def test_filter_empty_paging_and_clear_keep_detail_consistent(bank, trial):
    b=bank
    choose(b,trial['ids'][0])
    b.evaluate("document.getElementById('filterChapter').value='';document.getElementById('searchInput').value='分类同步合成题 2';loadQuestions();true")
    b.command('wait','--fn',"!questionDetailLoading&&EditorState.questionId===__trial.ids[2]&&document.querySelectorAll('#questionsList .question-card').length===1")
    assert b.evaluate("document.querySelector('#questionsList .active').dataset.id===String(EditorState.questionId)&&document.getElementById('paperContent').textContent.includes('合成题 2')")
    b.evaluate("document.getElementById('searchInput').value='绝无匹配内容';loadQuestions();true")
    b.command('wait','--fn',"document.getElementById('previewSection').dataset.detailState==='empty'")
    assert b.evaluate("!document.querySelector('#previewSection .bank-preview-content').checkVisibility()&&document.getElementById('editQuestionFromPreviewBtn').disabled&&document.getElementById('reclassifyQuestionBtn').disabled")
    b.evaluate("document.getElementById('searchInput').value='';currentBankPage=2;loadQuestions();true")
    b.command('wait','--fn',"!questionDetailLoading&&document.getElementById('questionsList').getAttribute('aria-busy')!=='true'")
    # Server clamps pages to the available range; details must match that page.
    assert b.evaluate("document.getElementById('previewSection').dataset.detailState==='ready'&&!!document.querySelector('#questionsList .active')")


def test_late_detail_and_failure_cannot_show_stale_question(bank, trial):
    b=bank
    choose(b,trial['ids'][0])
    b.evaluate(r"""(() => {
        window.__realFetch=window.fetch;
        window.fetch=(url,options)=>String(url)==='/api/questions/'+__trial.ids[1]
            ?new Promise(resolve=>{window.__releaseDetail=()=>__realFetch(url).then(resolve);}) : __realFetch(url,options);
        selectQuestion({id:__trial.ids[1]},{fromBankList:true});return true;
    })()""")
    assert b.evaluate("!document.querySelector('#previewSection .bank-preview-content').checkVisibility()")
    b.evaluate("document.getElementById('searchInput').value='分类同步合成题 2';loadQuestions();true")
    b.command('wait','--fn',"EditorState.questionId===__trial.ids[2]&&!questionDetailLoading")
    b.evaluate("__releaseDetail();window.fetch=__realFetch;true")
    b.settle()
    assert b.evaluate("EditorState.questionId===__trial.ids[2]&&document.getElementById('paperContent').textContent.includes('合成题 2')")
    b.evaluate("window.fetch=(url,options)=>String(url)==='/api/questions/'+__trial.ids[2]?Promise.resolve(new Response('{}',{status:500})):__realFetch(url,options);selectQuestion({id:__trial.ids[2]},{fromBankList:true});true")
    b.command('wait','--fn',"document.getElementById('previewSection').dataset.detailState==='error'")
    assert b.evaluate("!document.querySelector('#previewSection .bank-preview-content').checkVisibility()&&document.getElementById('editQuestionFromPreviewBtn').disabled")
    b.evaluate('window.fetch=__realFetch;true')


def test_filter_refresh_preserves_unsaved_editor(bank, trial):
    b=bank
    choose(b,trial['ids'][0])
    b.command('click','#editQuestionFromPreviewBtn')
    b.evaluate("document.getElementById('editContent').value+=' 未保存文本';document.getElementById('editContent').dispatchEvent(new Event('input'));document.getElementById('searchInput').value='分类同步合成题 2';loadQuestions();true")
    b.command('wait','--fn',"document.getElementById('previewSection').dataset.detailState==='preserved'")
    assert b.evaluate("EditorState.questionId===__trial.ids[0]&&isEditorModified()&&document.getElementById('editContent').value.includes('未保存文本')&&!document.querySelector('#previewSection .bank-preview-content').checkVisibility()")
    stored=b.evaluate(f"fetch('/api/questions/{trial['ids'][0]}').then(r=>r.json())")
    assert '未保存文本' not in stored['content']


def mock_classify(b, *, late=False):
    b.evaluate(r"""(() => {
        window.__realFetch=window.fetch;window.__aiCalls=0;window.__writes=0;
        window.fetch=(url,options={})=>{
            if(String(url).endsWith('/api/ai/classify')) {
                __aiCalls++;
                const response=()=>new Response(JSON.stringify({status:'success',compulsory:__trial.book,chapter:__trial.chapter,
                    knowledge:__trial.section,question_form:'choice',knowledge_points:[],version_code:activeCurriculumVersion}),
                    {status:200,headers:{'Content-Type':'application/json'}});
                return LATE ? new Promise(resolve=>window.__releaseAI=()=>resolve(response())) : Promise.resolve(response());
            }
            if(options.method==='PUT')__writes++;
            return __realFetch(url,options);
        };return true;
    })()""".replace('LATE','true' if late else 'false'))


@pytest.mark.parametrize('width',[1600,375])
def test_suggestion_requires_analysis_and_confirmation_cancel_is_read_only(bank, trial, width):
    b=bank
    b.command('set','viewport',str(width),'1000')
    choose(b,trial['ids'][0])
    before=b.evaluate(f"fetch('/api/questions/{trial['ids'][0]}').then(r=>r.json())")
    mock_classify(b)
    b.command('click','#reclassifyQuestionBtn')
    b.command('wait','--fn',"getComputedStyle(document.getElementById('aiClassifyModal')).opacity==='1'")
    assert b.evaluate("__aiCalls===0&&__writes===0&&document.getElementById('classifyCurrentPlacement').textContent.includes('待细分')")
    b.command('click','#classifyAIButton')
    b.command('wait','--fn',"document.getElementById('classifyResult').checkVisibility()")
    assert b.evaluate("__aiCalls===1&&__writes===0&&document.getElementById('classifyApplyButton').disabled")
    assert b.evaluate("document.getElementById('recKnowledge').textContent===__trial.section")
    b.settle()
    b.command('screenshot',str(b.root/f'subdivision-suggestion-{width}.png'))
    b.command('press','Escape')
    after=b.evaluate(f"fetch('/api/questions/{trial['ids'][0]}').then(r=>r.json())")
    assert before==after
    assert b.evaluate('__writes===0&&!isEditorModified()')


def test_edit_or_cancel_during_ai_rejects_late_suggestion(bank, trial):
    b=bank
    choose(b,trial['ids'][0])
    mock_classify(b,late=True)
    b.command('click','#reclassifyQuestionBtn')
    b.command('wait','--fn',"getComputedStyle(document.getElementById('aiClassifyModal')).opacity==='1'")
    b.command('click','#classifyAIButton')
    b.evaluate("document.getElementById('editContent').value+=' 已改动';__releaseAI();true")
    b.command('wait','--fn',"!document.getElementById('classifyAIButton').classList.contains('hidden')")
    assert b.evaluate("__writes===0&&temporaryClassifyData===null&&document.getElementById('classifyResult').classList.contains('hidden')")


def test_explicit_confirmation_saves_once_and_updates_subdivision_count(bank, trial):
    b=bank
    choose(b,trial['ids'][0])
    before=b.evaluate(f"fetch('/api/questions/{trial['ids'][0]}').then(r=>r.json())")
    mock_classify(b)
    b.command('click','#reclassifyQuestionBtn')
    b.command('wait','--fn',"getComputedStyle(document.getElementById('aiClassifyModal')).opacity==='1'")
    b.command('click','#classifyAIButton')
    b.command('wait','--fn',"document.getElementById('classifyResult').checkVisibility()")
    b.command('click','#classifySingleChoiceBtn')
    b.command('click','#classifyApplyButton')
    b.command('wait','--fn',"__writes===1&&!isQuestionSaveInFlight()&&!isEditorModified()")
    saved=b.evaluate(f"fetch('/api/questions/{trial['ids'][0]}').then(r=>r.json())")
    assert saved['category_knowledge']==trial['section']
    for field in ['content','answer_markdown','image_paths','question_type','difficulty','source']:
        assert saved[field]==before[field]
    assert b.evaluate('__aiCalls===1&&__writes===1')
    data=b.evaluate("fetch('/api/library/overview').then(r=>r.json())")
    chapter=next(ch for book in data['books'] if book['name']==trial['book'] for ch in book['chapters'] if ch['name']==trial['chapter'])
    assert chapter['section_unassigned']==0
    assert next(s for s in chapter['sections'] if s['name']==trial['section'])['count']==2
