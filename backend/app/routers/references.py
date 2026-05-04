from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import DB, CurrentUser
from app.models.reference import Reference, ReferenceTag
from app.schemas.reference import ReferenceCreate, ReferenceUpdate, ReferenceOut
from app.services import ingestion

router = APIRouter(prefix="/references", tags=["references"])


async def _attach_tags(db: DB, ref: Reference, tags: list[str]):
    for existing in ref.tags:
        await db.delete(existing)
    for tag in tags:
        t = tag.strip().lower()
        if t:
            db.add(ReferenceTag(reference_id=ref.id, tag=t))


@router.post("/upload", response_model=ReferenceOut, status_code=201)
async def upload_pdf(
    file: UploadFile = File(...),
    collection_id: Optional[int] = Form(None),
    model: str = Form("claude-sonnet-4-6"),
    db: DB = None,
    current_user: CurrentUser = None,
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.max_upload_mb}MB)")

    meta = await ingestion.ingest_pdf(content, file.filename, model)

    ref = Reference(
        title=meta.get("title", file.filename),
        authors=meta.get("authors"),
        year=meta.get("year"),
        source_type=meta.get("source_type", "paper"),
        abstract=meta.get("abstract"),
        summary=meta.get("summary"),
        url=meta.get("url"),
        file_path=meta.get("file_path"),
        file_name=meta.get("file_name"),
        full_text=meta.get("full_text"),
        collection_id=collection_id,
        created_by=current_user.id,
        extra_metadata=meta.get("extra_metadata"),
    )
    db.add(ref)
    await db.flush()

    for tag in meta.get("tags", []):
        db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))

    await db.flush()
    await db.refresh(ref)

    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref.id))
    return result.scalar_one()


@router.post("/from-url", response_model=ReferenceOut, status_code=201)
async def ingest_from_url(
    url: str,
    collection_id: Optional[int] = None,
    model: str = "claude-sonnet-4-6",
    db: DB = None,
    current_user: CurrentUser = None,
):
    meta = await ingestion.ingest_url(url, model)

    ref = Reference(
        title=meta.get("title", url),
        authors=meta.get("authors"),
        year=meta.get("year"),
        source_type=meta.get("source_type", "other"),
        abstract=meta.get("abstract"),
        summary=meta.get("summary"),
        url=url,
        full_text=meta.get("full_text"),
        collection_id=collection_id,
        created_by=current_user.id,
        extra_metadata=meta.get("extra_metadata"),
    )
    db.add(ref)
    await db.flush()

    for tag in meta.get("tags", []):
        db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))

    await db.flush()
    await db.refresh(ref)

    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref.id))
    return result.scalar_one()


@router.get("", response_model=list[ReferenceOut])
async def list_references(
    db: DB,
    current_user: CurrentUser,
    collection_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    stmt = select(Reference).options(selectinload(Reference.tags))
    if collection_id is not None:
        stmt = stmt.where(Reference.collection_id == collection_id)
    if source_type:
        stmt = stmt.where(Reference.source_type == source_type)
    stmt = stmt.order_by(Reference.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{ref_id}", response_model=ReferenceOut)
async def get_reference(ref_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    return ref


@router.patch("/{ref_id}", response_model=ReferenceOut)
async def update_reference(ref_id: int, data: ReferenceUpdate, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")

    for field in ["title", "authors", "year", "source_type", "abstract", "summary", "url", "collection_id"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(ref, field, val)

    if data.tags is not None:
        await _attach_tags(db, ref, data.tags)

    await db.flush()
    await db.refresh(ref)
    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref.id))
    return result.scalar_one()


@router.delete("/{ref_id}", status_code=204)
async def delete_reference(ref_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Reference).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    await db.delete(ref)
