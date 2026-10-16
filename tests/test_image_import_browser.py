"""Image entry with real clipboard/drop/upload DOM and deterministic AI replies."""
import json
from pathlib import Path

from PIL import Image
import pytest
from test_preview_browser import browser, complete_import_fixture_categories, pytestmark  # noqa: F401


@pytest.fixture
def entry(browser, tmp_path):
    browser.evaluate("""(() => {
        if(window.__imageEntryOriginalFetch)window.fetch=window.__imageEntryOriginalFetch;
        finishCloseQuestionEditorModal();startNewQuestionWithoutPrompt();
        selectWorkspace('import','导入中心'); resetImportState(false);PhysicsBankImageImport.reset();
        PhysicsBankImageImport.select(true);
        window.__imageEntryOriginalFetch=window.fetch;window.__imageEntryRequests=[];
        window.fetch=async (input,options={})=>{
            const url=String(input);
            if(url==='/api/ocr'){
                __imageEntryRequests.push({url,file:options.body.get('file').name,skip:options.body.get('skip_tikz')});
                return new Response(JSON.stringify({status:'success',latex:'图片入口回归：电流为 $3\\\\,mA$，方向向右。',
                    confidence:.99,image_path:'/static/uploads/entry-source.png',illustrations:[]}),{status:200});
            }
            if(url==='/api/upload/image-task'){
                __imageEntryRequests.push({url,files:options.body.getAll('files').map(f=>f.name),generate:options.body.get('generate_answers'),title:options.body.get('paper_title')});
                return new Response(JSON.stringify({status:'success',task_id:'image-entry-task'}),{status:200});
            }
            if(url==='/api/tasks/image-entry-task/status')return new Response(JSON.stringify({status:'completed',progress:100,
                data:[{content:'图片拆题回归：求加速度。',question_type:'detailed_answer',difficulty:'normal',answer_markdown:'',image_paths:[]}],
                page_images:['/static/uploads/entry-source.png'],page_numbers:[1],diagnostics:{},generate_answers:false}),{status:200});
            if(url.startsWith('/api/tasks/image-entry-task/'))return new Response(JSON.stringify({status:'success'}),{status:200});
            if(url.startsWith('/api/ai/') || url.startsWith('/api/upload/pdf-task') || url.startsWith('/api/upload/docx-task'))throw Error('Unexpected model or task request: '+url);
            return __imageEntryOriginalFetch(input,options);
        };return true;
    })()""")
    Image.new("RGB", (80, 40), "navy").save(browser.root / 'static/uploads/entry-source.png')
    files = []
    for index, color in enumerate(('red', 'blue')):
        path = tmp_path / f'page-{index + 1}.png'
        Image.new("RGB", (80, 40), color).save(path)
        files.append(path)
    yield browser, files
    browser.evaluate("if(window.__imageEntryOriginalFetch)window.fetch=__imageEntryOriginalFetch; finishCloseQuestionEditorModal();startNewQuestionWithoutPrompt();resetImportState(false);PhysicsBankImageImport.reset();true")


def _clipboard_or_drop(browser, name, *, drop=False, zone='importImageDropzone'):
    return browser.evaluate("""(async()=>{
        const blob=await __imageEntryOriginalFetch('/static/uploads/entry-source.png').then(r=>r.blob());
        const data=new DataTransfer();data.items.add(new File([blob],%s,{type:'image/png'}));
        const event=%s;
        %s.dispatchEvent(event); return event.defaultPrevented;
    })()""" % (json.dumps(name),
        "new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:data})" if drop else "new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:data})",
        'document.getElementById('+json.dumps(zone)+')'))


@pytest.mark.parametrize('viewport', [(1600, 1100), (375, 812)])
def test_upload_paste_drop_sort_and_mode_preservation(entry, viewport, tmp_path):
    browser, files = entry
    browser.command('set', 'viewport', *map(str, viewport))
    try:
        browser.command('upload', '#importImageFiles', str(files[0]))
        assert browser.evaluate('__imageEntryRequests.length') == 0
        assert _clipboard_or_drop(browser, 'pasted.png')
        assert browser.evaluate("PhysicsBankImageImport.filesForSplit().map(f=>f.name)") == [files[0].name, 'pasted.png']
        browser.command('scrollintoview', '#importImageList li:nth-child(2) button:first-child')
        browser.settle()
        browser.command('click', '#importImageList li:nth-child(2) button:first-child')
        assert browser.evaluate("PhysicsBankImageImport.filesForSplit().map(f=>f.name)") == ['pasted.png', files[0].name]
        browser.command('scrollintoview', '#importImageList li:nth-child(2) button:last-child')
        browser.settle()
        browser.command('click', '#importImageList li:nth-child(2) button:last-child')
        assert _clipboard_or_drop(browser, 'dropped.png', drop=True)
        assert browser.evaluate('PhysicsBankImageImport.filesForSplit().map(f=>f.name)') == ['pasted.png', 'dropped.png']
        browser.command('scrollintoview', '#importDocumentMode')
        browser.settle()
        browser.command('click', '#importDocumentMode')
        assert browser.evaluate("document.getElementById('texDropzone').checkVisibility() && !document.getElementById('importImagePanel').checkVisibility()")
        # Images dropped on the original file box also lead to the image workflow.
        assert _clipboard_or_drop(browser, 'on-file-box.png', drop=True, zone='texDropzone')
        assert browser.evaluate('PhysicsBankImageImport.filesForSplit().length') == 3
        metrics = browser.evaluate("""(()=>{const p=document.getElementById('importInputPane');return{
            overflow:p.scrollWidth>p.clientWidth+1,touch:[...document.querySelectorAll('#importImagePanel button')].every(b=>b.getBoundingClientRect().height>=44),
            requests:__imageEntryRequests.length};})()""")
        assert metrics == {'overflow': False, 'touch': True, 'requests': 0}
        browser.command('scrollintoview', '#importImageDropzone')
        browser.command('screenshot', str(tmp_path / f'image-import-{viewport[0]}.png'))
    finally:
        browser.command('set', 'viewport', '1600', '1100')


def test_single_screenshot_opens_existing_editor_and_saves_normally(entry):
    browser, files = entry
    browser.command('upload', '#importImageFiles', str(files[0]))
    browser.command('fill', '#importPaperTitle', '截图录题来源')
    browser.command('scrollintoview', '#runParseBtn')
    browser.command('click', '#runParseBtn')
    browser.command('wait', '--fn', "!document.getElementById('editorSection').classList.contains('hidden') && document.getElementById('editContent').value.includes('图片入口回归')")
    assert browser.evaluate('__imageEntryRequests') == [{'url': '/api/ocr', 'file': files[0].name, 'skip': 'true'}]
    assert browser.evaluate("document.getElementById('editSource').value") == '截图录题来源'
    assert browser.evaluate("!document.getElementById('contentTabContent-ocr').classList.contains('hidden')")
    browser.evaluate("""(()=>{
        const comp=document.getElementById('editCompulsory');comp.value=Object.keys(categoryTree)[0];comp.dispatchEvent(new Event('change'));
        const chapter=document.getElementById('editChapter');chapter.value=Object.keys(categoryTree[comp.value])[0];chapter.dispatchEvent(new Event('change'));return true;
    })()""")
    assert browser.evaluate('saveQuestion(true)') is True
    stored = browser.evaluate("fetch('/api/questions/'+EditorState.questionId).then(r=>r.json())")
    assert stored['source'] == '截图录题来源' and '图片入口回归' in stored['content']


def test_screenshot_entry_cannot_overwrite_cancelled_unsaved_editor(entry):
    browser, files = entry
    browser.command('upload', '#importImageFiles', str(files[0]))
    browser.evaluate("document.getElementById('editContent').value='尚未保存的旧题';document.getElementById('editContent').dispatchEvent(new Event('input'));true")
    browser.command('scrollintoview', '#runParseBtn')
    browser.command('click', '#runParseBtn')
    browser.command('wait', '--fn', "!!document.getElementById('unsavedChangesModalTitle')")
    browser.command('click', '#cancelBtn')
    assert browser.evaluate("document.getElementById('editContent').value") == '尚未保存的旧题'
    assert browser.evaluate('__imageEntryRequests') == []
    assert browser.evaluate("document.querySelectorAll('#importImageList li').length") == 1


def test_multiple_images_keep_order_and_use_shared_review_without_auto_save(entry):
    browser, files = entry
    browser.command('upload', '#importImageFiles', *map(str, files))
    browser.command('fill', '#importPaperTitle', '按页序导入的图片题目')
    browser.command('click', '#importImageList li:nth-child(2) button:first-child')
    before = browser.evaluate("fetch('/api/questions').then(r=>r.json()).then(q=>q.length)")
    browser.command('scrollintoview', '#runParseBtn')
    browser.command('click', '#runParseBtn')
    browser.command('wait', '--fn', "!!document.getElementById('parsed-card-0') && !document.getElementById('parsedQuestionsWrapper').classList.contains('hidden')")
    assert browser.evaluate('__imageEntryRequests') == [{'url': '/api/upload/image-task', 'files': [files[1].name, files[0].name], 'generate': 'false', 'title': '按页序导入的图片题目'}]
    assert browser.evaluate("fetch('/api/questions').then(r=>r.json()).then(q=>q.length)") == before
    assert browser.evaluate('pdfPageNumbers') == [1]
    complete_import_fixture_categories(browser, 0)
    assert browser.evaluate('saveParsedQuestion(0)') is True
    assert browser.evaluate("fetch('/api/questions').then(r=>r.json()).then(q=>q.length)") == before + 1


def test_invalid_and_overlimit_images_leave_selected_pages_untouched(entry):
    browser, files = entry
    browser.command('upload', '#importImageFiles', str(files[0]))
    checks = browser.evaluate("""(()=>{
        const invalid=new File(['x'],'bad.svg',{type:'image/svg+xml'});
        const many=Array.from({length:20},()=>new File(['x'],'page.png',{type:'image/png'}));
        return [PhysicsBankImageImport.addFiles([invalid]),PhysicsBankImageImport.addFiles(many),document.querySelectorAll('#importImageList li').length,__imageEntryRequests.length];
    })()""")
    assert checks == [False, False, 1, 0]
