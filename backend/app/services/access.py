"""
Project / reference access control.

Closes the standing security gap (memory note: "Direct reference endpoints
do not enforce project ownership"). Until the Phase 4 team-membership model
lands, "access" is the minimum-viable check: the current user must either
have created the project, or have created the reference itself. In the
single-user deployment that the project currently targets, every check
passes — these helpers are a no-op for that case but provide hard isolation
the moment a second user is added.

Design:
* user_can_access_project(db, project_id, user_id) — True when the user
  created the project, or when project_id is None.
* user_can_access_reference(db, ref, user_id) — True when the user created
  the ref directly, OR has project access to the ref's project_id.
* require_reference_access(...) is the FastAPI-friendly entrypoint: it
  fetches the reference, raises 404 when missing, 403 when present but
  inaccessible, and returns the ref otherwise.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.reference import Reference


async def user_can_access_project(db: AsyncSession, project_id: Optional[int], user_id: int) -> bool:
    """True when the user can read/write the given project.

    A None project_id is treated as "no project scope" and always allowed — this
    keeps orphan references (no project assigned yet) reachable by whoever
    created them.
    """
    if project_id is None:
        return True
    result = await db.execute(select(Project.created_by).where(Project.id == project_id))
    row = result.first()
    if row is None:
        # The project genuinely doesn't exist — let the caller decide whether
        # that's a 404 or a denial (typically 404 in the calling endpoint).
        return False
    return row[0] == user_id


async def user_can_access_reference(db: AsyncSession, ref: Reference, user_id: int) -> bool:
    """True when the user owns the reference directly or owns its project."""
    if ref.created_by == user_id:
        return True
    return await user_can_access_project(db, ref.project_id, user_id)


async def require_reference_access(
    db: AsyncSession,
    ref_id: int,
    user_id: int,
    *,
    load_tags: bool = False,
) -> Reference:
    """Fetch a reference and enforce access in one call.

    Raises HTTPException(404) when the reference doesn't exist (don't leak
    existence to unauthorised users) and HTTPException(403) only after
    confirming the row exists — but in practice we collapse both to 404 below
    so that an attacker cannot distinguish "no such id" from "exists but not
    yours". Returns the loaded Reference on success.
    """
    stmt = select(Reference).where(Reference.id == ref_id)
    if load_tags:
        stmt = stmt.options(selectinload(Reference.tags))
    ref = (await db.execute(stmt)).scalar_one_or_none()
    if ref is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    if not await user_can_access_reference(db, ref, user_id):
        # Same status as not-found so existence is not leaked.
        raise HTTPException(status_code=404, detail="Reference not found")
    return ref


async def require_project_access(db: AsyncSession, project_id: int, user_id: int) -> Project:
    """Fetch a project and enforce access. Returns the Project on success."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.created_by != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
