from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

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


# Columns added after the initial schema — applied idempotently on every startup.
# These are safe to run repeatedly (ADD COLUMN IF NOT EXISTS).
_MIGRATIONS = [
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS domains JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS settings JSONB",
    "ALTER TABLE collections ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)",
    "ALTER TABLE references ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)",
    "ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS collection_id INTEGER REFERENCES collections(id)",
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Apply incremental column additions for tables that already exist
        for migration in _MIGRATIONS:
            try:
                await conn.execute(text(migration))
            except Exception:
                pass  # Column likely already exists or table not yet created
