"""Execute the shipped import-correction state transitions without AI/network."""

from pathlib import Path
import shutil
import subprocess

import pytest

from test_import_source_review import review_script


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def correction_script(review_script):
    base = review_script.rsplit("scenarios[process.argv[1]]", 1)[0]
    source = (ROOT / "static/js/import.js").read_text(encoding="utf-8")
    start = source.index("function submitPdfCropCoordinates()")
    crop = source[start:source.index("function performOrphanedTempCropsCleanup", start)]
    start = source.index("function renderParsedCardPreview(")
    preview = "const actualPreview = " + source[start:source.index("function validateParsedQuestionBeforeImport", start)] + ";"
    setup = r"""
Element.prototype.setSelectionRange=function(start,end){this.selection=[start,end];};
Element.prototype.append=function(...items){items.forEach(item=>this.appendChild(item));};
Element.prototype.setAttribute=function(name,value){this[name]=value;};
document.body=root;
const prompts=[];
let modalOptions=null,modalCloses=0;
window.MathBankModal={open(modal,options){prompts.push(allText(modal));modalOptions=options;},close(){modalCloses++;}};
const dismissCorrection=accept=>document.getElementById(accept?'parsedIncompleteContinue':'parsedIncompleteBack').onclick();
let rectLeft=10,rectTop=10,rectWidth=30,rectHeight=30,activePageIndex=0;
const originalPdfPageNumber=index=>window.pdfPageNumbers?.[index]||index+1;
const closePdfCropModal=()=>{window.activeParsedCropContext=null;};
for(const id of ['pdfCropActiveImage','pdfCropImageContainer','pdfCropConfirmBtn'])create(id);
document.getElementById('pdfCropImageContainer').getBoundingClientRect=()=>({width:100,height:100});
const image='/static/uploads/tmp/a.png',other='/static/uploads/tmp/b.png';
function question(content='力的示意图 [插图待补: 图1]') {
  return {content,answer_markdown:'',image_paths:[]};
}
function imageQuestion() {
  return {content:`题干 ![图](${image})`,answer_markdown:`解析 ![图](${image})`,image_paths:[image,other],
    content_tikz_assets:[{id:'a',image_path:image,reference_image_path:other,tikz_code:'draw'}],
    answer_tikz_assets:[{id:'b',image_path:other,reference_image_path:image,tikz_code:'keep'}],
    tikz_code:'legacy',tikz_reference_image_path:image,image_layouts:{[image]:{align:'left'}}};
}
const allText=node=>node.textContent+' '+node.children.map(allText).join(' ');
window.MathBankSafe.sanitizeRichHtml=String;
const parseMarkdownWithMath=text=>text;
const renderMathInElement=()=>{};
const cases={
  classifications_and_code_examples() {
    const source='`[插图待补: 示例]`\n```text\n[公式待核对]\n```\n速度 [公式结构待核对：上下标] [插图待补: 图1]';
    const found=parsedContentIssues(source,'[公式待核对: 电流方向]',{required:true});
    assert.deepEqual(found.map(item=>item.kind),['formula','missing_image','formula','source']);
    assert.equal(found[0].offset,source.indexOf('[公式结构'));
    assert.equal(found[0].label,'公式转换不完整');
    const q=question(source),card=show([q]);
    assert.ok(allText(card).includes('定位并编辑公式'));
    assert.ok(allText(card).includes('上传图片补此处'));
    focusParsedCorrection(0,found[0]);
    assert.deepEqual(card.querySelector('.card-content-textarea').selection,[found[0].offset,found[0].offset+found[0].marker.length]);
  },
  review_is_optional_and_invalidates_on_edit_revert() {
    const q=pendingQuestion(),card=show([q]);
    const button=card.querySelectorAll('button').find(el=>el.textContent==='我已对照原文');
    button.onclick(); assert.ok(parsedManualReviews.has(q));
    const original=card.querySelector('.card-content-textarea').value;
    edit(card,'.card-content-textarea',original+'修改');
    edit(card,'.card-content-textarea',original);
    assert.equal(parsedManualReviews.has(q),false);
    assert.equal(q.source_review.required,true,'manual review never certifies backend source evidence');
    assert.equal(confirmParsedIncompleteImport([0]),true);
    assert.equal(prompts.length,0,'advisory source mismatches never prompt to import');
  },
  async explicit_missing_warning_can_cancel_or_continue() {
    const q=question(),card=show([q]);
    const rejected=confirmParsedIncompleteImport([0]);
    assert.ok(prompts[0].includes('保留标记继续入库'));
    assert.equal(modalOptions.initialFocus.id,'parsedIncompleteImportTitle');
    dismissCorrection(false);assert.equal(await rejected,false);
    assert.deepEqual(card.querySelector('.card-content-textarea').selection,[6,16]);
    const accepted=confirmParsedIncompleteImport([0]);dismissCorrection(true);
    assert.equal(await accepted,true);
    assert.ok(card.querySelector('.card-content-textarea').value.includes('[插图待补'));
  },
  async warning_escape_cancels_and_stale_confirmation_never_imports() {
    const q=question(),card=show([q]);
    const escaped=confirmParsedIncompleteImport([0]);
    const oldContinue=document.getElementById('parsedIncompleteContinue');
    modalOptions.onEscape();oldContinue.onclick();
    assert.equal(await escaped,false);
    assert.equal(modalCloses,1,'Esc and a stale click must finish only once');
    const stale=confirmParsedIncompleteImport([0]);
    edit(card,'.card-answer-textarea','确认期间新增解析');dismissCorrection(true);
    assert.equal(await stale,false);
    const replaced=confirmParsedIncompleteImport([0]);replaceParsedQuestions([question()]);
    dismissCorrection(true);assert.equal(await replaced,false);
    assert.equal(requests.length,0);
  },
  remove_and_undo_update_every_reference_without_disk_delete() {
    const q=imageQuestion(),card=show([q]);
    // render fixture normalizes image paths with the real safeImageUrl.
    q.image_paths=[image,other];
    const before=parsedCorrectionState(0);
    removeParsedQuestionImage(0,image);
    const after=parsedCorrectionState(0);
    assert.ok(!after.content.includes(image)); assert.ok(!after.answer_markdown.includes(image));
    assert.deepEqual(after.image_paths,[other]); assert.deepEqual(after.content_tikz_assets,[]);
    assert.equal(after.answer_tikz_assets[0].reference_image_path,'');
    assert.equal(after.answer_tikz_assets[0].tikz_code,'keep');
    assert.equal(after.tikz_reference_image_path,''); assert.deepEqual(after.image_layouts,{});
    assert.ok(parsedImageUndo.has(q)); undoParsedImageChange(0);
    assert.deepEqual(parsedCorrectionState(0),before); assert.equal(requests.length,0);
    removeParsedQuestionImage(0,image); edit(card,'.card-answer-textarea','新的人工解析');
    undoParsedImageChange(0); assert.equal(card.querySelector('.card-answer-textarea').value,'新的人工解析');
  },
  deleting_last_markdown_reference_detaches_fallback_only_when_unused() {
    const q=imageQuestion(),card=show([q]);q.image_paths=[image,other];
    edit(card,'.card-content-textarea','题干');
    assert.ok(q.image_paths.includes(image),'answer reference still owns image');
    edit(card,'.card-answer-textarea','解析');
    assert.deepEqual(q.image_paths,[other],'unanchored legacy attachment is preserved');
    assert.deepEqual(q.content_tikz_assets,[]); assert.equal(q.tikz_reference_image_path,'');
  },
  targeted_replacement_and_undo_preserve_other_missing_slots() {
    const q=question('A [插图待补: 图1] B [插图待补: 图1]');show([q]);
    const issue=parsedContentIssues(q.content,'',null)[1];
    const before=parsedCorrectionSnapshot(0);
    assert.equal(applyParsedNewImage(0,q,image,{issue},before),true);
    assert.equal(parsedCorrectionState(0).content,`A [插图待补: 图1] B ![插图](${image})`);
    undoParsedImageChange(0); assert.equal(parsedCorrectionSnapshot(0),before);
    assert.equal(applyParsedNewImage(0,q,image,{issue},'stale'),false);
  },
  recrop_replaces_both_fields_and_is_undoable() {
    const q=imageQuestion();show([q]);q.image_paths=[image,other];
    const before=parsedCorrectionState(0),newImage='/static/uploads/tmp/new.png';
    assert.equal(applyParsedNewImage(0,q,newImage,{replacePath:image},parsedCorrectionSnapshot(0)),true);
    const after=parsedCorrectionState(0);
    assert.ok(after.content.includes(newImage));assert.ok(after.answer_markdown.includes(newImage));
    assert.ok(!after.image_paths.includes(image));assert.ok(after.image_paths.includes(newImage));
    undoParsedImageChange(0);assert.deepEqual(parsedCorrectionState(0),before);
  },
  answer_only_image_does_not_reappear_in_stem() {
    const q=question('题干'),card=show([q]);q.image_paths=[image,other];
    const answer=`解析 ![图](${image})`;
    actualPreview(card,'题干',answer);
    assert.ok(!card.querySelector('.card-content-preview').innerHTML.includes(image));
    assert.ok(card.querySelector('.card-content-preview').innerHTML.includes(other),'attachment-only image still renders');
    assert.ok(card.querySelector('.card-answer-preview').innerHTML.includes(image));
  },
  deleting_last_tikz_image_clears_legacy_compatibility_fields() {
    const state=imageQuestion();state.tikz_reference_image_path=other;
    const result=removeParsedImageFromState(state,image);
    assert.deepEqual(result.content_tikz_assets,[]);
    assert.equal(result.tikz_code,'');assert.equal(result.tikz_reference_image_path,'');
  },
  async cancelled_single_and_batch_save_never_call_network() {
    show([question()]);
    const single=saveParsedQuestion(0);dismissCorrection(false);
    assert.equal(await single,false);
    const batch=saveAllParsedQuestions();modalOptions.onEscape();
    assert.equal(await batch,false);
    assert.equal(requests.length,0);
  },
  async single_and_batch_stale_modal_snapshot_never_reaches_precheck() {
    let calls=0;precheck=async()=>{calls++;return {ok:false};};
    let card=show([question()]);
    const single=saveParsedQuestion(0);
    edit(card,'.card-content-textarea','内容已被修改 [插图待补: 新图]');dismissCorrection(true);
    assert.equal(await single,false);assert.equal(calls,0);
    card=show([question(),question('第二题 [公式待核对]')]);
    const batch=saveAllParsedQuestions();
    edit(card,'.card-answer-textarea','确认期间新增答案');dismissCorrection(true);
    assert.equal(await batch,false);assert.equal(calls,0);assert.equal(requests.length,0);
  },
  async stale_crop_never_attaches_to_other_card() {
    const first=question('第一题'),second=question('第二题');show([first,second]);
    window.currentPdfTaskId='task';window.pdfPageNumbers=[5];
    const context={q:first,index:0,generation:parsedQuestionsGeneration,taskId:'task',options:{},snapshot:parsedCorrectionSnapshot(0)};
    window.activeParsedCropContext=context;
    const work=submitPdfCropCoordinates();
    window.activeParsedCropContext={q:second,index:1,generation:parsedQuestionsGeneration,taskId:'task',options:{},snapshot:parsedCorrectionSnapshot(1)};
    requests.at(-1).resolve({ok:true,json:async()=>({status:'success',image_path:image})});await work;
    assert.equal(first.content,'第一题');assert.equal(second.content,'第二题');
    assert.equal(JSON.parse(requests[0].options.body).page_index,4);
  },
  async current_crop_updates_only_captured_card() {
    const first=question('第一题'),second=question('第二题');show([first,second]);
    window.currentPdfTaskId='task';
    window.activeParsedCropContext={q:first,index:0,generation:parsedQuestionsGeneration,taskId:'task',options:{},snapshot:parsedCorrectionSnapshot(0)};
    const work=submitPdfCropCoordinates();
    window.activeCropQuestionIndex=1;
    requests.at(-1).resolve({ok:true,json:async()=>({status:'success',image_path:image})});await work;
    assert.ok(first.content.includes(image));assert.equal(second.content,'第二题');
  },
  async save_in_flight_protects_new_edits() {
    const q=imageQuestion(),card=show([q]);q.image_paths=[image,other];
    const work=saveParsedQuestion(0); await new Promise(resolve=>setImmediate(resolve));
    assert.equal(requests.length,1);
    const before=parsedCorrectionSnapshot(0);
    removeParsedQuestionImage(0,image);
    assert.equal(parsedCorrectionSnapshot(0),before,'correction buttons cannot mutate in-flight save');
    edit(card,'.card-answer-textarea','等待中编辑的解析');
    requests[0].resolve({ok:true,json:async()=>({status:'success',id:7})});
    assert.equal(await work,false);assert.equal(q.saved,false);
    assert.equal(card.querySelector('.card-answer-textarea').value,'等待中编辑的解析');
    assert.ok(toasts.some(message=>message.includes('提交版本已入库')));
  }
};
Promise.resolve(cases[process.argv[1]]()).catch(error=>{console.error(error);process.exitCode=1;});
"""
    return base + "\n" + crop + "\n" + preview + "\n" + setup


@pytest.mark.parametrize("scenario", [
    "classifications_and_code_examples", "review_is_optional_and_invalidates_on_edit_revert",
    "explicit_missing_warning_can_cancel_or_continue", "remove_and_undo_update_every_reference_without_disk_delete",
    "warning_escape_cancels_and_stale_confirmation_never_imports", "single_and_batch_stale_modal_snapshot_never_reaches_precheck",
    "deleting_last_markdown_reference_detaches_fallback_only_when_unused",
    "targeted_replacement_and_undo_preserve_other_missing_slots", "recrop_replaces_both_fields_and_is_undoable",
    "answer_only_image_does_not_reappear_in_stem", "deleting_last_tikz_image_clears_legacy_compatibility_fields",
    "cancelled_single_and_batch_save_never_call_network", "stale_crop_never_attaches_to_other_card",
    "current_crop_updates_only_captured_card", "save_in_flight_protects_new_edits",
])
def test_import_corrections(correction_script, scenario):
    node = shutil.which("node")
    assert node, "Node.js is required for executable frontend regression checks"
    result = subprocess.run([node, "-e", "eval(require('node:fs').readFileSync(0,'utf8'))", scenario],
                            input=correction_script, text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
