"""Shared preview rules agree with exports without rewriting authored content."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from mathbank.paper_image_layout import normalize_paper_image_choices

ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / 'static/js/api.js').read_text(encoding='utf-8')
HELPERS = API[API.index('window.ImageLayoutTools = {'):API.index('const FigureLayoutState = {')]
OPTIONS = '\n'.join(f'{label}．\n![](/static/uploads/{label}.png)' for label in 'ABCD')


def evaluate(source):
    node = shutil.which('node')
    assert node, 'Node.js is required for executable frontend regression tests'
    result = subprocess.run([node, '-'], input='global.window = {};\n' + HELPERS + source,
                            text=True, encoding='utf-8', capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('source,kind', [
    ('题干\n' + OPTIONS, 'single_choice'),
    ('题干\n' + OPTIONS.replace('．', '.'), 'single_choice'),
    ('题干\n' + OPTIONS.replace('．', '、'), 'multi_choice'),
    ('题干\n![](/static/uploads/stem.png)\n' + OPTIONS, 'single_choice'),
    ('题干\n' + OPTIONS, 'experiment'),
    ('题干\n' + OPTIONS.replace('C．', 'B．'), 'single_choice'),
    ('题干\n' + OPTIONS.replace('B．', 'B．有文字说明'), 'single_choice'),
    ('题干\n' + OPTIONS + '\n后续小问', 'single_choice'),
    ('题干\n' + OPTIONS.replace('D．\n![](/static/uploads/D.png)', ''), 'single_choice'),
    ('```\n' + OPTIONS + '\n```', 'single_choice'),
    ('\\begin{tabular}{c}\n' + OPTIONS, 'single_choice'),
    ('\\begin{choices}\n\\item ![](/static/uploads/A.png)\n\\end{choices}', 'single_choice'),
])
def test_shared_image_choices_match_export_rules(source, kind):
    result = evaluate(f"""
const source = {json.dumps(source)}, kind = {json.dumps(kind)};
const output = window.ImageLayoutTools.normalizeImageChoices(source, kind);
console.log(JSON.stringify({{output, source}}));
""")
    assert result['source'] == source
    assert result['output'] == normalize_paper_image_choices(source, kind)


def test_scale_sanitization_and_four_option_anchor_safety():
    source = json.dumps('题干\n' + OPTIONS)
    result = evaluate(f"""
const tools = window.ImageLayoutTools;
const content = tools.normalizeImageChoices({source}, 'single_choice');
console.log(JSON.stringify({{
    scales: [null, undefined, true, false, [], {{}}, '', 'invalid', 19, 151, 70.5,
        20, '35', 70, 150].map(value => tools.imageScale(value)),
    tail: tools.split(content).tail,
    images: tools.split(content).matches.map(match => match[1])
}}));
""")
    assert result['scales'] == [70] * 11 + [20, 35, 70, 150]
    assert result['tail'] == ''  # In particular, D cannot become a detached figure.
    assert result['images'] == [f'/static/uploads/{label}.png' for label in 'ABCD']
