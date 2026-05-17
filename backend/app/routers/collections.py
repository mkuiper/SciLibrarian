from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DB, CurrentUser
from app.models.collection import Collection
from app.models.project import Project
from app.models.reference import Reference
from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionOut
from app.services.access import user_can_access_project, require_project_access

router = APIRouter(prefix="/collections", tags=["collections"])


def build_path(parent_path: str, collection_id: int) -> str:
    return f"{parent_path}{collection_id}/"


async def _count(db, collection_id: int) -> int:
    return (await db.execute(
        select(func.count(Reference.id)).where(Reference.collection_id == collection_id)
    )).scalar_one()


async def _require_collection_access(db, collection_id: int, user_id: int) -> Collection:
    """Fetch a collection and enforce project-ownership-based access.

    Like require_reference_access, 404 covers both missing and foreign so
    existence isn't leaked. Collections with no project_id are treated as
    universally accessible (legacy data from before project scoping).
    """
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    if col.project_id is not None and not await user_can_access_project(db, col.project_id, user_id):
        raise HTTPException(status_code=404, detail="Collection not found")
    return col


def _user_project_filter(user_id: int):
    """Build a subquery returning project IDs the user can access."""
    return select(Project.id).where(Project.created_by == user_id).scalar_subquery()


def _col_to_out(col: Collection, ref_count: int = 0, children: list = None) -> CollectionOut:
    """Build CollectionOut without accessing lazy SQLAlchemy relationships."""
    return CollectionOut(
        id=col.id,
        name=col.name,
        description=col.description,
        parent_id=col.parent_id,
        project_id=col.project_id,
        path=col.path,
        created_by=col.created_by,
        created_at=col.created_at,
        reference_count=ref_count,
        children=children or [],
    )


@router.post("", response_model=CollectionOut, status_code=201)
async def create_collection(data: CollectionCreate, db: DB, current_user: CurrentUser):
    parent_path = "/"
    project_id = data.project_id

    if data.parent_id:
        parent = await _require_collection_access(db, data.parent_id, current_user.id)
        parent_path = parent.path
        if not project_id:
            project_id = parent.project_id

    # If a project_id is supplied (or derived from parent), enforce ownership.
    if project_id is not None and not await user_can_access_project(db, project_id, current_user.id):
        raise HTTPException(status_code=404, detail="Project not found")

    col = Collection(
        name=data.name,
        description=data.description,
        parent_id=data.parent_id,
        project_id=project_id,
        path=parent_path,
        created_by=current_user.id,
    )
    db.add(col)
    await db.flush()
    col.path = build_path(parent_path, col.id)
    await db.flush()
    await db.refresh(col)
    count = await _count(db, col.id)
    return _col_to_out(col, count)


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    db: DB,
    current_user: CurrentUser,
    project_id: Optional[int] = Query(None),
):
    if project_id is not None:
        # Verify ownership of the specific project being queried.
        await require_project_access(db, project_id, current_user.id)
    user_projects = _user_project_filter(current_user.id)
    stmt = select(Collection).where(Collection.project_id.in_(user_projects)).order_by(Collection.path)
    if project_id:
        stmt = stmt.where(Collection.project_id == project_id)
    result = await db.execute(stmt)
    cols = result.scalars().all()
    out = []
    for col in cols:
        count = await _count(db, col.id)
        out.append(_col_to_out(col, count))
    return out


@router.get("/tree", response_model=list[CollectionOut])
async def get_collection_tree(
    db: DB,
    current_user: CurrentUser,
    project_id: Optional[int] = Query(None),
):
    if project_id is not None:
        await require_project_access(db, project_id, current_user.id)
    user_projects = _user_project_filter(current_user.id)
    stmt = (
        select(Collection)
        .where(Collection.parent_id == None, Collection.project_id.in_(user_projects))
        .order_by(Collection.name)
    )
    if project_id:
        stmt = stmt.where(Collection.project_id == project_id)
    result = await db.execute(stmt)
    roots = result.scalars().all()

    async def load_children(col: Collection) -> CollectionOut:
        count = await _count(db, col.id)
        child_result = await db.execute(
            select(Collection).where(Collection.parent_id == col.id).order_by(Collection.name)
        )
        children = [await load_children(c) for c in child_result.scalars().all()]
        return _col_to_out(col, count, children)

    return [await load_children(r) for r in roots]


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(collection_id: int, db: DB, current_user: CurrentUser):
    col = await _require_collection_access(db, collection_id, current_user.id)
    count = await _count(db, col.id)
    return _col_to_out(col, count)


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(collection_id: int, data: CollectionUpdate, db: DB, current_user: CurrentUser):
    col = await _require_collection_access(db, collection_id, current_user.id)
    for field in ["name", "description"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(col, field, val)
    await db.flush()
    await db.refresh(col)
    count = await _count(db, col.id)
    return _col_to_out(col, count)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(collection_id: int, db: DB, current_user: CurrentUser):
    col = await _require_collection_access(db, collection_id, current_user.id)
    await db.delete(col)


@router.get("/{collection_id}/bibtex")
async def export_collection_bibtex(collection_id: int, db: DB, current_user: CurrentUser):
    from app.routers.references import _to_bibtex

    col = await _require_collection_access(db, collection_id, current_user.id)

    refs = (await db.execute(
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(Reference.collection_id == collection_id)
    )).scalars().all()

    body = "\n\n".join(_to_bibtex(ref) for ref in refs)
    return Response(
        content=body,
        media_type="text/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="collection_{collection_id}.bib"'},
    )
