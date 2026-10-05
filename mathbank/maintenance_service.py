"""Maintenance service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from fastapi import BackgroundTasks


@dataclass(frozen=True)
class MaintenanceServiceDependencies:
    state: RuntimeState
    DATABASE_PATH: Any
    PROJECT_ROOT: Any
    Question: Any
    QuestionCurriculum: Any
    clean_orphaned_images: Callable
    create_full_backup_if_due: Any
    export_database_to_files: Any
    fingerprint_for_question: Any
    get_active_version_code: Callable
    get_current_curriculum: Callable
    heal_database_curriculum_names: Callable
    is_pdf_inspector_available: Any
    json: Any
    load_curriculum: Any
    os: Any
    print_optional_tool_diagnostics: Callable
    rebuild_all_missing_fingerprints: Any
    recalibrate_usage_counts: Callable
    shutil: Any
    sys: Any
    time: Any
    upsert_question_fingerprint: Any


def schedule_database_export(background_tasks: BackgroundTasks, *, operation: str, dependencies: MaintenanceServiceDependencies) -> None:
    """Best-effort export scheduling after a database transaction commits."""

    def run_export_safely() -> None:
        try:
            dependencies.export_database_to_files()
        except Exception as exc:
            print(
                f"[Database Export] Post-commit export failed for {operation} "
                f"(type={type(exc).__name__}); the next write/startup export can retry."
            )

    try:
        background_tasks.add_task(run_export_safely)
    except Exception as exc:
        print(
            f"[Database Export] Post-commit scheduling failed for {operation} "
            f"(type={type(exc).__name__}); the next write/startup export can retry."
        )


def schedule_question_fingerprint_retry(background_tasks: BackgroundTasks, *, question_id: int, operation: str, dependencies: MaintenanceServiceDependencies) -> None:
    def retry_safely() -> None:
        from mathbank.database import SessionLocal

        retry_db = SessionLocal()
        try:
            question = retry_db.query(dependencies.Question).filter(dependencies.Question.id == question_id).first()
            if question is None:
                return
            fingerprint = dependencies.fingerprint_for_question(
                question,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            )
            dependencies.upsert_question_fingerprint(retry_db, question, fingerprint)
            retry_db.commit()
        except Exception as exc:
            retry_db.rollback()
            print(
                f"[Duplicate Index] Post-commit retry failed for {operation} "
                f"(question_id={question_id}, type={type(exc).__name__}); "
                "startup backfill will retry."
            )
        finally:
            retry_db.close()

    try:
        background_tasks.add_task(retry_safely)
    except Exception as exc:
        print(
            f"[Duplicate Index] Retry scheduling failed for {operation} "
            f"(question_id={question_id}, type={type(exc).__name__}); "
            "startup backfill will retry."
        )


def print_startup_diagnostics(*, dependencies: MaintenanceServiceDependencies):
    """打印不扫描 PATH、不阻塞就绪的基础启动诊断。"""
    is_venv = dependencies.sys.prefix != dependencies.sys.base_prefix
    env_type = f"虚拟环境 ({dependencies.os.path.basename(dependencies.sys.prefix)})" if is_venv else "全局/系统环境"
    pdf_insp_ok = dependencies.is_pdf_inspector_available()

    print("=" * 64, flush=True)
    print("      本地物理题库教研系统 (PhysicsBank) 启动自检与诊断面板", flush=True)
    print("=" * 64, flush=True)
    print(f"  • Python 运行环境   : {dependencies.sys.version.split()[0]} [{env_type}]", flush=True)
    print(f"  • Python 可执行路径 : {dependencies.sys.executable}", flush=True)
    if is_venv:
        print(f"  • 虚拟环境根目录   : {dependencies.sys.prefix}", flush=True)
    print(f"  • PDF Inspector 引擎: {'🚀 已就绪 (原生矢量试卷毫秒级直提)' if pdf_insp_ok else '⚠️ 未安装 (已自动平滑降级至 VLM 多模态 OCR)'}", flush=True)
    print("  • 可选排版工具   : 服务就绪后后台检测", flush=True)
    print(f"  • SQLite 本地数据库 : {dependencies.DATABASE_PATH}", flush=True)
    print(f"  • 项目静态与根路径 : {dependencies.PROJECT_ROOT}", flush=True)
    print("=" * 64, flush=True)


def print_optional_tool_diagnostics(*, dependencies: MaintenanceServiceDependencies):
    """服务就绪后再扫描可选工具，避免慢 PATH 阻断启动。"""

    latex_engine = dependencies.shutil.which("xelatex") or dependencies.shutil.which("pdflatex")
    pandoc_path = dependencies.os.getenv("MATHBANK_PANDOC_PATH", "").strip() or dependencies.shutil.which("pandoc")
    try:
        import pymupdf  # noqa: F401

        pymupdf_status = "ready"
    except ImportError:
        pymupdf_status = "missing"
    print(
        "[Optional Tools] "
        f"latex={latex_engine or 'missing'}, "
        f"pandoc={pandoc_path or 'missing'}, "
        f"pymupdf={pymupdf_status}",
        flush=True,
    )


def heal_database_curriculum_names(*, dependencies: MaintenanceServiceDependencies):
    # These aliases belong to legacy mathematics curricula. PhysicsBank uses
    # the official book names such as “必修第一册”, so applying the old repair
    # would silently corrupt valid physics classifications on every startup.
    if dependencies.get_active_version_code() == "P":
        return
    from mathbank.database import SessionLocal
    db = SessionLocal()
    try:
        mappings = {
            "选择性必修一": "选修一",
            "选择性必修二": "选修二",
            "选择性必修三": "选修三",
            "必修第一册": "必修一",
            "必修第二册": "必修二",
            "必修第三册": "必修三",
            "必修第四册": "必修四",
        }
        updated_questions = 0
        for old, new in mappings.items():
            res = db.query(dependencies.Question).filter(dependencies.Question.category_compulsory == old).update(
                {dependencies.Question.category_compulsory: new}, synchronize_session=False
            )
            updated_questions += res

        updated_mappings = 0
        for old, new in mappings.items():
            res = db.query(dependencies.QuestionCurriculum).filter(dependencies.QuestionCurriculum.compulsory == old).update(
                {dependencies.QuestionCurriculum.compulsory: new}, synchronize_session=False
            )
            updated_mappings += res

        # 清理在主表 questions 及镜像表 question_curriculums 中残留的不属于各自大纲小节列表的旧章名/错位知识点
        curr = dependencies.get_current_curriculum()
        healed_know_count = 0
        all_qs = db.query(dependencies.Question).all()
        for q in all_qs:
            comp = q.category_compulsory
            chap = q.category_chapter
            know = q.category_knowledge
            if know:
                valid_knows = curr.get(comp, {}).get(chap, [])
                if know not in valid_knows:
                    q.category_knowledge = ""
                    healed_know_count += 1

        all_qcs = db.query(dependencies.QuestionCurriculum).all()
        for qc in all_qcs:
            if qc.knowledge:
                try:
                    c_tree = dependencies.load_curriculum(qc.version_code)
                except ValueError:
                    c_tree = curr
                valid_knows = c_tree.get(qc.compulsory, {}).get(qc.chapter, [])
                if qc.knowledge not in valid_knows:
                    qc.knowledge = ""
                    healed_know_count += 1

        if updated_questions > 0 or updated_mappings > 0 or healed_know_count > 0:
            db.commit()
            print(f"[Self-Healing DB] Migrated {updated_questions} questions, {updated_mappings} mappings, and cleaned {healed_know_count} mismatched knowledge values.")
    except Exception as e:
        db.rollback()
        print(f"[Self-Healing DB Error] Failed to run database book names migration: {e}")
    finally:
        db.close()


def clean_orphaned_images(*, dependencies: MaintenanceServiceDependencies):
    """扫描 static/uploads 目录及其 tmp 子目录，安全彻底擦除未被数据库引用的孤儿图片与旧残留临时图片"""
    try:
        from mathbank.database import SessionLocal, Question
        db = SessionLocal()
        try:
            # 1. 搜集数据库中所有题目引用的图片路径
            questions = db.query(Question._image_paths).all()
            referenced_images = set()
            for (img_paths_str,) in questions:
                if img_paths_str:
                    try:
                        paths = dependencies.json.loads(img_paths_str)
                        for path in paths:
                            referenced_images.add(path.lstrip("/").lower())
                    except Exception:
                        pass

            # 2. 遍历本地图片目录及 tmp 子目录
            upload_dir = dependencies.state.UPLOAD_DIR
            if not dependencies.os.path.exists(upload_dir):
                return

            cleaned_count = 0
            now = dependencies.time.time()
            one_hour_seconds = 3600

            # 清理 static/uploads/ 根目录下未引用的孤儿图片
            for filename in dependencies.os.listdir(upload_dir):
                full_path = dependencies.os.path.join(upload_dir, filename)
                if dependencies.os.path.isfile(full_path) and not filename.startswith("."):
                    local_rel_path = f"{dependencies.state.UPLOAD_DIR_REL}/{filename}".lower()
                    if local_rel_path not in referenced_images:
                        try:
                            mtime = dependencies.os.path.getmtime(full_path)
                            if now - mtime > one_hour_seconds:
                                dependencies.os.remove(full_path)
                                cleaned_count += 1
                        except Exception:
                            pass

            # 清理 static/uploads/tmp/ 子目录下残留的所有旧拆卷/OCR临时切片图
            tmp_dir = dependencies.os.path.join(upload_dir, "tmp")
            if dependencies.os.path.exists(tmp_dir):
                for filename in dependencies.os.listdir(tmp_dir):
                    full_path = dependencies.os.path.join(tmp_dir, filename)
                    if dependencies.os.path.isfile(full_path) and not filename.startswith("."):
                        local_rel_path = f"{dependencies.state.UPLOAD_DIR_REL}/tmp/{filename}".lower()
                        if local_rel_path not in referenced_images:
                            try:
                                mtime = dependencies.os.path.getmtime(full_path)
                                if now - mtime > 600:  # 超过 10 分钟未被使用的 tmp 切片立即清理
                                    dependencies.os.remove(full_path)
                                    cleaned_count += 1
                            except Exception:
                                pass

            if cleaned_count > 0:
                print(f"[Storage Cleanup] 成功检测并清除 {cleaned_count} 个残留的旧临时图片与孤儿文件，磁盘无痕瘦身成功！")
        finally:
            db.close()
    except Exception as e:
        print(f"[Storage Cleanup Error] 执行静默图片净化时发生异常: {str(e)}")


def recalibrate_usage_counts(*, dependencies: MaintenanceServiceDependencies):
    """自动校准全库题目的引用频次 usage_count，修正由于历史删除试卷遗留的计数差异"""
    try:
        from mathbank.database import SessionLocal, Question, PaperQuestion
        from sqlalchemy import func
        db = SessionLocal()
        try:
            counts = db.query(PaperQuestion.question_id, func.count(PaperQuestion.id)).group_by(PaperQuestion.question_id).all()
            ref_map = dict(counts)
            questions = db.query(Question).all()
            changed = False
            for q in questions:
                actual_ref = ref_map.get(q.id, 0)
                if (q.usage_count or 0) != actual_ref:
                    q.usage_count = actual_ref
                    changed = True
            if changed:
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[Usage Calibration Error] {e}")


def start_startup_cleanup(*, dependencies: MaintenanceServiceDependencies):
    # Lifespan 已确保模块完整导入；再让出短暂时间给首屏请求。
    dependencies.time.sleep(2.5)
    try:
        backup_path = dependencies.create_full_backup_if_due()
        if backup_path:
            print(f"[Backup] 已创建并验证每日完整备份: {backup_path.name}")
    except Exception as exc:
        print(f"[Backup Error] 每日完整备份失败: {type(exc).__name__}: {exc}")
        dependencies.print_optional_tool_diagnostics()
        return
    dependencies.heal_database_curriculum_names()
    dependencies.clean_orphaned_images()
    dependencies.recalibrate_usage_counts()
    try:
        from mathbank.database import SessionLocal

        fingerprint_result = dependencies.rebuild_all_missing_fingerprints(
            SessionLocal,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
            batch_size=250,
        )
        if fingerprint_result.get("backfilled"):
            print(
                "[Duplicate Index] Backfill complete: "
                f"{fingerprint_result['indexed']}/{fingerprint_result['total']}"
            )
    except Exception as exc:
        print(
            "[Duplicate Index] Background backfill failed "
            f"(type={type(exc).__name__}); duplicate checks will report partial coverage."
        )
    dependencies.print_optional_tool_diagnostics()
