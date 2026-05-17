from typing import Optional
from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reference import Reference


# Standard Reciprocal Rank Fusion constant from Cormack & Clarke (2009).
# Higher k flattens the curve — less weight at the top, more uniform across the list.
# 60 is the canonical value used by Elasticsearch, OpenSearch, etc.
_RRF_K = 60


async def hybrid_search(
    db: AsyncSession,
    query: str,
    project_id: int,
    *,
    limit: int = 20,
    pool_per_method: int = 30,
    collection_id: Optional[int] = None,
) -> list[tuple[Reference, float, dict]]:
    """Merge FTS + semantic results via Reciprocal Rank Fusion.

    Pulls the top `pool_per_method` from each retrieval method, computes
    sum(1 / (RRF_K + rank)) across both lists for each unique reference,
    returns the merged top `limit` as (ref, rrf_score, components) tuples
    where components is {fts_rank, semantic_rank, snippet}.

    Parallelizes FTS and embedding generation. Falls back to FTS-only if
    embedding fails or times out (15s).
    """
    import asyncio
    from app.services.embeddings import get_embedding, similarity_search

    # 1. Parallelize FTS pool and Embedding generation
    fts_task = full_text_search(
        db, query, collection_id=collection_id, project_id=project_id,
        limit=pool_per_method, offset=0,
    )
    
    # Embedding might hang/slow; wrap in timeout.
    embedding_task = asyncio.wait_for(get_embedding(query), timeout=15.0)

    try:
        results = await asyncio.gather(
            fts_task, embedding_task, return_exceptions=True
        )
        fts_result = results[0]
        query_embedding = results[1]

        # Handle exceptions from gather (e.g. timeout or LiteLLM error)
        if isinstance(fts_result, Exception):
            raise fts_result # FTS failure is fatal for hybrid search
        
        fts_refs, fts_snippets, _ = fts_result
        
        if isinstance(query_embedding, Exception):
            query_embedding = [] # Embedding failure is a fallback case
    except asyncio.TimeoutError:
        # If gather itself timed out (shouldn't happen with inner wait_for but safe)
        fts_refs, fts_snippets, _ = await fts_task
        query_embedding = []

    fts_ranks: dict[int, int] = {ref.id: idx + 1 for idx, ref in enumerate(fts_refs)}
    fts_snippet_map: dict[int, str] = {
        ref.id: fts_snippets[idx] for idx, ref in enumerate(fts_refs) if fts_snippets[idx]
    }

    # 2. Semantic pool — run similarity search with the embedding we just got
    semantic_ranks: dict[int, int] = {}
    semantic_pool: list[Reference] = []
    if query_embedding:
        scored = await similarity_search(
            db, query_embedding,
            project_id=project_id,
            collection_id=collection_id,
            limit=pool_per_method,
        )
        for idx, (ref, _) in enumerate(scored):
            semantic_ranks[ref.id] = idx + 1
            semantic_pool.append(ref)

    # Build a ref-id → Reference map from both pools
    ref_by_id: dict[int, Reference] = {r.id: r for r in fts_refs}
    for r in semantic_pool:
        ref_by_id.setdefault(r.id, r)

    # 3. RRF: score = sum over methods of 1 / (k + rank). Higher is better.
    scored_ids: list[tuple[int, float, dict]] = []
    for ref_id in ref_by_id.keys():
        components = {
            "fts_rank": fts_ranks.get(ref_id),
            "semantic_rank": semantic_ranks.get(ref_id),
            "snippet": fts_snippet_map.get(ref_id),
        }
        score = 0.0
        if components["fts_rank"]:
            score += 1.0 / (_RRF_K + components["fts_rank"])
        if components["semantic_rank"]:
            score += 1.0 / (_RRF_K + components["semantic_rank"])
        scored_ids.append((ref_id, score, components))

    scored_ids.sort(key=lambda item: item[1], reverse=True)
    return [(ref_by_id[rid], score, comp) for rid, score, comp in scored_ids[:limit]]


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
        # Generated tsvector column (title=A, abstract=B, summary=C, full_text=D) — index hits this directly
        tsq = func.plainto_tsquery('english', q)
        fts_cond = Reference.tsv.op('@@')(tsq)
        rank_expr = func.ts_rank_cd(Reference.tsv, tsq)

        # Headline scans the longest non-empty source so quote-level matches surface in context.
        headline_source = func.coalesce(
            func.nullif(Reference.full_text, ''),
            func.concat(func.coalesce(Reference.abstract, ''), ' ', func.coalesce(Reference.summary, '')),
        )
        snippet_expr = func.ts_headline(
            'english',
            headline_source,
            tsq,
            'MaxWords=35,MinWords=15,ShortWord=3',
        ).label('snippet')

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
