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


async def _to_out(db, col: Collection) -> CollectionOut:
    out = CollectionOut.model_validate(col)
    out.reference_count = await _count(db, col.id)
    return out


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
        # Inherit project_id from parent if not explicitly set
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
    return await _to_out(db, col)


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
    collections = result.scalars().all()
    return [await _to_out(db, c) for c in collections]


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
        out = await _to_out(db, col)
        child_result = await db.execute(
            select(Collection).where(Collection.parent_id == col.id).order_by(Collection.name)
        )
        out.children = [await load_children(c) for c in child_result.scalars().all()]
        return out

    return [await load_children(r) for r in roots]


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(collection_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await _to_out(db, col)


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
    return await _to_out(db, col)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(collection_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.delete(col)
