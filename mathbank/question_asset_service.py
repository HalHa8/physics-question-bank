"""Question asset service; all application dependencies are explicit."""

from typing import List, Optional
from pathlib import Path
from fastapi import BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session
from mathbank.database import get_db
from dataclasses import dataclass
from typing import Any, Callable
from mathbank.application_state import RuntimeState


@dataclass(frozen=True)
class QuestionAssetServiceDependencies:
    AssetLifecycleError: Any
    AssetSecurityError: Any
    Path: Any
    Question: Any
    _referenced_question_assets: Any
    embedded_question_assets: Any
    json: Any
    normalize_upload_asset_reference: Any
    os: Any
    quarantine_asset: Any
    re: Any
    resolve_upload_asset: Any
    rewrite_question_asset_paths: Any
    shutil: Any
    state: RuntimeState
    structured_question_assets: Any


def rollback_question_asset_promotions(promotions: list[tuple[Path, Path]], *, dependencies: QuestionAssetServiceDependencies) -> None:
    """Best-effort compensation when a DB transaction rejects promoted files."""
    for (source, destination) in reversed(promotions):
        try:
            if destination.is_file() and source.is_file():
                destination.unlink()
        except OSError as exc:
            print(f'[Storage Rollback] Failed to restore a promoted asset: {type(exc).__name__}')



def _referenced_question_assets(db: Session, *, dependencies: QuestionAssetServiceDependencies) -> set[Path]:
    """Resolve every stored question image reference with one database query."""
    resolved_references: set[dependencies.Path] = set()
    rows = db.query(dependencies.Question._image_paths, dependencies.Question.content, dependencies.Question.answer_markdown, dependencies.Question.review, dependencies.Question._content_tikz_assets, dependencies.Question._answer_tikz_assets, dependencies.Question.tikz_reference_image_path).yield_per(250)
    for (raw_paths, content, answer_markdown, review, content_assets, answer_assets, legacy_reference) in rows:
        references = []
        try:
            parsed = dependencies.json.loads(raw_paths or '[]')
            if not isinstance(parsed, list):
                raise ValueError('题目图片清单不是数组，已停止清理')
            references.extend(parsed)
            references.extend(dependencies.structured_question_assets(content_assets, answer_assets, legacy_reference=legacy_reference))
        except (TypeError, ValueError) as exc:
            raise ValueError('题目图片记录损坏，已停止清理') from exc
        references.extend(dependencies.embedded_question_assets(content, answer_markdown, review))
        references.extend(dependencies.re.findall('/static/(?:uploads|test_uploads)/[a-zA-Z0-9_./-]+', f"{content or ''}\n{answer_markdown or ''}"))
        for reference in references:
            try:
                resolved = dependencies.resolve_upload_asset(reference, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
            except dependencies.AssetSecurityError:
                continue
            resolved_references.add(resolved)
    return resolved_references


def delete_unreferenced_question_assets(db: Session, references, *, dependencies: QuestionAssetServiceDependencies) -> int:
    """Retain committed-away images recoverably after checking every reference."""
    candidates: set[dependencies.Path] = set()
    for reference in set(references or []):
        try:
            candidates.add(dependencies.resolve_upload_asset(reference, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False))
        except dependencies.AssetSecurityError:
            print('[Storage Cleanup] Skipped an invalid legacy image path.')
    if not candidates:
        return 0
    referenced = dependencies._referenced_question_assets(db)
    removed = 0
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate not in referenced:
                relative = candidate.relative_to(dependencies.Path(dependencies.state.UPLOAD_DIR).resolve()).as_posix()
                removed += int(dependencies.quarantine_asset(f'/{dependencies.state.UPLOAD_DIR_REL}/{relative}', uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, reason='question-reference-removed'))
        except (OSError, dependencies.AssetLifecycleError):
            print('[Storage Cleanup] Skipped an unavailable legacy image path.')
    return removed



def promote_question_temp_assets(content: str, answer_markdown: str, image_paths_list: list, *, promotion_log: list[tuple[Path, Path]] | None=None, path_map: dict[str, str] | None=None, dependencies: QuestionAssetServiceDependencies) -> tuple:
    """Copy temporary images durably, preserving drafts and shared import cards."""
    import shutil
    if not isinstance(image_paths_list, list):
        raise dependencies.AssetSecurityError('image_paths 必须是插图路径数组。')
    embedded_paths = dependencies.embedded_question_assets(content, answer_markdown)
    all_references = [value for value in image_paths_list if value] + embedded_paths
    canonical_by_input: dict[str, str] = {}
    resolved_by_canonical: dict[str, dependencies.Path] = {}
    for reference in all_references:
        canonical = dependencies.normalize_upload_asset_reference(reference, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL)
        canonical_by_input[reference] = canonical
        resolved_by_canonical.setdefault(canonical, dependencies.resolve_upload_asset(canonical, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL))
    upload_root = dependencies.Path(dependencies.state.UPLOAD_DIR).resolve()
    temp_root = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR).resolve()
    promoted_by_canonical: dict[str, str] = {}
    for (canonical, source) in resolved_by_canonical.items():
        if source.parent == temp_root:
            destination_url = f'/{dependencies.state.UPLOAD_DIR_REL}/{source.name}'
            destination = dependencies.resolve_upload_asset(destination_url, uploads_dir=upload_root, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
            from mathbank.asset_lifecycle import restore_asset
            restore_asset(destination, uploads_dir=upload_root)
            if destination.exists():
                with source.open('rb') as original, destination.open('rb') as existing:
                    while True:
                        (left, right) = (original.read(1024 * 1024), existing.read(1024 * 1024))
                        if left != right:
                            raise dependencies.AssetSecurityError('目标插图文件已存在且内容不同，已停止覆盖。')
                        if not left:
                            break
            else:
                output = destination.open('xb')
                try:
                    with output, source.open('rb') as original:
                        shutil.copyfileobj(original, output)
                        output.flush()
                        dependencies.os.fsync(output.fileno())
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                if promotion_log is not None:
                    promotion_log.append((source, destination))
            promoted_by_canonical[canonical] = dependencies.normalize_upload_asset_reference(destination_url, uploads_dir=upload_root, url_prefix=dependencies.state.UPLOAD_DIR_REL)
        elif source.is_relative_to(upload_root):
            promoted_by_canonical[canonical] = canonical
        else:
            raise dependencies.AssetSecurityError('临时插图越出了上传目录。')
    replacements: dict[str, str] = {}
    for (original, canonical) in canonical_by_input.items():
        promoted = promoted_by_canonical[canonical]
        replacements[original] = promoted
        replacements[canonical] = promoted
    new_content = dependencies.rewrite_question_asset_paths(content, replacements)
    new_answer = dependencies.rewrite_question_asset_paths(answer_markdown, replacements)
    if path_map is not None:
        path_map.update({old: new for (old, new) in replacements.items() if old != new})
    updated_paths: list[str] = []
    for original in image_paths_list:
        if not original:
            continue
        promoted = promoted_by_canonical[canonical_by_input[original]]
        if promoted not in updated_paths:
            updated_paths.append(promoted)
    for embedded in embedded_paths:
        promoted = promoted_by_canonical[canonical_by_input[embedded]]
        if promoted not in updated_paths:
            updated_paths.append(promoted)
    return (new_content, new_answer, updated_paths)



def _delete_task_temp_assets(paths: list, *, dependencies: QuestionAssetServiceDependencies) -> int:
    """Retain task files recoverably so old drafts and result URLs still work."""
    removed = 0
    tmp_root = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR).resolve()
    from mathbank.database import SessionLocal
    try:
        with SessionLocal() as db:
            referenced = dependencies._referenced_question_assets(db)
        if dependencies.state.DOCUMENT_PROJECTS:
            for url in dependencies.state.DOCUMENT_PROJECTS.referenced_assets():
                try:
                    referenced.add(dependencies.resolve_upload_asset(url, uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False))
                except dependencies.AssetSecurityError:
                    pass
    except Exception as exc:
        print(f'[Storage Retention] Could not verify task image references; kept files ({type(exc).__name__}).')
        return 0
    for url in paths or []:
        try:
            full_path = dependencies.resolve_upload_asset(str(url), uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, require_file=False)
        except dependencies.AssetSecurityError:
            continue
        if full_path.parent != tmp_root or full_path in referenced:
            continue
        if full_path.is_file():
            try:
                removed += int(dependencies.quarantine_asset(str(url), uploads_dir=dependencies.state.UPLOAD_DIR, url_prefix=dependencies.state.UPLOAD_DIR_REL, reason='document-task-expired-or-cancelled'))
            except (OSError, dependencies.AssetLifecycleError):
                pass
    return removed
