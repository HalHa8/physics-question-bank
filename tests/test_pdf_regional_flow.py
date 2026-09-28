"""Regional PDF routing with mocked paid boundaries and the real task lifecycle."""

import uuid
from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image

from mathbank.ai_providers import OCRConfigurationError, OCRResponseTimeoutError, ParseConfigurationError


@pytest.fixture(autouse=True)
def no_model_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("Regional flow tests must not contact a model")
    monkeypatch.setattr("requests.sessions.Session.request", reject)


def pdf_bytes(count=3):
    with fitz.open() as document:
        for _ in range(count):
            document.new_page(width=595, height=842)
        return document.tobytes()


def joint(markdown):
    return {"markdown": markdown, "layout": {"figures": [], "ignored_candidates": [],
            "page_complete": True, "notes": []},
            "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 150}}


@pytest.mark.parametrize("strategy", ["layout_aware", "native_preferred"])
def test_native_regional_and_full_pages_share_one_split_without_duplicate_vision(monkeypatch, strategy):
    import main
    from mathbank import pdf_native_regions, pdf_region_vision, pdf_page_vision

    native = "1. 原生正文保持不变，计算结果并说明理由。"
    regional = "2. 局部页保留原文。识别公式 $x=2$。"
    full = "3. 复杂页面完成识别。"
    monkeypatch.setattr(main, "inspect_and_extract_pdf", lambda *a, **k: {
        "pdf_type": "mixed", "pages": [
            {"page_index": 0, "markdown": native, "needs_ocr": False},
            {"page_index": 1, "markdown": "BAD_NATIVE", "needs_ocr": True},
            {"page_index": 2, "markdown": "BAD_TABLE", "needs_ocr": True},
        ],
    })
    planned, regional_calls, full_calls = [], [], []
    def plan(page, info):
        planned.append(info["page_index"])
        if info["page_index"] != 1:
            return None
        return {"pieces": [{"text": "局部页保留原文。"}, {"region_id": "r1"}],
                "regions": [{"id": "r1", "bbox": [0, 0, 1000, 200], "page_info": info}],
                "native_characters": 9, "area_ratio": .2, "kind": "mixed"}
    monkeypatch.setattr(pdf_native_regions, "plan_pdf_regions", plan)
    def region_request(image, info, plan, **kwargs):
        kwargs["check_cancelled"]()
        regional_calls.append((info["page_index"], kwargs["include_figures"]))
        return joint(regional)
    monkeypatch.setattr(pdf_region_vision, "request_pdf_regions", region_request)
    def page_request(image, info, **kwargs):
        full_calls.append(info["page_index"])
        return joint(full)
    monkeypatch.setattr(pdf_page_vision, "request_pdf_page", page_request)
    def legacy(image):
        full_calls.append("legacy")
        return full
    monkeypatch.setattr(main, "ocr_pdf_page_image", legacy)
    split_inputs = []
    def split(source, *args, **kwargs):
        split_inputs.append(source)
        return [{"content": text, "answer_markdown": ""} for text in (native, regional, full)]
    monkeypatch.setattr(main, "parse_paper_text_internal", split)
    task_id = "regional-flow-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(), "regional.pdf", pdf_strategy=strategy)
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "completed", task.get("log")
        assert planned == [1, 2]
        assert regional_calls == [(1, strategy == "layout_aware")]
        assert full_calls == ([2] if strategy == "layout_aware" else ["legacy"])
        assert len(split_inputs) == 1 and native in split_inputs[0]
        assert "局部页保留原文" in split_inputs[0]
        assert "BAD_NATIVE" not in split_inputs[0] and "BAD_TABLE" not in split_inputs[0]
        diagnostic = task["diagnostics"]
        page_evidence = task["pdf_source_pages"]
        assert [item["page_number"] for item in page_evidence] == [1, 2, 3]
        assert [item["origin"] for item in page_evidence] == [
            "native", "regional_vision", "joint_vision" if strategy == "layout_aware" else "ocr"]
        assert all(item["markdown"].endswith(text) for item, text in zip(page_evidence, (native, regional, full)))
        assert all(isinstance(item["figures"], list) for item in page_evidence)
        assert diagnostic["pdf_extraction"]["native_pages"] == 1
        assert diagnostic["pdf_extraction"]["regional_pages"] == 1
        assert diagnostic["pdf_extraction"]["full_vision_pages"] == 1
        assert diagnostic["pdf_extraction"]["native_characters_reused"] == 9
        assert [p["mode"] for p in diagnostic["pdf_extraction"]["pages"]] == ["native", "regional", "full_vision"]
        assert diagnostic["pdf_regional_usage"]["total_tokens"] == 150
        if strategy == "layout_aware":
            assert diagnostic["pdf_layout"]["visual_calls"] == 0
            assert diagnostic["pdf_layout"]["joint_visual_calls"] == 2
            assert diagnostic["pdf_layout"]["regional_visual_calls"] == 1
            assert diagnostic["pdf_joint_usage"]["total_tokens"] == 300
    finally:
        main.DOCUMENT_TASKS.remove(task_id)


def test_failed_regional_call_never_retries_full_page_or_splits(monkeypatch):
    import main
    from mathbank import pdf_native_regions, pdf_region_vision, pdf_page_vision

    monkeypatch.setattr(main, "inspect_and_extract_pdf", lambda *a, **k: {
        "pdf_type": "mixed", "pages": [{"page_index": 0, "markdown": "BAD", "needs_ocr": True}]})
    monkeypatch.setattr(pdf_native_regions, "plan_pdf_regions", lambda *a: {
        "native_characters": 50, "regions": [{}], "area_ratio": .3})
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise ValueError("局部识别缺少区域，未自动重试")
    def forbidden(*args, **kwargs):
        raise AssertionError("No second paid request or split is allowed")
    monkeypatch.setattr(pdf_region_vision, "request_pdf_regions", fail)
    monkeypatch.setattr(pdf_page_vision, "request_pdf_page", forbidden)
    monkeypatch.setattr(main, "ocr_pdf_page_image", forbidden)
    monkeypatch.setattr(main, "parse_paper_text_internal", forbidden)
    task_id = "regional-failure-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(1), "failure.pdf", pdf_strategy="layout_aware")
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "error" and "局部识别缺少区域" in task["error"]
        assert calls == [True]
    finally:
        main.DOCUMENT_TASKS.remove(task_id)


def test_missing_ocr_configuration_marks_task_for_settings_without_second_call(monkeypatch):
    import main
    from mathbank import pdf_native_regions, pdf_page_vision

    monkeypatch.setattr(main, "inspect_and_extract_pdf", lambda *a, **k: {
        "pdf_type": "mixed", "pages": [
            {"page_index": 0, "markdown": "原生正文", "needs_ocr": False},
            {"page_index": 1, "markdown": "不可靠", "needs_ocr": True},
        ],
    })
    monkeypatch.setattr(pdf_native_regions, "plan_pdf_regions", lambda *a: None)
    calls = []

    def missing(*args, **kwargs):
        calls.append(1)
        raise OCRConfigurationError("硅基流动 API Key 未配置，请在系统设置中填写。")

    monkeypatch.setattr(pdf_page_vision, "request_pdf_page", missing)
    monkeypatch.setattr(main, "parse_paper_text_internal", lambda *a, **k: pytest.fail("No incomplete split"))
    task_id = "regional-missing-ocr-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(2), "needs-ocr.pdf", pdf_strategy="layout_aware")
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "error"
        assert task["error_code"] == "ocr_configuration_required"
        assert "第 2 页需要识图" in task["error"]
        assert calls == [1]
    finally:
        main.DOCUMENT_TASKS.remove(task_id)


def test_full_page_timeout_identifies_page_and_never_retries_or_splits(monkeypatch):
    import main
    from mathbank import pdf_native_regions, pdf_page_vision

    monkeypatch.setattr(main, "inspect_and_extract_pdf", lambda *a, **k: {
        "pdf_type": "mixed", "pages": [
            {"page_index": 0, "markdown": "原生正文", "needs_ocr": False},
            {"page_index": 1, "markdown": "不可靠", "needs_ocr": True},
        ],
    })
    monkeypatch.setattr(pdf_native_regions, "plan_pdf_regions", lambda *a: None)
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise OCRResponseTimeoutError("识图服务在 300 秒内未返回结果；可能已计费，未自动重试。")

    monkeypatch.setattr(pdf_page_vision, "request_pdf_page", timeout)
    monkeypatch.setattr(main, "parse_paper_text_internal", lambda *a, **k: pytest.fail("No incomplete split"))
    task_id = "regional-ocr-timeout-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(2), "timeout.pdf", pdf_strategy="layout_aware")
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "error"
        assert task["error_code"] == "ocr_response_timeout"
        assert "第 2 页识图超时" in task["error"]
        assert calls == [1]
    finally:
        main.DOCUMENT_TASKS.remove(task_id)


def test_wide_table_full_page_uses_compact_vector_render_and_cleans_it(monkeypatch):
    import main
    from mathbank import pdf_native_regions, pdf_page_vision

    monkeypatch.setattr(main, "inspect_and_extract_pdf", lambda *a, **k: {
        "pdf_type": "scanned", "pages": [{"page_index": 0, "markdown": "原生错排文字" * 30,
            "needs_ocr": True, "quality_reasons": ["原生正文被错排为宽表。"]}],
    })
    monkeypatch.setattr(pdf_native_regions, "plan_pdf_regions", lambda *a: None)
    received = []

    def capture(image_path, info, **kwargs):
        with Image.open(image_path) as image:
            received.append((str(image_path), image.size))
        return joint("1. 识别后的完整题文。")

    monkeypatch.setattr(pdf_page_vision, "request_pdf_page", capture)
    monkeypatch.setattr(main, "parse_paper_text_internal", lambda *a, **k: [
        {"content": "识别后的完整题文。", "answer_markdown": ""},
    ])
    task_id = "regional-compact-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(1), "wide-table.pdf", pdf_strategy="layout_aware")
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "completed", task.get("error")
        assert len(received) == 1 and received[0][1][0] < 1000
        assert received[0][1][1] < 1400
        assert not Path(received[0][0]).exists()
    finally:
        main.DOCUMENT_TASKS.remove(task_id)


def test_missing_split_model_configuration_marks_task_for_settings(monkeypatch):
    import main

    monkeypatch.setattr(main, "inspect_and_extract_pdf", lambda *a, **k: {
        "pdf_type": "text_based", "pages": [
            {"page_index": 0, "markdown": "1. 原生试题", "needs_ocr": False},
        ],
    })
    monkeypatch.setattr(main, "parse_paper_text_internal", lambda *a, **k: (_ for _ in ()).throw(
        ParseConfigurationError("试卷拆解模型 API Key 未配置。")))
    task_id = "regional-missing-parse-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(1), "no-model.pdf", pdf_strategy="native_preferred")
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "error"
        assert task["error_code"] == "parse_configuration_required"
    finally:
        main.DOCUMENT_TASKS.remove(task_id)


def test_force_ocr_never_uses_regional_planning(monkeypatch):
    import main
    from mathbank import pdf_native_regions, pdf_region_vision

    def forbidden(*args, **kwargs):
        raise AssertionError("Force OCR must not use native or regional routing")
    monkeypatch.setattr(main, "inspect_and_extract_pdf", forbidden)
    monkeypatch.setattr(pdf_native_regions, "plan_pdf_regions", forbidden)
    monkeypatch.setattr(pdf_region_vision, "request_pdf_regions", forbidden)
    monkeypatch.setattr(main, "ocr_pdf_page_image", lambda *a: "1. 直接识别整页。")
    monkeypatch.setattr(main, "parse_paper_text_internal", lambda *a, **k: [{"content": "直接识别整页。"}])
    task_id = "regional-force-" + uuid.uuid4().hex
    main.DOCUMENT_TASKS.create(task_id, document_type="pdf", temp_assets=[])
    try:
        main.run_pdf_parsing_task(task_id, pdf_bytes(1), "force.pdf", pdf_strategy="force_ocr")
        task = main.DOCUMENT_TASKS.snapshot(task_id)
        assert task["status"] == "completed"
        assert task["diagnostics"]["pdf_extraction"]["full_vision_pages"] == 1
        assert task["diagnostics"]["pdf_extraction"]["regional_pages"] == 0
    finally:
        main.DOCUMENT_TASKS.remove(task_id)
