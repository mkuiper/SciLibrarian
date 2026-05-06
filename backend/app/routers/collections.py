from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.dependencies import DB, CurrentUser
from app.models.collection import Collection
from app.models.reference import Reference
from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionOut

router = APIRouter(prefix="/collections", tags=["collections"])


def build_path(parent_path: str, collection_id: int) -> str:
    return f"{parent_path}{collection_id}/"


async def _count(db, collection_id: int) -> int:
    return (await db.execute(
        select(func.count(Reference.id)).where(Reference.collection_id == collection_id)
    )).scalar_one()


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
        result = await db.execute(select(Collection).where(Collection.id == data.parent_id))
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent collection not found")
        parent_path = parent.path
        if not project_id:
            project_id = parent.project_id

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
    stmt = select(Collection).order_by(Collection.path)
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
    stmt = select(Collection).where(Collection.parent_id == None).order_by(Collection.name)
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
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    count = await _count(db, col.id)
    return _col_to_out(col, count)


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(collection_id: int, data: CollectionUpdate, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
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
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.delete(col)
