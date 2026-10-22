"""Knowledge catalogue HTTP boundary; no application bootstrap or AI access."""

from dataclasses import dataclass
from typing import Callable

from fastapi import BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from mathbank.application_state import RuntimeState
from mathbank.database import get_db
from mathbank.knowledge_points import create_local_point, list_catalog


@dataclass(frozen=True)
class KnowledgePointServiceDependencies:
    state: RuntimeState
    schedule_database_export: Callable


def get_knowledge_points(q: str = "", compulsory: str = "", chapter: str = "", knowledge: str = "",
                         limit: int = 100, offset: int = 0, version_code: str = "P", db: Session = Depends(get_db), *,
                         dependencies: KnowledgePointServiceDependencies):
    try:
        return list_catalog(db, q, compulsory, chapter, knowledge, limit, offset, version_code=version_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def add_knowledge_point(payload: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db), *,
                        dependencies: KnowledgePointServiceDependencies):
    try:
        point = create_local_point(db, payload)
        # Serialize before committing; serialization failure cannot misreport a
        # successful write and tempt a duplicate retry.
        result = point.to_dict()
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    dependencies.schedule_database_export(background_tasks, operation="add_knowledge_point")
    return {**result, "status": "success", "point": result}
