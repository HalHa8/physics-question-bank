"""Original physics crops survive actual Word/PDF export without redrawing."""

from io import BytesIO
import os
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw
import pytest

from mathbank.ocr_illustrations import parse_single_ocr_response, materialize_ocr_illustrations
from mathbank.paper_helper import build_latex_document, compile_tex_to_pdf
from mathbank.word_export_helper import build_word_document


def crop_question(tmp_path):
    source = Image.new('RGB', (1000, 600), 'white')
    draw = ImageDraw.Draw(source)
    figures = []
    for index, color in enumerate(('navy', 'green', 'maroon', 'purple', 'teal')):
        x = index * 190 + 20
        draw.rectangle((x, 70, x + 140, 185), outline=color, width=3)
        draw.text((x + 5, 80), '+ R / mA -', fill=color)
        figures.append({'slot': f'图{index + 1}',
            'bbox': {'left': x - 5, 'top': 100, 'right': x + 150, 'bottom': 330}})
    text = r'实验装置：\begin{tabular}{cc}装置 & [插图待补: 图5]\\ 电流单位 & mA\end{tabular}'
    text += '\n选择正确的电路连接。\\begin{choices}' + ''.join(
        r'\item [插图待补: 图' + str(i) + ']' for i in range(1, 5)) + r'\end{choices}'
    result = materialize_ocr_illustrations(parse_single_ocr_response({'markdown': text, 'figures': figures}),
        source, skip_tikz=True, upload_root=tmp_path, url_prefix='static/uploads',
        draw=lambda *_: pytest.fail('no drawing'), compile_tikz=lambda *_: pytest.fail('no TeX drawing'))
    paths = [item['image_path'] for item in result['illustrations']]
    return {'id': 1510, 'question_type': 'single_choice', 'content': result['markdown'],
        'image_paths': paths, 'image_layouts': result['image_layouts'], 'figure_align': 'bottom_right'}, paths


def test_original_crop_word_media_pixels_order_and_table_anchor(tmp_path):
    from lxml import etree
    question, paths = crop_question(tmp_path)
    data, diagnostics = build_word_document('物理截图', '', 'exam', [{'question': question, 'score': 5}],
        uploads_dir=tmp_path, show_secret=False, show_notice=False)
    assert '插图待补' not in question['content']
    with zipfile.ZipFile(BytesIO(data)) as package:
        media = [name for name in package.namelist() if name.startswith('word/media/')]
        assert len(media) == 5
        xml = etree.fromstring(package.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
              'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
              'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
        relations = etree.fromstring(package.read('word/_rels/document.xml.rels'))
        by_id = {rel.get('Id'): 'word/' + rel.get('Target') for rel in relations}
        ordered_media = [by_id[blip.get('{'+ns['r']+'}embed')] for blip in xml.xpath('//a:blip', namespaces=ns)]
        assert len(ordered_media) == len(paths)
        for name, path in zip(ordered_media, paths):
            with Image.open(BytesIO(package.read(name))) as image, Image.open(tmp_path / Path(path).name) as original:
                assert image.convert('RGB').tobytes() == original.convert('RGB').tobytes()
        assert len(xml.xpath('//a:blip', namespaces=ns)) == 5
        assert len(xml.xpath('//w:tbl[.//w:t[contains(.,"装置")]]//a:blip', namespaces=ns)) == 1


@pytest.mark.skipif(os.environ.get('MATHBANK_TEST_TIKZ_NATIVE') != '1', reason='opt-in native XeLaTeX')
@pytest.mark.parametrize('paper_type', ['exam', 'quiz'])
def test_native_physics_original_crops_are_complete_and_within_pdf_pages(tmp_path, paper_type):
    import pymupdf as fitz
    question, paths = crop_question(tmp_path)
    tex = build_latex_document('物理原图裁剪验收', '', paper_type, [{'question': question, 'score': 5}],
        show_secret=False, show_notice=False)
    positions = [tex.index(Path(path).name) for path in paths]
    assert positions == sorted(positions)
    pdf, diagnostic = compile_tex_to_pdf(tex, [str(tmp_path / Path(path).name) for path in paths])
    assert pdf, diagnostic
    with fitz.open(stream=pdf, filetype='pdf') as document:
        images = [(page, image) for page in document for image in page.get_image_info()]
        assert len(images) == 5
        for page, image in images:
            box = fitz.Rect(image['bbox'])
            assert 0 <= box.x0 < box.x1 <= page.rect.width
            assert 0 <= box.y0 < box.y1 <= page.rect.height
            assert image['width'] == 155 and image['height'] == 138
