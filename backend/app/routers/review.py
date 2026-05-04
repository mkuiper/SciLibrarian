from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
from app.models.review_queue import ReviewQueueItem
from app.models.reference import Reference
from app.models.search_monitor import SearchMonitor
from app.schemas.review_queue import ReviewQueueItemOut, ReviewDecision
from app.schemas.search_monitor import SearchMonitorCreate, SearchMonitorUpdate, SearchMonitorOut
from app.services.proactive_search import run_monitor

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=list[ReviewQueueItemOut])
async def get_queue(
    db: DB,
    current_user: CurrentUser,
    status: str = Query("pending"),
    limit: int = Query(50),
    offset: int = Query(0),
):
    stmt = (
        select(ReviewQueueItem)
        .where(ReviewQueueItem.status == status)
        .order_by(ReviewQueueItem.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/queue/{item_id}/decide", response_model=ReviewQueueItemOut)
async def decide(item_id: int, decision: ReviewDecision, db: DB, current_user: CurrentUser):
    result = await db.execute(select(ReviewQueueItem).where(ReviewQueueItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    if decision.action == "approve":
        ref = Reference(
            title=item.title,
            authors=item.authors,
            year=item.year,
            source_type="paper",
            abstract=item.abstract,
            url=item.url,
            collection_id=decision.collection_id,
            created_by=current_user.id,
        )
        db.add(ref)
        item.status = "approved"
    elif decision.action == "reject":
        item.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="action must be approve or reject")

    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(item)
    return item


@router.get("/monitors", response_model=list[SearchMonitorOut])
async def list_monitors(db: DB, current_user: CurrentUser):
    result = await db.execute(select(SearchMonitor).where(SearchMonitor.user_id == current_user.id))
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
