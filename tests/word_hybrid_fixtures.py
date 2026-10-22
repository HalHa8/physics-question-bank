"""Independent mixed-Word contract checks: real native evidence, no paid HTTP."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from xml.sax.saxutils import escape
import zipfile

from PIL import Image

import pytest

from mathbank.ai_providers import resolve_text_provider
from mathbank.content_locks import _formulas
from mathbank.docx_helper import extract_docx_markdown
from mathbank.source_metadata import SourceMetadataContractError
from mathbank.question_assets import embedded_question_assets
from mathbank.task_manager import TaskCancelled
from mathbank.word_hybrid_plan import WordHybridPlanError, build_word_hybrid_plan
from mathbank.word_hybrid_request import request_word_hybrid

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
CURRICULUM = {"必修一": {"1. 集合与常用逻辑用语": [], "3. 函数的概念与性质": []}}
FIELDS = {"question_type": "detailed_answer", "category_compulsory": "必修一",
          "category_chapter": "3. 函数的概念与性质", "difficulty": "normal"}
PROVIDER = resolve_text_provider("SILICONFLOW/Qwen/test-model", {"SILICONFLOW_API_KEY": "isolated-fake-key"})


def paragraph(value):
    return '<w:p><w:r><w:t>' + escape(value) + '</w:t></w:r></w:p>'


def bad_question(number):
    return (f'<w:p><w:r><w:t>{number}. 比较未知式并求函数值：</w:t></w:r>'
            '<m:oMath><m:unknownSafetyFixture><m:r><m:t>x+1</m:t></m:r>'
            '</m:unknownSafetyFixture></m:oMath></w:p>')


def native_plan(tmp_path, *, two_bad=False, shared=False, with_image=False):
    body = paragraph('一、解答题')
    body += paragraph(r'1. 设$f(x)=x^2$，求$f(3)$。阅读代码`x___`和$\underline{AB}$，两个公式不能省略。')
    if with_image:
        body += '<w:p><w:r><w:pict><v:shape><v:imagedata r:id="img"/></v:shape></w:pict></w:r></w:p>'
    body += paragraph('【解析】$f(3)=9$。原始代码`[EXTRACTED_ORIGINAL]`必须保留。')
    body += bad_question(2)
    body += paragraph('【解析】这是原题二的独立解法；应保留原始未知式，不能生成新解法。')
    body += paragraph(r'3. 设集合$A=\{1,2,3\}$，求其元素个数。')
    body += paragraph('【解析】$3$，这是原题三的原答案。')
    if two_bad:
        body += bad_question(4) + paragraph('【解析】这是原题四的原答案。')
        body += paragraph('5. 已知$x=5$，求$x+x$。') + paragraph('【解析】$10$。')
    if shared:
        body = body.replace('3. 设集合', '3. 根据第2题中的函数，设集合')
    data = BytesIO()
    with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        archive.writestr('word/document.xml', f'<w:document xmlns:w="{W}" xmlns:m="{M}" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{body}</w:body></w:document>')
        if with_image:
            pixels = BytesIO(); Image.new('RGB', (8,8), 'red').save(pixels, format='PNG')
            archive.writestr('word/media/figure.png', pixels.getvalue())
            archive.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="img" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/figure.png"/></Relationships>')
    blob = data.getvalue()
    native = extract_docx_markdown(blob, output_dir=tmp_path, include_source_asset_evidence=True,
                                   include_source_review_evidence=True)
    assert native['success']
    plan = build_word_hybrid_plan(native['markdown'], native['diagnostics'], task_id='independent-hybrid',
        generation=3, source_document_sha256=hashlib.sha256(blob).hexdigest(),
        source_review_evidence=native['_source_review_evidence'], asset_evidence=native['_source_asset_evidence'],
        min_metadata_source_characters=0)
    assert plan['mode'] == 'hybrid', plan['global_reasons']
    return plan


def reply_for(plan, payload):
    """A fixture response includes original bodies only for requested risky IDs."""
    envelope = json.loads(payload['messages'][1]['content'])
    by_id = {q['id']: q for q in plan['_inspection']['questions']}
    meta = [{'id': item['id'], **FIELDS} for item in envelope['metadata_items']]
    splits = []
    for group in envelope['split_groups']:
        rows = []
        for qid in group['source_ids']:
            source = by_id[qid]
            rows.append({'source_id': qid, **FIELDS, 'content': source['content'],
                'answer_markdown': '[EXTRACTED_ORIGINAL]' + source['answer_markdown'] if source['answer_markdown'] else '',
                'source': '', 'referenced_images': embedded_question_assets(source['content'], source['answer_markdown'])})
        splits.append({'group_id': group['group_id'], 'questions': rows})
    return {'metadata': {'items': meta}, 'splits': splits}


class Response:
    status_code = 200

    def __init__(self, parsed, *, status_code=200):
        self.parsed = parsed
        self.status_code = status_code

    def json(self):
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(self.parsed, ensure_ascii=False)}}],
                'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30}}


def call(plan, post, *, fallback=lambda: pytest.fail('Unexpected whole-source fallback'), check_cancelled=lambda: None):
    diagnostics = {}
    result = request_word_hybrid(plan, CURRICULUM, provider=PROVIDER, post=post, diagnostics=diagnostics,
        normalize_fillin=lambda value: value, full_source_fallback=fallback,
        task_id='independent-hybrid', generation=3, check_cancelled=check_cancelled)
    return result, diagnostics
