"""Knowledge classification UI against a disposable app; model replies are fake."""
import os
from pathlib import Path

import pytest

from test_preview_browser import browser  # noqa: F401


pytestmark = pytest.mark.skipif(os.environ.get("MATHBANK_TEST_BROWSER") != "1",
                                reason="opt-in isolated browser regression")
EVIDENCE = Path(__file__).resolve().parents[1] / ".system_generated" / "ai-knowledge-browser"


def click(browser, selector):
    browser.command("scrollintoview", selector)
    browser.settle()
    browser.command("click", selector)


@pytest.mark.parametrize("width,height", [(1600, 1100), (375, 812)])
def test_same_classification_request_merges_pending_points_then_requires_teacher_confirmation(browser, width, height):
    browser.command("reload")
    browser.command("set", "viewport", str(width), str(height))
    browser.command("wait", "--fn", "typeof window.renderParsedQuestionsList==='function'")
    browser.command("network", "route", "**/api/ai/**", "--abort")
    question = browser.evaluate(r"""(async()=>{
      await loadCategories();await loadKnowledgePointCatalog();selectWorkspace('bank','题库管理');
      const form=new FormData();Object.entries({content:'物体A、B相互作用，求合外力做功与动能变化。 视口'+innerWidth,
        answer_markdown:'动能变化等于合外力做功。',question_type:'detailed_answer',difficulty:'normal',
        category_compulsory:'选择性必修第一册',category_chapter:'第一章 动量守恒定律',category_knowledge:'动量',
        knowledge_points:JSON.stringify([{code:'phy:momentum-conservation',role:'auxiliary',status:'suggested',origin:'historical'}])
      }).forEach(([key,value])=>form.set(key,value));
      const response=await fetch('/api/questions',{method:'POST',body:form});const body=await response.json();
      if(!response.ok)throw Error(JSON.stringify(body));await loadQuestions();return body.question;
    })()""")
    qid = question["id"]
    browser.command("wait", f'#questionsList [data-id="{qid}"]')
    browser.command("click", f'#questionsList [data-id="{qid}"]')
    browser.command("wait", "--fn", f"EditorState.questionId==={qid}&&!questionDetailLoading&&!isEditorModified()")
    browser.command("click", "#editQuestionFromPreviewBtn")
    browser.command("click", '[data-editor-panel-target="classification"]')
    assert browser.evaluate("document.querySelectorAll('#editKnowledgePointPicker .mb-kp-selected button').length")
    assert browser.evaluate("document.getElementById('editKnowledgePointPicker').textContent.includes('动量')")
    assert "待确认" in browser.evaluate("document.getElementById('editKnowledgePointPicker').textContent")
    browser.evaluate(r"""(()=>{
      window.__knowledgeOriginalFetch=window.fetch;window.__knowledgeRequests=[];
      window.fetch=(url,options={})=>{
        if(String(url).endsWith('/api/ai/classify')){
          window.__knowledgeRequests.push(Object.fromEntries(options.body));
          return Promise.resolve(new Response(JSON.stringify({status:'success',compulsory:'选择性必修第一册',
            chapter:'第一章 动量守恒定律',knowledge:'动量',question_form:'detailed_answer',
            knowledge_points:[{code:'phy:momentum-conservation',name:'动量守恒定律',role:'main',status:'suggested',origin:'ai_classification'},
              {code:'phy:work-energy-theorem',name:'动能定理',role:'main',status:'confirmed',origin:'ai_classification',
                evidence_source:'content',evidence:'物体A、B',reason:'物理情境及原解中使用动能定理。'}],knowledge_point_warnings:[]
          }),{status:200,headers:{'Content-Type':'application/json'}}));
        }return window.__knowledgeOriginalFetch(url,options);
      };return true;
    })()""")
    click(browser, "#editKnowledgePointPicker .mb-kp-header button:nth-of-type(2)")
    browser.command("wait", "--fn", "!document.getElementById('classifyResult').classList.contains('hidden')")
    assert browser.evaluate("window.__knowledgeRequests.length") == 1
    assert browser.evaluate("window.__knowledgeRequests[0].answer_markdown") == "动能变化等于合外力做功。"
    assert browser.evaluate("document.getElementById('classifyKnowledgePoints').textContent.includes('动能定理')")
    assert browser.evaluate("document.getElementById('classifyAcceptKnowledgePoints')===null")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    browser.command('wait', '--fn', "getComputedStyle(document.getElementById('aiClassifyModal')).opacity==='1'")
    assert browser.evaluate("document.getElementById('recQuestionForm').textContent") == '计算题'
    browser.settle()
    browser.command("screenshot", str(EVIDENCE / f"classification-{width}.png"))
    assert browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    click(browser, "#classifyApplyButton")
    duplicate = "document.getElementById('parsedDuplicateReviewModal')&&!document.getElementById('parsedDuplicateReviewModal').classList.contains('hidden')"
    browser.command("wait", "--fn", "(!isQuestionSaveInFlight()&&!isEditorModified())||(" + duplicate + ")")
    if browser.evaluate(duplicate):
        click(browser, "#duplicateReviewIndependentBtn")
        browser.command("wait", "--fn", "!isQuestionSaveInFlight()&&!isEditorModified()")
    # A committed save can finish before the duplicate dialog's 200ms close
    # animation. Do not click through the still-visible safety overlay.
    browser.command("wait", "--fn", "!(" + duplicate + ")")
    saved = browser.evaluate(f"fetch('/api/questions/{qid}').then(r=>r.json())")
    points = {point["code"]: point for point in saved["knowledge_points"]}
    assert set(points) == {"phy:momentum-conservation", "phy:work-energy-theorem"}
    assert (points["phy:momentum-conservation"]["role"], points["phy:momentum-conservation"]["status"]) == ("auxiliary", "suggested")
    assert (points["phy:work-energy-theorem"]["role"], points["phy:work-energy-theorem"]["status"]) == ("main", "suggested")
    assert points["phy:work-energy-theorem"]["origin"] == "ai_classification"
    assert browser.evaluate("window.__knowledgeRequests.length") == 1

    # Confirm the new suggestion explicitly in the editor, without a model call.
    click(browser, '#editKnowledgePointPicker .mb-kp-selected button:last-child')
    click(browser, '#editKnowledgePointPicker .mb-kp-menu > button:first-of-type')
    assert browser.evaluate("KnowledgePointState.snapshot().at(-1).status") == 'confirmed'
    browser.evaluate('window.__manualSave=null;saveQuestion(true).then(v=>window.__manualSave=v);true')
    browser.command('wait','--fn',"window.__manualSave!==null || (" + duplicate + ")")
    if browser.evaluate(duplicate):
        click(browser, '#duplicateReviewIndependentBtn')
    browser.command('wait','--fn',"window.__manualSave===true&&!isQuestionSaveInFlight()")
    browser.command("wait", "--fn", "!(" + duplicate + ")")
    assert browser.evaluate(f"fetch('/api/questions/{qid}').then(r=>r.json()).then(q=>q.knowledge_points.at(-1).status)") == 'confirmed'
    assert browser.evaluate("window.__knowledgeRequests.length") == 1

    # The same point array survives a document card and the real save endpoint.
    browser.evaluate(r"""(()=>{
      window.fetch=window.__knowledgeOriginalFetch;closeQuestionEditorModal();selectWorkspace('import','导入中心');
      replaceParsedQuestions([{content:'物理关系导入合成回归，视口'+innerWidth,answer_markdown:'',
        question_type:'detailed_answer',difficulty:'normal',category_compulsory:'选择性必修第一册',
        category_chapter:'第一章 动量守恒定律',category_knowledge:'动量',image_paths:[],
        knowledge_points:[{code:'phy:work-energy-theorem',name:'动能定理',role:'main',status:'suggested',
          origin:'ai_classification',evidence_source:'content',evidence:'物理关系',reason:'分类依据。'}]}]);
      renderParsedQuestionsList(parsedQuestionsData);
      document.getElementById('importPlaceholder').classList.add('hidden');
      document.getElementById('parsedQuestionsWrapper').classList.remove('hidden');return true;
    })()""")
    assert browser.evaluate("document.querySelector('#parsed-card-0 .card-knowledge-points').textContent.includes('动能定理')")
    assert "待确认" in browser.evaluate("document.querySelector('#parsed-card-0 .card-knowledge-points').textContent")
    browser.command("scrollintoview", "#parsed-card-0 .card-knowledge-points")
    browser.settle()
    browser.command("screenshot", str(EVIDENCE / f"import-card-{width}.png"))
    click(browser, '#parsed-card-0 .card-knowledge-points button:first-of-type')
    assert browser.evaluate('parsedQuestionsData[0].knowledge_points[0].status') == 'confirmed'
    assert browser.evaluate('window.__knowledgeRequests.length') == 1
    click(browser, "#parsed-card-0 .card-save-btn")
    browser.command("wait", "--fn", "parsedQuestionsData[0].saved===true||(" + duplicate + ")")
    if browser.evaluate(duplicate):
        click(browser, "#duplicateReviewIndependentBtn")
    browser.command("wait", "--fn", "parsedQuestionsData[0].saved===true")
    assert browser.evaluate("parsedQuestionsData[0].knowledge_points[0].code") == "phy:work-energy-theorem"
    assert browser.evaluate("JSON.stringify(parsedQuestionsData[0].savedSnapshot).includes('phy:work-energy-theorem')")


def test_edit_during_classification_rejects_late_points(browser):
    browser.command("reload")
    browser.command("wait", "--fn", "typeof window.runAIClassify==='function'")
    browser.evaluate("selectWorkspace('bank','题库管理');openNewQuestionEditor();true")
    browser.command("wait", "--fn", "!questionDetailLoading&&!isQuestionSaveInFlight()")
    browser.evaluate(r"""(()=>{
      document.getElementById('editContent').value='原始集合题';
      openClassifyModal();window.__lateKnowledgeOriginalFetch=window.fetch;
      window.fetch=(url,options)=>String(url).endsWith('/api/ai/classify')
        ?new Promise(resolve=>window.__resolveKnowledge=resolve):window.__lateKnowledgeOriginalFetch(url,options);
      runAIClassify();document.getElementById('editContent').value='请求期间改过的题干';
      window.__resolveKnowledge(new Response(JSON.stringify({status:'success',compulsory:'选择性必修第一册',
        chapter:'第一章 动量守恒定律',knowledge:'',question_form:'detailed_answer',
        knowledge_points:[{code:'phy:work-energy-theorem',role:'main',status:'confirmed'}]}),{status:200}));return true;
    })()""")
    browser.command("wait", "--fn", "document.getElementById('classifyLoading').classList.contains('hidden')")
    assert browser.evaluate("KnowledgePointState.snapshot().length") == 0
    assert browser.evaluate("document.getElementById('classifyResult').classList.contains('hidden')")
    browser.evaluate("window.fetch=window.__lateKnowledgeOriginalFetch;closeClassifyModal();true")
