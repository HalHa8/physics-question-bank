"""Real private PDF transcript witnesses: integrity is never math truth."""
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import json,re

from PIL import Image
import pytest

from mathbank.ai_providers import resolve_text_provider
from mathbank.pdf_layout import apply_figure_anchors
from mathbank.pdf_figures import clear_resolved_figure_placeholders
from mathbank.pdf_transcription_scopes import (
    begin_pdf_transcription_witness, finish_pdf_transcription_witness,
    finalize_pdf_transcription_snapshot, verify_pdf_transcription_snapshot,
)
from mathbank.pdf_hybrid_plan import (
    PdfHybridPlanError, build_pdf_snapshot_hybrid_plan,
    require_pdf_hybrid_plan, require_pdf_snapshot_hybrid_plan,
)
from mathbank.pdf_hybrid_request import request_pdf_hybrid
from mathbank.source_metadata import SourceMetadataContractError
from mathbank.task_manager import TaskCancelled

CURRICULUM={'必修一':{'3. 函数的概念与性质':[]}}
FIELDS={'question_type':'detailed_answer','category_compulsory':'必修一',
        'category_chapter':'3. 函数的概念与性质','difficulty':'normal'}
PROVIDER=resolve_text_provider('SILICONFLOW/Qwen/test-model',{'SILICONFLOW_API_KEY':'fake-key-no-network'})


def raster(path,color='red'):
    data=BytesIO();Image.new('RGB',(8,8),color).save(data,format='PNG');path.write_bytes(data.getvalue())


def prepared(tmp_path,*,risk=True,with_figure=False,shared=False):
    # These are deliberate test machine transcripts of tiny color rasters.
    # No fixture claims raster/transcript mathematical equivalence.
    texts=['一、解答题\n1. 甲题如图，已知$x=99$。\n【答案】$99$。原始代码`[EXTRACTED_ORIGINAL]`。',
           '2. 乙题已知$y=2$，求$y+y$。\n【解析】原乙题答案$4$。',
           '3. 丙题已知$z=3$，求$z+z$。\n【解析】原丙题答案$6$。']
    if shared:texts[2]=texts[2].replace('丙题已知','根据第1题中的函数，丙题已知')
    pages=[];layout=[];witnesses={};image_paths=[];figures={};figure_url='/static/uploads/tmp/source_figure.png'
    for index,text in enumerate(texts):
        image=tmp_path/f'page-{index}.png';raster(image);image_paths.append(image)
        info={'page_index':index,'width':8,'height':8}
        before=begin_pdf_transcription_witness(image,info)
        result={'markdown':text,'layout':{'page_complete':not(risk and index==1),
                                        'native_reliable':True,'source_math_verified':True}}
        state={'page_index':index,'page_number':index+1,'status':'checked','warnings':[], 'figures':[]}
        if with_figure and index==0:
            figure=tmp_path/'figure.png';raster(figure,'blue');figures[figure_url]=str(figure)
            state['figures']=[{'id':'local-F1','slot_id':'slot-F1','page_index':index,'bbox':[100,100,400,400],
                'image_path':figure_url,'attached':True,'review_reasons':[],'review_required':False,
                'anchor_before':'已知$x=99$。','anchor_after':'【答案】$99$。'}]
        result['layout']['figures'] = deepcopy(state['figures'])
        witnesses[index]=finish_pdf_transcription_witness(before,result)
        marked=f'<!-- MATHBANK_PDF_PAGE:{index+1} -->\n'+text
        attached=apply_figure_anchors(marked,state['figures'])
        marked=clear_resolved_figure_placeholders(attached['markdown'],state['figures'])
        pages.append({'page_number':index+1,'origin':'joint_vision','markdown':marked})
        layout.append(state)
    source='\n\n'.join(re.sub(r'<!-- MATHBANK_PDF_PAGE:\d+ -->','',page['markdown']) for page in pages)
    diagnostics={'pdf_extraction':'joint_vision','pdf_native_quality':[{'reason':'unverified native glyphs remain unverified'}]}
    evidence=finalize_pdf_transcription_snapshot(source,diagnostics,source_document_sha256='a'*64,
        source_pages=pages,layout_result={'pages':layout},witnesses=witnesses,
        transcript_normalizer=lambda x:x,figure_assets=figures)
    assert evidence is not None
    plan=build_pdf_snapshot_hybrid_plan(source,diagnostics,source_pages=pages,layout_result={'pages':layout},
        task_id='pdf-integrity-test',generation=2,source_document_sha256='a'*64,
        source_review_evidence=evidence,min_metadata_source_characters=0)
    assert plan['mode'] in {'hybrid','whole_metadata'},plan['global_reasons']
    return plan,image_paths,figures


def response_for(plan,payload):
    data=json.loads(payload['messages'][1]['content']);original={q['id']:q for q in plan['_inspection']['questions']}
    splits=[]
    for group in data['split_groups']:
        rows=[]
        for qid in group['source_ids']:
            q=original[qid];rows.append({'source_id':qid,**FIELDS,'content':q['content'],
                'answer_markdown':'[EXTRACTED_ORIGINAL]'+q['answer_markdown'] if q['answer_markdown'] else '',
                'source':'','referenced_images':[]})
        splits.append({'group_id':group['group_id'],'questions':rows})
    return {'metadata':{'items':[{'id':item['id'],**FIELDS} for item in data['metadata_items']]},'splits':splits}


class Response:
    status_code=200
    def __init__(self,content):self.content=content
    def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.content,ensure_ascii=False)}}],
        'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}


def run(plan,post,*,fallback=lambda:pytest.fail('Unexpected whole retry'),cancel=lambda:None):
    diagnostics={};result=request_pdf_hybrid(plan,CURRICULUM,provider=PROVIDER,post=post,diagnostics=diagnostics,
        normalize_fillin=lambda x:x,full_source_fallback=fallback,task_id='pdf-integrity-test',generation=2,check_cancelled=cancel)
    return result,diagnostics
