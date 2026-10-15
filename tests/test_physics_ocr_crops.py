"""Physics screenshot crops: real pixels, HTTP persistence, no paid requests."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from mathbank.ocr_illustrations import parse_single_ocr_response, materialize_ocr_illustrations


def source_image():
    image = Image.new('RGB', (1000, 600), 'white')
    draw = ImageDraw.Draw(image)
    # Circuit leads/polarity and an independent force/axis diagram.
    draw.line((60, 90, 210, 90, 210, 210, 60, 210, 60, 90), fill='black', width=2)
    draw.text((55, 65), '+  -  R1 / mA', fill='black')
    draw.line((550, 330, 720, 330), fill='navy', width=2)
    draw.line((550, 330, 550, 240), fill='navy', width=2)
    draw.text((560, 245), 'F / mN, -2.00', fill='navy')
    return image


def response_data():
    return {'markdown': r'电流 $i=-2.00\,\mathrm{mA}$，电压 $U=3.0\,\mathrm{kV}$。'
            r'\begin{choices}\item [插图待补: 图1]\item [插图待补: 图2]\end{choices}',
            'figures': [
                {'slot': '图1', 'bbox': {'left': 40, 'top': 80, 'right': 240, 'bottom': 380}},
                {'slot': '图2', 'bbox': {'left': 530, 'top': 370, 'right': 750, 'bottom': 580}},
            ]}


def test_physics_crops_preserve_circuit_polarity_axes_units_signs_and_source_pixels(tmp_path):
    image = source_image()
    result = materialize_ocr_illustrations(parse_single_ocr_response(response_data()), image,
        skip_tikz=True, upload_root=tmp_path, url_prefix='static/uploads',
        draw=lambda *_: pytest.fail('raw crop must not redraw'),
        compile_tikz=lambda *_: pytest.fail('raw crop needs no TeX'))
    assert r'$i=-2.00\,\mathrm{mA}$' in result['markdown']
    assert r'$U=3.0\,\mathrm{kV}$' in result['markdown']
    assert result['markdown'].count(r'\item ![](') == 2
    for item in result['illustrations']:
        box = item['bbox']
        pixels = (int(box['left']), int(box['top'] * .6), int(box['right']), int(box['bottom'] * .6))
        with Image.open(tmp_path / Path(item['image_path']).name) as crop:
            assert crop.tobytes() == image.crop(pixels).tobytes()


@pytest.fixture
def ocr_setup(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, 'UPLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(main, 'UPLOAD_DIR_REL', 'static/test_uploads')
    provider = SimpleNamespace(api_key='fixture-only', provider_label='Fixture',
        model_name='fixture-vision', credential_label='FIXTURE')
    monkeypatch.setattr(main, 'resolve_ocr_provider', lambda _: provider)
    call = Mock(return_value=json.dumps(response_data(), ensure_ascii=False))
    monkeypatch.setattr(main, 'ocr_via_provider', call)
    draw = Mock(side_effect=AssertionError('unexpected paid drawing'))
    monkeypatch.setattr(main, 'draw_tikz_via_high_model', draw)
    buffer = io.BytesIO()
    source_image().save(buffer, format='PNG')
    return main, call, draw, buffer.getvalue(), tmp_path


def recognize(client, setup):
    main, _, _, raw, _ = setup
    return client.post('/api/ocr', data={'engine': 'siliconflow', 'skip_tikz': 'true'},
        files={'file': ('physics.png', raw, 'image/png')}, headers={'X-Local-Token': main.LOCAL_TOKEN})


def test_single_ocr_http_crops_and_saves_original_positions_and_image_lifecycle(client, ocr_setup):
    main, call, draw, _, root = ocr_setup
    reply = recognize(client, ocr_setup)
    assert reply.status_code == 200, reply.text
    data = reply.json()
    call.assert_called_once()
    assert call.call_args.kwargs == {'include_illustration_box': True}
    draw.assert_not_called()
    assert len(data['illustrations']) == 2
    assert data['illustration_review'] == {'status': 'manual_required', 'visual_calls': 0}
    assert all(item['review']['status'] == 'manual_required' for item in data['illustrations'])
    assert data['tikz_assets'] == []
    paths = [item['image_path'] for item in data['illustrations']]
    assert data['image_path'] not in data['latex']
    with Image.open(root / Path(data['image_path']).name) as image:
        assert image.size == (1000, 600)  # No auto-trim losing faint diagram edges.
    save = client.post('/api/questions', data={
        'content': data['latex'], 'question_type': 'single_choice', 'difficulty': 'medium',
        'category_compulsory': '必修第三册', 'category_chapter': '恒定电流',
        'image_paths': json.dumps(paths), 'image_layouts': json.dumps(data['image_layouts']),
    }, headers={'X-Local-Token': main.LOCAL_TOKEN})
    assert save.status_code == 200, save.text
    detail = client.get('/api/questions/' + str(save.json()['question']['id'])).json()
    assert detail['content'] == data['latex']
    assert detail['content'].count(r'\item ![](') == 2
    assert set(detail['image_paths']) == set(paths)
    assert len(detail['image_layouts']) == 2
    assert all((root / Path(path).name).is_file() for path in paths)


def test_invalid_figure_json_keeps_text_and_manual_repair_without_second_request(client, ocr_setup):
    _, call, draw, _, _ = ocr_setup
    call.return_value = '{"markdown":"电路图[插图待补: 图1]","figures":BROKEN}'
    data = recognize(client, ocr_setup).json()
    assert data['status'] == 'success'
    assert data['latex'] == '电路图[插图待补: 图1]'
    assert data['warnings'] and data['illustrations'][0]['status'] == 'unresolved'
    call.assert_called_once()
    draw.assert_not_called()


def test_failed_normalization_rolls_back_only_new_original_and_crops(client, ocr_setup, monkeypatch):
    main, _, _, _, root = ocr_setup
    existing = root / 'existing.png'
    Image.new('RGB', (8, 8), 'red').save(existing)
    monkeypatch.setattr(main, 'normalize_fillin_macro', Mock(side_effect=ValueError('fixture failure')))
    assert recognize(client, ocr_setup).status_code == 500
    assert list(root.iterdir()) == [existing]


@pytest.mark.parametrize('finish', ['length', 'content_filter', 'tool_calls'])
def test_incomplete_single_ocr_is_rejected_once_without_paid_retry(tmp_path, monkeypatch, finish):
    import main
    from mathbank.ai_providers import resolve_ocr_provider
    provider = resolve_ocr_provider('siliconflow', {'SILICONFLOW_API_KEY': 'fixture-only'})
    path = tmp_path / 'input.png'
    source_image().save(path)
    response = SimpleNamespace(status_code=200, json=lambda: {'choices': [
        {'finish_reason': finish, 'message': {'content': json.dumps(response_data())}}]})
    post = Mock(return_value=response)
    monkeypatch.setattr(main, 'post_chat_completion', post)
    with pytest.raises(RuntimeError, match='未完整结束'):
        main.ocr_via_provider(str(path), provider, include_illustration_box=True)
    post.assert_called_once()
    assert post.call_args.kwargs['retry_connection'] is False
    payload = post.call_args.args[1]
    assert payload['messages'][0]['role'] == 'system'
    assert '电路连接' in payload['messages'][1]['content'][0]['text']


def test_pdf_ocr_keeps_plain_text_protocol(tmp_path, monkeypatch):
    import main
    from mathbank.ai_providers import resolve_ocr_provider
    path = tmp_path / 'pdf.png'
    source_image().save(path)
    provider = resolve_ocr_provider('siliconflow', {'SILICONFLOW_API_KEY': 'fixture-only'})
    post = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: {
        'choices': [{'message': {'content': '原生物理题 $F=ma$'}}]}))
    monkeypatch.setattr(main, 'post_chat_completion', post)
    assert main.ocr_via_provider(str(path), provider) == '原生物理题 $F=ma$'
    payload = post.call_args.args[1]
    assert len(payload['messages']) == 1
    assert '单题图文协议' not in payload['messages'][0]['content'][0]['text']
