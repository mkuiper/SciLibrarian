"""
Activity timeline for a project.

Merges events from every table that records something the user might care about:
references added, queue decisions, restructure actions, literature-review
generations, monitor runs, digests. Each event has a uniform shape so the UI
can render the whole stream from one endpoint.

Per-table SELECTs run **sequentially** on the request session. The first draft
of this service used `asyncio.gather` and got bitten in Cycle 24 review:
SQLAlchemy's `AsyncSession` is not safe for concurrent operations even for
read-only queries — it owns a single DBAPI connection and raises
`InvalidRequestError` under interleaved use. Sequential is fast enough at
this scale (6 indexed queries, sub-second total).

The `since` filter pushes down to SQL in each fan-out so we don't fetch rows
we'll throw away. Per-table limit equals the requested global limit so a
single hot table can fill the entire feed if it needs to.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.literature_review import LiteratureReview
from app.models.project import Digest
from app.models.reference import Reference
from app.models.review_queue import ReviewQueueItem
from app.models.search_monitor import SearchMonitor

logger = logging.getLogger(__name__)


def _event(
    *,
    source_id: int,
    timestamp: datetime,
    event_type: str,
    title: str,
    description: Optional[str] = None,
    link: Optional[str] = None,
    actor_id: Optional[int] = None,
) -> dict:
    """One activity entry — uniform across the eight source tables.

    `source_id` is the primary key of the row in its source table. Combined
    with `type`, it forms a globally unique identifier for the event — needed
    because multiple events of the same type can share a timestamp when the
    underlying rows were inserted in one transaction (Postgres `now()` returns
    the transaction start time, so e.g. a bulk reference upload produces N
    `reference_added` events all sharing `created_at`). Cycle 24 Codex review
    catch.
    """
    return {
        "source_id": source_id,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "type": event_type,
        "title": title,
        "description": description,
        "link": link,
        "actor_id": actor_id,
    }


async def _recent_references(
    db: AsyncSession, project_id: int, limit: int, since: Optional[datetime] = None,
) -> list[dict]:
    stmt = select(Reference).where(Reference.project_id == project_id)
    if since is not None:
        stmt = stmt.where(Reference.created_at >= since)
    rows = (await db.execute(stmt.order_by(Reference.created_at.desc()).limit(limit))).scalars().all()
    return [
        _event(
            source_id=r.id,
            timestamp=r.created_at,
            event_type="reference_added",
            title=r.title or "(untitled reference)",
            description=f"Added to library — {r.source_type.replace('_', ' ')}" if r.source_type else "Added to library",
            link=f"/references/{r.id}",
            actor_id=r.created_by,
        )
        for r in rows
    ]


async def _recent_decisions(
    db: AsyncSession, project_id: int, limit: int, since: Optional[datetime] = None,
) -> list[dict]:
    stmt = (
        select(ReviewQueueItem)
        .where(
            ReviewQueueItem.project_id == project_id,
            ReviewQueueItem.reviewed_at.isnot(None),
        )
    )
    if since is not None:
        stmt = stmt.where(ReviewQueueItem.reviewed_at >= since)
    rows = (await db.execute(stmt.order_by(ReviewQueueItem.reviewed_at.desc()).limit(limit))).scalars().all()
    out = []
    for item in rows:
        verdict = "approved" if item.status == "approved" else "rejected"
        out.append(_event(
            source_id=item.id,
            timestamp=item.reviewed_at,
            event_type=f"queue_{verdict}",
            title=item.title or "(untitled queue item)",
            description=(
                f"Review queue item {verdict}"
                + (f" — {item.rejection_reason}" if verdict == "rejected" and item.rejection_reason else "")
            ),
            link=f"/review?status={verdict}",
            actor_id=item.reviewed_by,
        ))
    return out


async def _recent_restructure_actions(
    db: AsyncSession, project_id: int, limit: int, since: Optional[datetime] = None,
) -> list[dict]:
    from sqlalchemy import text as sa_text
    sql = (
        "SELECT id, user_id, action_type, action_payload, result, applied_at "
        "FROM restructure_actions WHERE project_id = :p"
    )
    params: dict = {"p": project_id, "l": limit}
    if since is not None:
        sql += " AND applied_at >= :since"
        params["since"] = since
    sql += " ORDER BY applied_at DESC LIMIT :l"
    rows = await db.execute(sa_text(sql), params)
    out = []
    for row in rows.mappings():
        atype = row["action_type"]
        payload = row["action_payload"] or {}
        result = row["result"] or {}
        # Mirror the friendly descriptions used on RestructurePage so the
        # activity feed reads the same way the user saw the action there.
        if atype == "create_collection":
            description = (
                f"Created \"{payload.get('name', '?')}\" with {result.get('moved_count', 0)} reference(s)"
                if result.get("moved_count")
                else f"Created \"{payload.get('name', '?')}\""
            )
        elif atype == "rename_collection":
            description = f"Renamed \"{result.get('previous_name', '?')}\" → \"{result.get('name', '?')}\""
        elif atype == "move_references":
            description = f"Moved {result.get('moved_count', 0)} reference(s) into collection {result.get('target_collection_id', '?')}"
        elif atype == "merge_collections":
            description = f"Merged \"{result.get('merged_from_name', '?')}\" into collection {result.get('target_collection_id', '?')}"
        else:
            description = atype
        out.append(_event(
            source_id=row["id"],
            timestamp=row["applied_at"],
            event_type=f"restructure_{atype}",
            title=description,
            description=None,
            link="/restructure",
            actor_id=row["user_id"],
        ))
    return out


async def _recent_literature_reviews(
    db: AsyncSession, project_id: int, limit: int, since: Optional[datetime] = None,
) -> list[dict]:
    stmt = select(LiteratureReview).where(LiteratureReview.project_id == project_id)
    if since is not None:
        stmt = stmt.where(LiteratureReview.created_at >= since)
    rows = (await db.execute(stmt.order_by(LiteratureReview.created_at.desc()).limit(limit))).scalars().all()
    return [
        _event(
            source_id=r.id,
            timestamp=r.created_at,
            event_type="literature_review_generated",
            title=f"Literature review v{r.version}",
            description=f"Synthesised from {r.ref_count_at_generation} references using {r.model_used or 'default model'}",
            link="/literature-review",
            actor_id=r.created_by,
        )
        for r in rows
    ]


async def _recent_monitor_runs(
    db: AsyncSession, project_id: int, limit: int, since: Optional[datetime] = None,
) -> list[dict]:
    """Monitors don't have a per-run history table — only `last_run`. So this
    surfaces each monitor once, with its most recent run time. Useful but not
    a full audit trail; flagged for a future cycle if we want per-run history.
    """
    stmt = select(SearchMonitor).where(
        SearchMonitor.project_id == project_id,
        SearchMonitor.last_run.isnot(None),
    )
    if since is not None:
        stmt = stmt.where(SearchMonitor.last_run >= since)
    rows = (await db.execute(stmt.order_by(SearchMonitor.last_run.desc()).limit(limit))).scalars().all()
    return [
        _event(
            source_id=m.id,
            timestamp=m.last_run,
            event_type="monitor_ran",
            title=f"Monitor \"{m.name}\" ran",
            description=f"{m.approve_count or 0} approved / {m.reject_count or 0} rejected lifetime",
            link="/monitors",
            actor_id=m.user_id,
        )
        for m in rows
    ]


async def _recent_digests(
    db: AsyncSession, project_id: int, limit: int, since: Optional[datetime] = None,
) -> list[dict]:
    stmt = select(Digest).where(Digest.project_id == project_id)
    if since is not None:
        stmt = stmt.where(Digest.created_at >= since)
    rows = (await db.execute(stmt.order_by(Digest.created_at.desc()).limit(limit))).scalars().all()
    return [
        _event(
            source_id=d.id,
            timestamp=d.created_at,
            event_type="digest_generated",
            title=d.title or "Digest",
            description=f"{d.new_references} new references over the period",
            link="/digests",
            actor_id=d.created_by,
        )
        for d in rows
    ]


async def project_activity(
    db: AsyncSession,
    project_id: int,
    *,
    limit: int = 50,
    since: Optional[datetime] = None,
) -> list[dict]:
    """Chronological merge of every recorded event for the project.

    Runs each table query sequentially on the shared request session — SQLAlchemy's
    AsyncSession isn't safe under `asyncio.gather`, even read-only. Per-table limit
    equals the global limit so a single hot table can fill the entire feed.
    """
    # Normalise to UTC so the SQL-side >= comparison is consistent regardless
    # of the offset the client supplied (Cycle 24 review caught the
    # lexicographic-iso-string bug; comparing datetime objects here makes it
    # impossible).
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    sources = (
        _recent_references,
        _recent_decisions,
        _recent_restructure_actions,
        _recent_literature_reviews,
        _recent_monitor_runs,
        _recent_digests,
    )
    events: list[dict] = []
    for fn in sources:
        try:
            events.extend(await fn(db, project_id, limit, since))
        except Exception as e:
            logger.warning(f"activity source {fn.__name__} failed: {e}")

    # Filter defensively — drop rows without a usable timestamp.
    events = [e for e in events if e["timestamp"]]
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events[:limit]
