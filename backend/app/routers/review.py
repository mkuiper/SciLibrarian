import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
from app.models.review_queue import ReviewQueueItem
from app.models.reference import Reference, ReferenceTag
from app.models.search_monitor import SearchMonitor
from app.schemas.review_queue import ReviewQueueItemOut
from app.schemas.search_monitor import SearchMonitorCreate, SearchMonitorUpdate, SearchMonitorOut
from app.services.access import user_can_access_project
from app.services.proactive_search import run_monitor, suggest_monitor_improvements
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])


class ReviewDecision(BaseModel):
    action: str                          # "approve" or "reject"
    collection_id: Optional[int] = None
    model: str = ""                      # model for full ingestion (empty = use project default)
    full_ingest: bool = True             # whether to run full ingestion pipeline on approve
    rejection_reason: Optional[str] = None  # optional free-text on reject; fed into monitor learning


@router.get("/queue", response_model=list[ReviewQueueItemOut])
async def get_queue(
    db: DB,
    current_user: CurrentUser,
    status: str = Query("pending"),
    project_id: Optional[int] = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
):
    # Scope to projects the user owns. project_id is an optional further filter
    # within that scope; without it we still avoid leaking other users' queues.
    from app.models.project import Project
    from sqlalchemy import or_ as _or_
    user_projects = select(Project.id).where(Project.created_by == current_user.id).scalar_subquery()
    stmt = (
        select(ReviewQueueItem)
        .where(
            ReviewQueueItem.status == status,
            _or_(ReviewQueueItem.project_id.in_(user_projects), ReviewQueueItem.project_id.is_(None)),
        )
        .order_by(ReviewQueueItem.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if project_id is not None:
        stmt = stmt.where(ReviewQueueItem.project_id == project_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/queue/{item_id}/decide", response_model=ReviewQueueItemOut)
async def decide(item_id: int, decision: ReviewDecision, db: DB, current_user: CurrentUser):
    result = await db.execute(select(ReviewQueueItem).where(ReviewQueueItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    # Ownership: deciding on a queue item that belongs to a project you don't
    # own would be a write into someone else's data.
    if item.project_id is not None and not await user_can_access_project(db, item.project_id, current_user.id):
        raise HTTPException(status_code=404, detail="Queue item not found")

    if decision.action == "approve":
        model = decision.model or settings.default_ingestion_model
        ref = await _approve_item(db, item, decision.collection_id, item.project_id, current_user.id, model, decision.full_ingest)
        db.add(ref)
        item.status = "approved"
    elif decision.action == "reject":
        item.status = "rejected"
        if decision.rejection_reason:
            item.rejection_reason = decision.rejection_reason.strip()[:1000] or None
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)

    # Update monitor quality stats
    if item.monitor_id:
        monitor_result = await db.execute(select(SearchMonitor).where(SearchMonitor.id == item.monitor_id))
        monitor = monitor_result.scalar_one_or_none()
        if monitor:
            if decision.action == "approve":
                monitor.approve_count = (monitor.approve_count or 0) + 1
            else:
                monitor.reject_count = (monitor.reject_count or 0) + 1

    await db.flush()
    await db.refresh(item)
    return item


async def _approve_item(
    db, item: ReviewQueueItem, collection_id: Optional[int], project_id: Optional[int],
    user_id: int, model: str, full_ingest: bool
) -> Reference:
    """
    Create a Reference from a review queue item.
    If full_ingest=True and the item has a URL, runs the complete ingestion
    pipeline (fetch page, extract text, Alexandria summary + tags).
    Falls back to the scraped metadata if ingestion fails.
    """
    if full_ingest and item.url:
        try:
            from app.services.ingestion import ingest_url
            meta = await ingest_url(item.url, model)
            ref = Reference(
                title=meta.get("title") or item.title,
                authors=meta.get("authors") or item.authors,
                year=meta.get("year") or item.year,
                source_type=meta.get("source_type", "paper"),
                abstract=meta.get("abstract") or item.abstract,
                summary=meta.get("summary"),
                url=item.url,
                full_text=meta.get("full_text"),
                doi=meta.get("doi") or item.doi,
                arxiv_id=meta.get("arxiv_id") or item.arxiv_id,
                collection_id=collection_id,
                project_id=project_id,
                created_by=user_id,
                extra_metadata=meta.get("extra_metadata"),
            )
            db.add(ref)
            await db.flush()  # populates ref.id before tag inserts
            for tag in meta.get("tags", []):
                if tag.strip():
                    db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))
            logger.info(f"Full ingestion completed for queue item {item.id}: {ref.title[:60]}")
            return ref
        except Exception as e:
            logger.warning(f"Full ingestion failed for {item.url}, falling back to scraped metadata: {e}")

    # Fallback: use scraped metadata from the monitor search
    return Reference(
        title=item.title,
        authors=item.authors,
        year=item.year,
        source_type="paper",
        abstract=item.abstract,
        url=item.url,
        doi=item.doi,
        arxiv_id=item.arxiv_id,
        collection_id=collection_id,
        project_id=project_id,
        created_by=user_id,
        extra_metadata=item.extra_metadata,
    )


# ── Monitors ──────────────────────────────────────────────────────────────────

@router.get("/monitors", response_model=list[SearchMonitorOut])
async def list_monitors(db: DB, current_user: CurrentUser, project_id: Optional[int] = Query(None)):
    stmt = select(SearchMonitor).where(SearchMonitor.user_id == current_user.id)
    if project_id is not None:
        stmt = stmt.where(SearchMonitor.project_id == project_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/monitors", response_model=SearchMonitorOut, status_code=201)
async def create_monitor(data: SearchMonitorCreate, db: DB, current_user: CurrentUser):
    monitor = SearchMonitor(user_id=current_user.id, **data.model_dump())
    db.add(monitor)
    await db.flush()
    await db.refresh(monitor)
    return monitor


@router.patch("/monitors/{monitor_id}", response_model=SearchMonitorOut)
async def update_monitor(monitor_id: int, data: SearchMonitorUpdate, db: DB, current_user: CurrentUser):
    result = await db.execute(select(SearchMonitor).where(SearchMonitor.id == monitor_id, SearchMonitor.user_id == current_user.id))
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(monitor, field, val)
    await db.flush()
    await db.refresh(monitor)
    return monitor


@router.delete("/monitors/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(SearchMonitor).where(SearchMonitor.id == monitor_id, SearchMonitor.user_id == current_user.id))
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await db.delete(monitor)


@router.post("/monitors/{monitor_id}/run", response_model=dict)
async def run_monitor_now(monitor_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(SearchMonitor).where(SearchMonitor.id == monitor_id, SearchMonitor.user_id == current_user.id))
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    added = await run_monitor(db, monitor)
    return {"added_to_queue": added}


@router.post("/monitors/{monitor_id}/suggest-improvements", response_model=dict)
async def suggest_improvements(monitor_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(SearchMonitor).where(SearchMonitor.id == monitor_id, SearchMonitor.user_id == current_user.id))
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return await suggest_monitor_improvements(db, monitor)
