"""Paper image scale regressions: persistence, safe grouping and real exports."""
from copy import deepcopy
from io import BytesIO
import os

import pytest
from PIL import Image
from docx import Document

from mathbank.paper_image_layout import normalize_image_scale, normalize_paper_image_choices
from mathbank.paper_helper import build_latex_document, compile_tex_to_pdf
from mathbank.word_export_helper import build_word_document
from mathbank.database import Question

def image_choices():
    return "选择正确的图像。\n![](/static/uploads/stem.png)\n\n" + "\n    ".join(
        f"{label}．\n![](/static/uploads/{label}.png)" for label in "ABCD"
    )

def question(scale=70):
    return dict(id=31, question_type="single_choice", content=image_choices(),
                image_paths=[f"/static/uploads/{name}.png" for name in ["stem", *"ABCD"]],
                figure_align="right", paper_image_scale=scale)

@pytest.mark.parametrize("separator", [".", "．", "、"])
def test_only_complete_image_options_are_grouped(separator):
    original = image_choices().replace("．", separator)
    normalized = normalize_paper_image_choices(original, "single_choice")
    assert normalized.count(r"\item ") == 4
    assert normalized.index("stem.png") < normalized.index(r"\begin{choices}")
    assert normalized.index("D.png") < normalized.index(r"\end{choices}")
    assert original == image_choices().replace("．", separator)

@pytest.mark.parametrize("change", [
    lambda text: text.replace("C．", "B．"),
    lambda text: text.replace("A．", "A．额外说明"),
    lambda text: text + "\n后续小问",
    lambda text: text.replace("C．\n", ""),
    lambda text: r"\begin{tabular}{c}" + "\n" + text,
    lambda text: chr(96) * 3 + "\n" + text,
])
def test_ambiguous_groups_are_untouched(change):
    source = change(image_choices())
    assert normalize_paper_image_choices(source, "single_choice") == source

def test_non_choice_and_authored_choices_are_untouched():
    assert normalize_paper_image_choices(image_choices(), "experiment") == image_choices()
    source = normalize_paper_image_choices(image_choices(), "single_choice")
    assert normalize_paper_image_choices(source, "single_choice") == source

@pytest.mark.parametrize("value", [0, 19, 151, -1, True, float("inf"), float("nan"), 70.5, "70%", "1; width:100%", {}, []])
def test_invalid_scales_fail(value):
    with pytest.raises(ValueError):
        normalize_image_scale(value)

def test_default_and_endpoints():
    assert normalize_image_scale() == 70
    assert [normalize_image_scale(value) for value in [20, "100", 150]] == [20, 100, 150]

def test_scale_is_per_paper_not_per_question(client, db_session):
    from main import LOCAL_TOKEN
    client.headers['X-Local-Token'] = LOCAL_TOKEN
    q = Question(content=image_choices(), question_type="single_choice")
    db_session.add(q)
    db_session.commit()
    before = q.content
    saved = []
    for scale in (40, 120):
        result = client.post("/api/paper/save", json={
            "title": "配图比例测试", "questions": [{"id": q.id, "score": 5, "image_scale": scale}]
        })
        assert result.status_code == 200, result.text
        saved.append(result.json()["paper_id"])
    for paper_id, scale in zip(saved, (40, 120)):
        detail = client.get(f"/api/papers/{paper_id}").json()["data"]
        assert detail["questions"][0]["image_scale"] == scale
        assert detail["questions"][0]["question"]["content"] == before
    db_session.refresh(q)
    assert q.content == before
    from main import _prepare_paper_export_questions, PaperExportValidationError
    exported = _prepare_paper_export_questions([{"id": q.id, "image_scale": 55}], db_session)
    assert exported[0]["question"]["paper_image_scale"] == 55
    with pytest.raises(PaperExportValidationError):
        _prepare_paper_export_questions([{"id": q.id, "image_scale": 999}], db_session)
    assert client.post("/api/paper/save", json={
        "title": "无效比例", "questions": [{"id": q.id, "image_scale": -1}]
    }).status_code == 400

@pytest.mark.parametrize("paper_type", ["exam", "quiz", "exam_19"])
def test_latex_scale_and_option_order(paper_type):
    q = question()
    before = deepcopy(q)
    tex = build_latex_document("图片比例", "", paper_type, [{"question": q, "score": 5}],
                               show_secret=False, show_notice=False)
    assert r"\begin{choices}[columns=4,label-pos=left]" in tex
    assert tex.count("max width=2.1cm,max height=2.1cm") == 4
    assert [tex.index("{" + label + ".png}") for label in "ABCD"] == sorted(
        tex.index("{" + label + ".png}") for label in "ABCD")
    assert all(tex.count("{" + label + ".png}") == 1 for label in ["stem", *"ABCD"])
    assert q == before

def make_images(directory):
    for name in ["stem", *"ABCD"]:
        Image.new("RGB", (600, 400), "orange" if name == "stem" else "blue").save(directory / f"{name}.png")

def test_word_scale_reduces_every_picture_and_keeps_four_columns(tmp_path):
    make_images(tmp_path)
    widths = []
    for scale in (40, 80):
        q = question(scale)
        original = deepcopy(q)
        data, diagnostics = build_word_document("图片比例", "", "exam", [{"question": q, "score": 5}],
            uploads_dir=tmp_path, show_secret=False, show_notice=False)
        doc = Document(BytesIO(data))
        assert len(doc.inline_shapes) == 5
        assert len(doc.tables[0].columns) == 4
        widths.append([shape.width for shape in doc.inline_shapes])
        assert q == original
    assert all(b == pytest.approx(a * 2, abs=2) for a, b in zip(*widths))

@pytest.mark.skipif(os.environ.get("MATHBANK_TEST_TIKZ_NATIVE") != "1", reason="opt-in XeLaTeX")
def test_real_pdf_four_options_share_one_row_at_default_scale(tmp_path):
    import pymupdf
    make_images(tmp_path)
    tex = build_latex_document("物理配图验收", "", "exam", [{"question": question(), "score": 5}],
                               show_secret=False, show_notice=False)
    pdf, diagnostics = compile_tex_to_pdf(tex, [str(path) for path in tmp_path.glob("*.png")])
    assert pdf, diagnostics
    (tmp_path / "paper-image-scale.pdf").write_bytes(pdf)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) == 1
        figures = [entry["bbox"] for page in doc for entry in page.get_image_info()]
        assert len(figures) == 5
        options = figures[1:]
        assert max(box[1] for box in options) - min(box[1] for box in options) < 1
        assert all(box[2] - box[0] <= 2.1 * 72 / 2.54 + 1 for box in options)
