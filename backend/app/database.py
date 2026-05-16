import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Each migration runs in its own transaction so one failure doesn't block others.
# 'references' is a reserved SQL word — must be double-quoted.
_MIGRATIONS = [
    'ALTER TABLE projects ADD COLUMN IF NOT EXISTS domains JSONB DEFAULT \'[]\'::jsonb',
    'ALTER TABLE projects ADD COLUMN IF NOT EXISTS settings JSONB',
    'ALTER TABLE collections ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)',
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)',
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS is_starred BOOLEAN NOT NULL DEFAULT FALSE',
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS read_status VARCHAR(20) NOT NULL DEFAULT \'unread\'',
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS notes TEXT',
    'ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS collection_id INTEGER REFERENCES collections(id)',
    'ALTER TABLE search_monitors ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)',
    'ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)',
    # Round 1: FTS index (weighted: title A > abstract B > summary C)
    'CREATE INDEX IF NOT EXISTS ix_references_fts ON "references" USING GIN ('
    ' to_tsvector(\'english\', concat(coalesce(title,\'\'), \' \', coalesce(abstract,\'\'), \' \', coalesce(summary,\'\'))))',
    # Round 8: Monitor quality metrics
    'ALTER TABLE search_monitors ADD COLUMN IF NOT EXISTS approve_count INTEGER NOT NULL DEFAULT 0',
    'ALTER TABLE search_monitors ADD COLUMN IF NOT EXISTS reject_count INTEGER NOT NULL DEFAULT 0',
    # Cycle 10: DOI / arXiv ID columns for stronger deduplication
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS doi VARCHAR(200)',
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS arxiv_id VARCHAR(50)',
    'CREATE INDEX IF NOT EXISTS ix_references_doi_project ON "references" (project_id, doi)',
    'CREATE INDEX IF NOT EXISTS ix_references_arxiv_project ON "references" (project_id, arxiv_id)',
    'ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS doi VARCHAR(200)',
    'ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS arxiv_id VARCHAR(50)',
    # Cycle 11: Weighted full-text search via generated tsvector column.
    # Title=A, abstract=B, summary=C, full_text=D so title matches still outrank body matches.
    'ALTER TABLE "references" ADD COLUMN IF NOT EXISTS tsv tsvector GENERATED ALWAYS AS ('
    " setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    " setweight(to_tsvector('english', coalesce(abstract, '')), 'B') || "
    " setweight(to_tsvector('english', coalesce(summary, '')), 'C') || "
    " setweight(to_tsvector('english', coalesce(full_text, '')), 'D')"
    ') STORED',
    'CREATE INDEX IF NOT EXISTS ix_references_tsv ON "references" USING GIN (tsv)',
    'DROP INDEX IF EXISTS ix_references_fts',
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run each migration in its own transaction — one failure won't block others
    for migration in _MIGRATIONS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(migration))
            logger.debug(f"Migration OK: {migration[:60]}")
        except Exception as e:
            logger.debug(f"Migration skipped ({e}): {migration[:60]}")
