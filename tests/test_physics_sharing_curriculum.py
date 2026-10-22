"""Sharing preflight may overlap P/legacy-A changes; backup+append cannot."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
import threading
import time
import pytest
from mathbank.curriculums import build_default_metadata
from mathbank.database import Question, QuestionCurriculum


@pytest.fixture
def metadata_scope(monkeypatch, tmp_path):
    import main
    monkeypatch.setattr(main, "METADATA_CACHE", build_default_metadata("P"))
    monkeypatch.setattr(main, "METADATA_FILE", str(tmp_path / "metadata.json"))
    monkeypatch.setattr(main, "schedule_database_export", lambda *args, **kwargs: None)
    return main

@pytest.mark.parametrize("pause_stage", ("inspect", "backup"))
def test_physics_zip_import_preparation_can_overlap_switch_but_backup_and_commit_bind_one_version(client, db_session, metadata_scope, monkeypatch, tmp_path, pause_stage):
    main = metadata_scope
    entered, release, switch_started = threading.Event(), threading.Event(), threading.Event()
    captures = []
    monkeypatch.setattr(main, "SYSTEM_GENERATED_DIR", tmp_path / "runtime")
    monkeypatch.setattr(main, "DATA_BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(main, "DATABASE_PATH", str(tmp_path / "isolated.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", str(tmp_path / "uploads"))
    prepared_package = SimpleNamespace(summary={"image_count": 0})
    @contextmanager
    def prepare(_archive, *, workspace_dir=None):
        if pause_stage == "inspect":
            entered.set()
            assert release.wait(5)
        yield prepared_package
    def backup(**kwargs):
        captures.append(("backup", main.get_active_version_code()))
        if pause_stage == "backup":
            entered.set()
            assert release.wait(5)
        return tmp_path / "isolated-backup.zip"
    def importer(db, _archive, *, uploads_dir, active_version, prepared):
        assert prepared is prepared_package
        captures.append(("import", active_version))
        assert active_version == main.get_active_version_code()
        question = Question(content="隔离导入题文", category_compulsory=active_version + "册", category_chapter="原章", category_knowledge="原节")
        question.curriculum_mappings.append(QuestionCurriculum(version_code=active_version, compulsory=active_version + "册", chapter="原章", knowledge="原节"))
        db.add(question)
        db.commit()
        return {"imported_count": 1, "image_count": 0}
    monkeypatch.setattr(main, "prepare_library_import", prepare)
    monkeypatch.setattr(main, "create_full_backup", backup)
    monkeypatch.setattr(main, "import_library_zip", importer)
    headers = {"X-Local-Token": main.LOCAL_TOKEN}
    def transfer():
        return client.post("/api/library-transfer/import", files={"file": ("share.zip", b"isolated test package", "application/zip")}, headers=headers)
    def switch():
        switch_started.set()
        return client.post("/api/config/metadata", json=build_default_metadata("A"), headers=headers)
    with ThreadPoolExecutor(max_workers=2) as executor:
        import_future = executor.submit(transfer)
        assert entered.wait(5)
        switch_future = executor.submit(switch)
        try:
            assert switch_started.wait(5)
            if pause_stage == "inspect":
                assert switch_future.result(timeout=5).status_code == 200
            else:
                time.sleep(0.03)
                assert not switch_future.done()
        finally:
            release.set()
        import_result, switch_result = import_future.result(timeout=10), switch_future.result(timeout=10)
    assert import_result.status_code == switch_result.status_code == 200
    version = "A" if pause_stage == "inspect" else "P"
    assert captures == [("backup", version), ("import", version)]
    assert import_result.json()["active_version_code"] == version
    db_session.expire_all()
    question = db_session.query(Question).one()
    n = db_session.query(QuestionCurriculum).filter_by(question_id=question.id, version_code="A").one()
    assert (question.category_compulsory, question.category_chapter, question.category_knowledge) == (n.compulsory, n.chapter, n.knowledge)
