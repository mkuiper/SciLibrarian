from typing import Optional
from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reference import Reference


async def full_text_search(
    db: AsyncSession,
    query: str,
    collection_id: Optional[int] = None,
    project_id: Optional[int] = None,
    source_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    tag: Optional[str] = None,
    read_status: Optional[str] = None,
    starred: Optional[bool] = None,
) -> tuple[list[Reference], list[str | None], int]:
    """
    PostgreSQL full-text search with weighted ranking and ts_headline snippets.
    Falls back to ilike when the query string is empty (list mode).
    Returns (refs, snippets, total) where snippets[i] is None when no query was given.
    """
    q = query.strip() if query else ""

    base_filters = []
    if collection_id is not None:
        base_filters.append(Reference.collection_id == collection_id)
    if project_id is not None:
        base_filters.append(Reference.project_id == project_id)
    if source_type:
        base_filters.append(Reference.source_type == source_type)
    if year_from is not None:
        base_filters.append(Reference.year >= year_from)
    if year_to is not None:
        base_filters.append(Reference.year <= year_to)
    if read_status:
        base_filters.append(Reference.read_status == read_status)
    if starred is not None:
        base_filters.append(Reference.is_starred == starred)
    if tag:
        from app.models.reference import ReferenceTag
        base_filters.append(
            exists().where(
                ReferenceTag.reference_id == Reference.id,
                ReferenceTag.tag == tag.lower().strip(),
            )
        )

    if q:
        # Build FTS expressions — concat matches the GIN index created in migrations
        doc = func.concat(
            func.coalesce(Reference.title, ''), ' ',
            func.coalesce(Reference.abstract, ''), ' ',
            func.coalesce(Reference.summary, ''),
        )
        tsvec = func.to_tsvector('english', doc)
        tsq = func.plainto_tsquery('english', q)

        snippet_expr = func.ts_headline(
            'english',
            func.concat(func.coalesce(Reference.abstract, ''), ' ', func.coalesce(Reference.summary, '')),
            tsq,
            'MaxWords=35,MinWords=15',
        ).label('snippet')

        fts_cond = tsvec.op('@@')(tsq)
        rank_expr = func.ts_rank_cd(tsvec, tsq)

        id_stmt = select(Reference.id).where(fts_cond)
        if base_filters:
            id_stmt = id_stmt.where(*base_filters)
        total = (await db.execute(select(func.count()).select_from(id_stmt.subquery()))).scalar_one()

        fetch_stmt = (
            select(Reference, snippet_expr)
            .options(selectinload(Reference.tags))
            .where(fts_cond, *base_filters)
            .order_by(rank_expr.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await db.execute(fetch_stmt)).all()
        return [r[0] for r in rows], [r[1] for r in rows], total

    # No query — list with filters, most recent first
    list_stmt = select(Reference).options(selectinload(Reference.tags))
    if base_filters:
        list_stmt = list_stmt.where(*base_filters)

    total = (await db.execute(select(func.count()).select_from(list_stmt.subquery()))).scalar_one()
    list_stmt = list_stmt.order_by(Reference.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(list_stmt)
    refs = result.scalars().all()
    return refs, [None] * len(refs), total
