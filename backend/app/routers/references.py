import asyncio
import io
import zipfile
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Response
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import DB, CurrentUser
from app.models.collection import Collection
from app.models.reference import Reference, ReferenceTag
from app.schemas.reference import ReferenceCreate, ReferenceUpdate, ReferenceOut
from app.services import ingestion

router = APIRouter(prefix="/references", tags=["references"])


async def _find_duplicate(
    db,
    url: str | None,
    title: str,
    project_id: int | None,
    doi: str | None = None,
    arxiv_id: str | None = None,
) -> Reference | None:
    """Return an existing Reference matching DOI, arXiv ID, URL, or normalised title within the same project."""
    from sqlalchemy import or_
    scope = [Reference.project_id == project_id] if project_id else []

    if doi:
        stmt = select(Reference).where(Reference.doi == doi, *scope)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

    if arxiv_id:
        stmt = select(Reference).where(Reference.arxiv_id == arxiv_id, *scope)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

    if url:
        norm = url.rstrip('/')
        stmt = select(Reference).where(or_(Reference.url == url, Reference.url == norm), *scope)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

    norm_title = title.strip().lower()
    if not norm_title:
        return None
    stmt = select(Reference).where(func.lower(func.trim(Reference.title)) == norm_title, *scope)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _attach_tags(db: DB, ref: Reference, tags: list[str]):
    for existing in ref.tags:
        await db.delete(existing)
    for tag in tags:
        t = tag.strip().lower()
        if t:
            db.add(ReferenceTag(reference_id=ref.id, tag=t))


async def _resolve_project_id(
    db: DB,
    collection_id: Optional[int],
    project_id: Optional[int],
) -> Optional[int]:
    """Keep references project-scoped even when callers only send collection_id."""
    if collection_id is None:
        return project_id

    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if project_id is not None and collection.project_id != project_id:
        raise HTTPException(status_code=400, detail="Collection does not belong to the selected project")
    return collection.project_id or project_id


@router.post("/upload", response_model=ReferenceOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    collection_id: Optional[int] = Form(None),
    project_id: Optional[int] = Form(None),
    model: str = Form("claude-sonnet-4-6"),
    db: DB = None,
    current_user: CurrentUser = None,
):
    from app.services.extractors import is_supported
    if not is_supported(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: PDF, DOCX, TXT, MD, CSV, TSV, XLSX, JSON, PDB, FASTA"
        )

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.max_upload_mb}MB)")

    project_id = await _resolve_project_id(db, collection_id, project_id)
    meta = await ingestion.ingest_file(content, file.filename, model)

    existing = await _find_duplicate(
        db,
        meta.get("url"),
        meta.get("title", file.filename),
        project_id,
        doi=meta.get("doi"),
        arxiv_id=meta.get("arxiv_id"),
    )
    if existing:
        result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == existing.id))
        raise HTTPException(status_code=409, detail={"message": "Duplicate reference", "existing_id": existing.id, "existing_title": existing.title})

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
        doi=meta.get("doi"),
        arxiv_id=meta.get("arxiv_id"),
        collection_id=collection_id,
        project_id=project_id,
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
    project_id: Optional[int] = None,
    model: str = "claude-sonnet-4-6",
    db: DB = None,
    current_user: CurrentUser = None,
):
    project_id = await _resolve_project_id(db, collection_id, project_id)

    # Quick URL + ID dedup before paying for ingestion
    url_doi, url_arxiv_id = ingestion.extract_ids_from_url(url)
    url_dup = await _find_duplicate(db, url, "", project_id, doi=url_doi, arxiv_id=url_arxiv_id)
    if url_dup:
        raise HTTPException(status_code=409, detail={"message": "Duplicate reference", "existing_id": url_dup.id, "existing_title": url_dup.title})

    meta = await ingestion.ingest_url(url, model)

    # Post-ingestion dedup: now we may have a DOI/arxiv_id the URL alone didn't reveal
    title_dup = await _find_duplicate(
        db, None, meta.get("title", url), project_id,
        doi=meta.get("doi"), arxiv_id=meta.get("arxiv_id"),
    )
    if title_dup:
        raise HTTPException(status_code=409, detail={"message": "Duplicate reference", "existing_id": title_dup.id, "existing_title": title_dup.title})

    ref = Reference(
        title=meta.get("title", url),
        authors=meta.get("authors"),
        year=meta.get("year"),
        source_type=meta.get("source_type", "other"),
        abstract=meta.get("abstract"),
        summary=meta.get("summary"),
        url=url,
        full_text=meta.get("full_text"),
        doi=meta.get("doi"),
        arxiv_id=meta.get("arxiv_id"),
        collection_id=collection_id,
        project_id=project_id,
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


@router.get("/stats/summary")
async def stats(db: DB, current_user: CurrentUser, project_id: Optional[int] = None):
    """Aggregate counts for dashboard. Must be declared before /{ref_id} routes."""
    stmt = select(func.count(Reference.id))
    if project_id:
        stmt = stmt.where(Reference.project_id == project_id)
    total = (await db.execute(stmt)).scalar_one()

    by_type_stmt = select(Reference.source_type, func.count(Reference.id))
    if project_id:
        by_type_stmt = by_type_stmt.where(Reference.project_id == project_id)
    by_type_rows = await db.execute(by_type_stmt.group_by(Reference.source_type))
    by_type = {row[0]: row[1] for row in by_type_rows}

    return {"total": total, "by_type": by_type}


@router.get("", response_model=list[ReferenceOut])
async def list_references(
    response: Response,
    db: DB,
    current_user: CurrentUser,
    collection_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    filters = []
    if collection_id is not None:
        filters.append(Reference.collection_id == collection_id)
    if project_id is not None:
        filters.append(Reference.project_id == project_id)
    if source_type:
        filters.append(Reference.source_type == source_type)

    count_stmt = select(func.count(Reference.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()
    response.headers["X-Total-Count"] = str(total)

    stmt = select(Reference).options(selectinload(Reference.tags))
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(Reference.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/batch", response_model=list[ReferenceOut])
async def batch_references(
    db: DB,
    current_user: CurrentUser,
    ids: str = Query(..., description="comma-separated reference IDs"),
    project_id: Optional[int] = Query(None),
):
    """Fetch up to 8 references by ID in a single round-trip — used by the comparison view.

    Optional project_id scopes results to that project (matches the list-endpoint pattern).
    """
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:8]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be comma-separated integers")
    if not id_list:
        return []
    stmt = select(Reference).options(selectinload(Reference.tags)).where(Reference.id.in_(id_list))
    if project_id is not None:
        stmt = stmt.where(Reference.project_id == project_id)
    result = await db.execute(stmt)
    refs = {r.id: r for r in result.scalars().all()}
    return [refs[i] for i in id_list if i in refs]


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

    if data.collection_id is not None:
        ref.project_id = await _resolve_project_id(db, data.collection_id, ref.project_id)

    for field in ["title", "authors", "year", "source_type", "abstract", "summary",
                  "url", "collection_id", "notes", "read_status"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(ref, field, val)
    if data.is_starred is not None:
        ref.is_starred = data.is_starred

    if data.tags is not None:
        await _attach_tags(db, ref, data.tags)

    await db.flush()
    await db.refresh(ref)
    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref.id))
    return result.scalar_one()


@router.post("/{ref_id}/reprocess", response_model=ReferenceOut)
async def reprocess_reference(
    ref_id: int,
    db: DB,
    current_user: CurrentUser,
    model: str = "claude-sonnet-4-6",
):
    """
    Re-run the full ingestion pipeline on an existing reference.
    Useful for references added from the review queue that got empty text,
    or to regenerate summaries with a better model.
    """
    result = await db.execute(select(Reference).options(selectinload(Reference.tags)).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")

    meta = None
    if ref.file_path and Path(ref.file_path).exists():
        # Re-ingest from stored PDF
        file_bytes = Path(ref.file_path).read_bytes()
        meta = await ingestion.ingest_pdf(file_bytes, ref.file_name or "document.pdf", model)
    elif ref.url:
        # Re-ingest from URL (now PDF-aware)
        meta = await ingestion.ingest_url(ref.url, model)

    if not meta:
        raise HTTPException(status_code=400, detail="No file or URL to reprocess")

    # Update fields
    for field in ["title", "authors", "year", "source_type", "abstract", "summary", "full_text", "extra_metadata"]:
        val = meta.get(field)
        if val:
            setattr(ref, field, val)

    if meta.get("file_path") and not ref.file_path:
        ref.file_path = meta["file_path"]
        ref.file_name = meta.get("file_name")

    # Replace tags
    for tag in ref.tags:
        await db.delete(tag)
    await db.flush()
    for tag in meta.get("tags", []):
        if tag.strip():
            db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))

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


@router.get("/{ref_id}/citations", response_model=dict)
async def reference_citations(ref_id: int, db: DB, current_user: CurrentUser):
    """Return papers that cite or are cited by this reference, via Semantic Scholar.

    Each paper carries `in_library_id` when we already have it (matched by DOI / arXiv ID).
    Result is cached in-process for 1 hour per reference.
    """
    from app.services.citations import fetch_citations

    result = await db.execute(select(Reference).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    return await fetch_citations(db, ref)


@router.get("/{ref_id}/file")
async def serve_file(ref_id: int, db: DB, current_user: CurrentUser):
    """Serve the uploaded PDF file for in-browser viewing."""
    result = await db.execute(select(Reference).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref or not ref.file_path:
        raise HTTPException(status_code=404, detail="No file attached to this reference")
    path = Path(ref.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=ref.file_name or path.name,
        headers={"Content-Disposition": "inline"},
    )


@router.get("/{ref_id}/bibtex", response_class=PlainTextResponse)
async def export_bibtex(ref_id: int, db: DB, current_user: CurrentUser):
    """Export reference as BibTeX."""
    result = await db.execute(select(Reference).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    return _to_bibtex(ref)


BATCH_LIMIT = 30  # max items per batch request


async def _ingest_pdf_and_save(
    db, content: bytes, filename: str, model: str,
    collection_id: Optional[int], project_id: Optional[int], user_id: int,
) -> dict:
    project_id = await _resolve_project_id(db, collection_id, project_id)
    meta = await ingestion.ingest_file(content, filename, model)
    ref = Reference(
        title=meta.get("title", filename),
        authors=meta.get("authors"),
        year=meta.get("year"),
        source_type=meta.get("source_type", "paper"),
        abstract=meta.get("abstract"),
        summary=meta.get("summary"),
        url=meta.get("url"),
        file_path=meta.get("file_path"),
        file_name=meta.get("file_name"),
        full_text=meta.get("full_text"),
        doi=meta.get("doi"),
        arxiv_id=meta.get("arxiv_id"),
        collection_id=collection_id,
        project_id=project_id,
        created_by=user_id,
        extra_metadata=meta.get("extra_metadata"),
    )
    db.add(ref)
    await db.flush()
    for tag in meta.get("tags", []):
        db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))
    await db.flush()
    return {"title": meta.get("title", filename), "id": ref.id, "status": "ok"}


@router.post("/upload-bulk")
async def upload_bulk(
    files: list[UploadFile] = File(...),
    collection_id: Optional[int] = Form(None),
    project_id: Optional[int] = Form(None),
    model: str = Form("claude-sonnet-4-6"),
    db: DB = None,
    current_user: CurrentUser = None,
):
    """Ingest multiple files in one request. Max 30 files. Supports all file types."""
    from app.services.extractors import is_supported
    valid_files = [f for f in files if is_supported(f.filename)][:BATCH_LIMIT]
    if not valid_files:
        raise HTTPException(status_code=400, detail="No supported files found in upload")

    succeeded, failed = [], []
    for f in valid_files:
        try:
            content = await f.read()
            result = await _ingest_pdf_and_save(
                db, content, f.filename, model, collection_id, project_id, current_user.id
            )
            succeeded.append(result)
        except Exception as e:
            failed.append({"filename": f.filename, "error": str(e)})

    return {
        "total": len(valid_files),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "results": succeeded,
        "errors": failed,
    }


@router.post("/upload-zip")
async def upload_zip(
    file: UploadFile = File(...),
    collection_id: Optional[int] = Form(None),
    project_id: Optional[int] = Form(None),
    model: str = Form("claude-sonnet-4-6"),
    db: DB = None,
    current_user: CurrentUser = None,
):
    """Ingest all PDFs from an uploaded ZIP archive. Max 30 PDFs."""
    content = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Not a valid ZIP file")

    pdf_names = [
        n for n in zf.namelist()
        if n.lower().endswith(".pdf") and not n.startswith("__MACOSX")
    ][:BATCH_LIMIT]

    if not pdf_names:
        raise HTTPException(status_code=400, detail="No PDF files found in ZIP")

    succeeded, failed = [], []
    for name in pdf_names:
        try:
            pdf_bytes = zf.read(name)
            filename = Path(name).name
            result = await _ingest_pdf_and_save(
                db, pdf_bytes, filename, model, collection_id, project_id, current_user.id
            )
            succeeded.append(result)
        except Exception as e:
            failed.append({"filename": name, "error": str(e)})

    return {
        "total": len(pdf_names),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "results": succeeded,
        "errors": failed,
    }


class BulkUrlRequest(BaseModel):
    urls: list[str]
    collection_id: Optional[int] = None
    project_id: Optional[int] = None
    model: str = "claude-sonnet-4-6"


@router.post("/from-urls-bulk")
async def from_urls_bulk(data: BulkUrlRequest, db: DB, current_user: CurrentUser):
    """Ingest multiple URLs concurrently. Max 30 URLs."""
    urls = [u.strip() for u in data.urls if u.strip()][:BATCH_LIMIT]
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    project_id = await _resolve_project_id(db, data.collection_id, data.project_id)

    async def ingest_one(url: str) -> dict:
        try:
            meta = await ingestion.ingest_url(url, data.model)
            return {"url": url, "meta": meta, "status": "ok"}
        except Exception as e:
            return {"url": url, "status": "error", "error": str(e)}

    # Fetch and summarize concurrently, then write sequentially with one DB session.
    sem = asyncio.Semaphore(4)

    async def bounded(url):
        async with sem:
            return await ingest_one(url)

    ingest_results = await asyncio.gather(*[bounded(u) for u in urls])

    succeeded, failed = [], []
    for result in ingest_results:
        if result["status"] == "error":
            failed.append({"url": result["url"], "status": "error", "error": result["error"]})
            continue

        try:
            url = result["url"]
            meta = result["meta"]
            ref = Reference(
                title=meta.get("title", url),
                authors=meta.get("authors"),
                year=meta.get("year"),
                source_type=meta.get("source_type", "other"),
                abstract=meta.get("abstract"),
                summary=meta.get("summary"),
                url=url,
                full_text=meta.get("full_text"),
                doi=meta.get("doi"),
                arxiv_id=meta.get("arxiv_id"),
                collection_id=data.collection_id,
                project_id=project_id,
                created_by=current_user.id,
                extra_metadata=meta.get("extra_metadata"),
            )
            db.add(ref)
            await db.flush()
            for tag in meta.get("tags", []):
                db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))
            await db.flush()
            succeeded.append({"url": url, "title": meta.get("title", url), "id": ref.id, "status": "ok"})
        except Exception as e:
            failed.append({"url": result["url"], "status": "error", "error": str(e)})

    return {
        "total": len(urls),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "results": succeeded,
        "errors": failed,
    }


def _to_bibtex(ref: Reference) -> str:
    authors = ref.authors or "Unknown"
    year = str(ref.year) if ref.year else "nd"
    first_author_last = authors.split(",")[0].strip().split()[-1] if authors else "Unknown"
    key = f"{first_author_last}{year}"

    entry_type = {
        "paper": "article",
        "policy": "techreport",
        "model_card": "misc",
        "evaluation": "techreport",
        "government": "techreport",
        "other": "misc",
    }.get(ref.source_type, "misc")

    lines = [
        f"@{entry_type}{{{key},",
        f'  title = {{{ref.title}}},',
        f'  author = {{{authors}}},',
        f'  year = {{{year}}},',
    ]
    if ref.url:
        lines.append(f'  url = {{{ref.url}}},')
    if ref.doi:
        lines.append(f'  doi = {{{ref.doi}}},')
    elif ref.extra_metadata and ref.extra_metadata.get("doi"):
        lines.append(f'  doi = {{{ref.extra_metadata["doi"]}}},')
    if ref.arxiv_id:
        lines.append(f'  eprint = {{{ref.arxiv_id}}},')
        lines.append(f'  archivePrefix = {{arXiv}},')
    if ref.extra_metadata and ref.extra_metadata.get("journal"):
        lines.append(f'  journal = {{{ref.extra_metadata["journal"]}}},')
    lines.append("}")
    return "\n".join(lines)
