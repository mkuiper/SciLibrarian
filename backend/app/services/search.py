from typing import Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reference import Reference


async def full_text_search(
    db: AsyncSession,
    query: str,
    collection_id: Optional[int] = None,
    source_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Reference], int]:
    terms = query.lower().split() if query else []

    stmt = select(Reference).options(selectinload(Reference.tags))

    if terms:
        conditions = []
        for term in terms[:8]:
            conditions.append(
                or_(
                    func.lower(Reference.title).contains(term),
                    func.lower(Reference.abstract).contains(term),
                    func.lower(Reference.summary).contains(term),
                    func.lower(Reference.authors).contains(term),
                    func.lower(Reference.full_text).contains(term),
                )
            )
        stmt = stmt.where(or_(*conditions))

    if collection_id is not None:
        stmt = stmt.where(Reference.collection_id == collection_id)

    if source_type:
        stmt = stmt.where(Reference.source_type == source_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Reference.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all(), total
