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
