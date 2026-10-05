"""Question asset service; all application dependencies are explicit."""

from dataclasses import dataclass
from typing import Any, Callable

from mathbank.application_state import RuntimeState
from pathlib import Path
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class QuestionAssetServiceDependencies:
    state: RuntimeState
    AssetSecurityError: Any
    Path: Any
    Question: Any
    _referenced_question_assets: Callable
    json: Any
    normalize_upload_asset_reference: Any
    re: Any
    resolve_upload_asset: Any
    shutil: Any


def rollback_question_asset_promotions(promotions: list[tuple[Path, Path]], *, dependencies: QuestionAssetServiceDependencies) -> None:
    """Best-effort compensation when a DB transaction rejects promoted files."""

    for source, destination in reversed(promotions):
        try:
            if destination.is_file() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                dependencies.shutil.move(str(destination), str(source))
        except OSError as exc:
            print(f"[Storage Rollback] Failed to restore a promoted asset: {type(exc).__name__}")


def _referenced_question_assets(db: Session, *, dependencies: QuestionAssetServiceDependencies) -> set[Path]:
    """Resolve every stored question image reference with one database query."""

    resolved_references: set[dependencies.Path] = set()
    rows = db.query(
        dependencies.Question._image_paths,
        dependencies.Question.content,
        dependencies.Question.answer_markdown,
    ).all()
    for raw_paths, content, answer_markdown in rows:
        references = []
        try:
            parsed = dependencies.json.loads(raw_paths or "[]")
            if isinstance(parsed, list):
                references.extend(parsed)
        except (TypeError, dependencies.json.JSONDecodeError):
            pass
        references.extend(
            dependencies.re.findall(
                r'/static/(?:uploads|test_uploads)/[a-zA-Z0-9_./-]+',
                f"{content or ''}\n{answer_markdown or ''}",
            )
        )
        for reference in references:
            try:
                resolved = dependencies.resolve_upload_asset(
                    reference,
                    uploads_dir=dependencies.state.UPLOAD_DIR,
                    url_prefix=dependencies.state.UPLOAD_DIR_REL,
                    require_file=False,
                )
            except dependencies.AssetSecurityError:
                continue
            resolved_references.add(resolved)
    return resolved_references


def delete_unreferenced_question_assets(db: Session, references, *, dependencies: QuestionAssetServiceDependencies) -> int:
    """Delete committed-away images only when no remaining question uses them."""

    candidates: set[dependencies.Path] = set()
    for reference in set(references or []):
        try:
            candidates.add(
                dependencies.resolve_upload_asset(
                    reference,
                    uploads_dir=dependencies.state.UPLOAD_DIR,
                    url_prefix=dependencies.state.UPLOAD_DIR_REL,
                    require_file=False,
                )
            )
        except dependencies.AssetSecurityError:
            print("[Storage Cleanup] Skipped an invalid legacy image path.")

    if not candidates:
        return 0
    referenced = dependencies._referenced_question_assets(db)
    removed = 0
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate not in referenced:
                candidate.unlink()
                removed += 1
        except OSError:
            print("[Storage Cleanup] Skipped an unavailable legacy image path.")
    return removed


def promote_question_temp_assets(content: str, answer_markdown: str, image_paths_list: list, *, promotion_log: list[tuple[Path, Path]] | None=None, dependencies: QuestionAssetServiceDependencies) -> tuple:
    """物理移动临时图片到永久目录，并更新题干、解析和图片路径列表中的引用"""
    import shutil

    if not isinstance(image_paths_list, list):
        raise dependencies.AssetSecurityError("image_paths 必须是插图路径数组。")

    embedded_paths = dependencies.re.findall(
        r'/static/(?:uploads|test_uploads)/tmp/[a-zA-Z0-9_.-]+',
        f"{content}\n{answer_markdown}",
    )
    all_references = [value for value in image_paths_list if value] + embedded_paths

    # Validate the complete set before moving anything.  A bad second path must
    # not leave the first path half-promoted.
    canonical_by_input: dict[str, str] = {}
    resolved_by_canonical: dict[str, dependencies.Path] = {}
    for reference in all_references:
        canonical = dependencies.normalize_upload_asset_reference(
            reference,
            uploads_dir=dependencies.state.UPLOAD_DIR,
            url_prefix=dependencies.state.UPLOAD_DIR_REL,
        )
        canonical_by_input[reference] = canonical
        resolved_by_canonical.setdefault(
            canonical,
            dependencies.resolve_upload_asset(
                canonical,
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            ),
        )

    upload_root = dependencies.Path(dependencies.state.UPLOAD_DIR).resolve()
    temp_root = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR).resolve()
    promoted_by_canonical: dict[str, str] = {}
    for canonical, source in resolved_by_canonical.items():
        if source.parent == temp_root:
            destination_url = f"/{dependencies.state.UPLOAD_DIR_REL}/{source.name}"
            destination = dependencies.resolve_upload_asset(
                destination_url,
                uploads_dir=upload_root,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
                require_file=False,
            )
            if destination.exists():
                raise dependencies.AssetSecurityError("目标插图文件已存在，已停止覆盖。")
            shutil.move(str(source), str(destination))
            if promotion_log is not None:
                promotion_log.append((source, destination))
            promoted_by_canonical[canonical] = dependencies.normalize_upload_asset_reference(
                destination_url,
                uploads_dir=upload_root,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
            )
        elif source.is_relative_to(upload_root):
            promoted_by_canonical[canonical] = canonical
        else:  # Defensive; resolve_upload_asset should already make this impossible.
            raise dependencies.AssetSecurityError("临时插图越出了上传目录。")

    replacements: dict[str, str] = {}
    for original, canonical in canonical_by_input.items():
        promoted = promoted_by_canonical[canonical]
        replacements[original] = promoted
        replacements[canonical] = promoted

    new_content = content
    new_answer = answer_markdown
    for old_path, new_path in replacements.items():
        new_content = new_content.replace(old_path, new_path)
        new_answer = new_answer.replace(old_path, new_path)

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

    return new_content, new_answer, updated_paths


def _delete_task_temp_assets(paths: list, *, dependencies: QuestionAssetServiceDependencies) -> int:
    """Delete only explicit files below this instance's upload tmp directory."""
    removed = 0
    tmp_root = dependencies.Path(dependencies.state.TMP_UPLOAD_DIR).resolve()
    for url in paths or []:
        try:
            full_path = dependencies.resolve_upload_asset(
                str(url),
                uploads_dir=dependencies.state.UPLOAD_DIR,
                url_prefix=dependencies.state.UPLOAD_DIR_REL,
                require_file=False,
            )
        except dependencies.AssetSecurityError:
            continue
        if full_path.parent != tmp_root:
            continue
        if full_path.is_file():
            try:
                full_path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
