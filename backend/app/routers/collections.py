from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DB, CurrentUser
from app.models.collection import Collection
from app.models.reference import Reference
from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionOut

router = APIRouter(prefix="/collections", tags=["collections"])


def build_path(parent_path: str, collection_id: int) -> str:
    return f"{parent_path}{collection_id}/"


@router.post("", response_model=CollectionOut, status_code=201)
async def create_collection(data: CollectionCreate, db: DB, current_user: CurrentUser):
    parent_path = "/"
    if data.parent_id:
        result = await db.execute(select(Collection).where(Collection.id == data.parent_id))
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent collection not found")
        parent_path = parent.path

    col = Collection(
        name=data.name,
        description=data.description,
        parent_id=data.parent_id,
        path=parent_path,
        created_by=current_user.id,
    )
    db.add(col)
    await db.flush()
    col.path = build_path(parent_path, col.id)
    await db.flush()
    await db.refresh(col)

    count = (await db.execute(select(func.count(Reference.id)).where(Reference.collection_id == col.id))).scalar_one()
    out = CollectionOut.model_validate(col)
    out.reference_count = count
    return out


@router.get("", response_model=list[CollectionOut])
async def list_collections(db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).order_by(Collection.path))
    collections = result.scalars().all()

    counts = {}
    for col in collections:
        count = (await db.execute(select(func.count(Reference.id)).where(Reference.collection_id == col.id))).scalar_one()
        counts[col.id] = count

    out = []
    for col in collections:
        o = CollectionOut.model_validate(col)
        o.reference_count = counts.get(col.id, 0)
        out.append(o)
    return out


@router.get("/tree", response_model=list[CollectionOut])
async def get_collection_tree(db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.parent_id == None).order_by(Collection.name))
    roots = result.scalars().all()

    async def load_children(col: Collection) -> CollectionOut:
        count = (await db.execute(select(func.count(Reference.id)).where(Reference.collection_id == col.id))).scalar_one()
        out = CollectionOut.model_validate(col)
        out.reference_count = count
        child_result = await db.execute(select(Collection).where(Collection.parent_id == col.id).order_by(Collection.name))
        children = child_result.scalars().all()
        out.children = [await load_children(c) for c in children]
        return out

    return [await load_children(r) for r in roots]


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(collection_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    count = (await db.execute(select(func.count(Reference.id)).where(Reference.collection_id == col.id))).scalar_one()
    out = CollectionOut.model_validate(col)
    out.reference_count = count
    return out


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(collection_id: int, data: CollectionUpdate, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    if data.name is not None:
        col.name = data.name
    if data.description is not None:
        col.description = data.description
    await db.flush()
    await db.refresh(col)
    count = (await db.execute(select(func.count(Reference.id)).where(Reference.collection_id == col.id))).scalar_one()
    out = CollectionOut.model_validate(col)
    out.reference_count = count
    return out


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(collection_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.delete(col)
