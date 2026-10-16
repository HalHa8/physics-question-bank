"""Real image pages, queue reuse and pre-request validation; no model calls."""

from io import BytesIO
import time

from fastapi import UploadFile
from PIL import Image
import pymupdf
import pytest

from mathbank.asset_security import UploadTooLargeError
from mathbank.image_import_service import image_pages_to_pdf


def picture(color="red", *, format="PNG", orientation=None):
    buffer = BytesIO()
    image = Image.new("RGB", (80, 40), color)
    options = {}
    if orientation:
        exif = image.getexif()
        exif[274] = orientation
        options["exif"] = exif
    image.save(buffer, format=format, **options)
    return buffer.getvalue()


def upload(raw, name="page.png"):
    return UploadFile(filename=name, file=BytesIO(raw))


def test_pdf_preserves_selected_page_order_pixels_and_aspect_ratio():
    source = [picture("red"), picture("blue")]
    result = image_pages_to_pdf([upload(raw) for raw in source])
    with pymupdf.open(stream=result, filetype="pdf") as document:
        assert len(document) == 2
        for page, color in zip(document, [(255, 0, 0), (0, 0, 255)]):
            assert page.rect.width / page.rect.height == pytest.approx(2)
            image = pymupdf.Pixmap(document.extract_image(page.get_images()[0][0])["image"])
            assert (image.width, image.height) == (80, 40)
            assert image.pixel(30, 20) == color


def test_exif_rotated_photo_uses_transposed_dimensions_without_stretching():
    result = image_pages_to_pdf([upload(picture(format="JPEG", orientation=6), "photo.jpg")])
    with pymupdf.open(stream=result, filetype="pdf") as document:
        assert document[0].rect.height / document[0].rect.width == pytest.approx(2)
        raster = pymupdf.Pixmap(document.extract_image(document[0].get_images()[0][0])["image"])
        assert (raster.width, raster.height) == (40, 80)


@pytest.mark.parametrize("items", [[], [upload(picture()) for _ in range(21)]])
def test_page_limit_rejects_before_creating_a_task(items):
    with pytest.raises(ValueError, match="1 至 20"):
        image_pages_to_pdf(items)


def test_invalid_image_and_batch_size_are_rejected_without_partial_output():
    with pytest.raises(ValueError, match="第 2 张"):
        image_pages_to_pdf([upload(picture()), upload(b"<svg>not raster</svg>")])
    with pytest.raises(UploadTooLargeError, match="第 2 张"):
        image_pages_to_pdf([upload(picture()), upload(picture())], max_batch_bytes=len(picture()) + 1)


def test_single_file_cap_prevents_unbounded_reading():
    class TooBig:
        consumed = 0
        def read(self, count):
            self.consumed += count
            return b"x" * count
    stream = TooBig()
    with pytest.raises(UploadTooLargeError, match="第 1 张"):
        image_pages_to_pdf([UploadFile(filename="large.png", file=stream)])
    assert stream.consumed <= 10 * 1024 * 1024 + 1


def test_image_api_requires_token_and_rejects_invalid_bytes_before_queue(client, monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(main, "run_pdf_parsing_task", lambda *args: calls.append(args))
    assert client.post("/api/upload/image-task", files=[("files", ("one.png", picture(), "image/png"))]).status_code == 403
    response = client.post("/api/upload/image-task", headers={"X-Local-Token": main.LOCAL_TOKEN},
        files=[("files", ("bad.png", b"invalid", "image/png"))])
    assert response.status_code == 400
    assert calls == []


def test_image_api_uses_existing_task_queue_and_ocr_policy(client, monkeypatch):
    import main
    calls = []
    def process(task_id, content, filename, generate, page_range, strategy, verify):
        calls.append((content, filename, generate, page_range, strategy, verify))
        main.DOCUMENT_TASKS.update(task_id, status="completed", result=[])
    monkeypatch.setattr(main, "run_pdf_parsing_task", process)
    response = client.post("/api/upload/image-task", headers={"X-Local-Token": main.LOCAL_TOKEN}, data={"paper_title": "有来源的图片试卷"},
        files=[("files", ("blue.png", picture("blue"), "image/png")),
               ("files", ("red.png", picture("red"), "image/png"))])
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    deadline = time.monotonic() + 2
    while not calls and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(calls) == 1
    content, filename, generate, page_range, strategy, verify = calls[0]
    assert (filename, generate, page_range, strategy, verify) == ("有来源的图片试卷.pdf", False, None, "layout_aware", False)
    assert client.get(f"/api/tasks/{task_id}/status").json()["status"] == "completed"
    with pymupdf.open(stream=content, filetype="pdf") as document:
        assert len(document) == 2
        pixel = pymupdf.Pixmap(document.extract_image(document[0].get_images()[0][0])["image"])
        assert pixel.pixel(10, 10) == (0, 0, 255)


def test_full_queue_returns_existing_429_without_adding_a_second_queue(client, monkeypatch):
    import main
    def full(*args, **kwargs):
        raise main.TaskQueueFull("队列已满")
    monkeypatch.setattr(main.DOCUMENT_TASKS, "submit", full)
    response = client.post("/api/upload/image-task", headers={"X-Local-Token": main.LOCAL_TOKEN},
        files=[("files", ("page.png", picture(), "image/png"))])
    assert response.status_code == 429
    assert "队列已满" in response.json()["message"]
