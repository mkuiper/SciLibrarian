"""
Background scheduler for automated tasks:
  - Monthly digest generation (1st of each month)
  - Search monitor execution (daily/weekly as configured)

Uses APScheduler with an in-process AsyncIOScheduler.
"""
from datetime import datetime, timezone
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def _run_monitors():
    from app.database import AsyncSessionLocal
    from app.services.proactive_search import run_all_due_monitors
    async with AsyncSessionLocal() as db:
        result = await run_all_due_monitors(db)
        logger.info(f"Scheduled monitor run: {result}")


async def _run_monthly_digests():
    """Generate digests for all projects on the 1st of each month."""
    from app.database import AsyncSessionLocal
    from app.services.digest import generate_digest
    from sqlalchemy import select
    from app.models.project import Project

    now = datetime.now(timezone.utc)
    from datetime import timedelta
    import calendar

    last_month = now.month - 1 or 12
    year = now.year if now.month > 1 else now.year - 1
    _, last_day = calendar.monthrange(year, last_month)
    period_start = datetime(year, last_month, 1, tzinfo=timezone.utc)
    period_end = datetime(year, last_month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project))
        projects = result.scalars().all()
        for project in projects:
            try:
                model = (project.settings or {}).get("librarian_model", "claude-sonnet-4-6")
                await generate_digest(db, project.id, project.created_by, period_start, period_end, model)
                logger.info(f"Generated digest for project {project.id}")
            except Exception as e:
                logger.error(f"Failed to generate digest for project {project.id}: {e}")


def start_scheduler():
    scheduler = get_scheduler()

    # Run monitors every 6 hours (they self-gate on frequency)
    scheduler.add_job(
        _run_monitors,
        CronTrigger(hour="*/6"),
        id="run_monitors",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Generate monthly digests on the 1st of each month at 08:00 UTC
    scheduler.add_job(
        _run_monthly_digests,
        CronTrigger(day=1, hour=8, minute=0),
        id="monthly_digest",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("Background scheduler started (monitors every 6h, digests monthly)")


def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
