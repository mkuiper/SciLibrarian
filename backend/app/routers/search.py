from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.dependencies import DB, CurrentUser
from app.services.access import require_project_access
from app.services.search import full_text_search, hybrid_search
from app.services.embeddings import get_embedding, similarity_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/hybrid", response_model=dict)
async def hybrid_search_endpoint(
    db: DB,
    current_user: CurrentUser,
    q: str = Query(..., min_length=2),
    project_id: int = Query(...),
    limit: int = Query(20, le=50),
    collection_id: Optional[int] = Query(None),
):
    """Merged keyword + semantic search via Reciprocal Rank Fusion.

    Pulls top 30 from FTS and top 30 from semantic similarity, fuses with
    RRF (k=60). Each result carries `rrf_score` plus the per-method ranks
    so the UI can show *why* a ref scored well. Falls back to FTS-only if
    no embedding provider is configured.
    """
    from app.schemas.reference import ReferenceOut

    await require_project_access(db, project_id, current_user.id)

    merged = await hybrid_search(
        db, q.strip(), project_id=project_id,
        limit=limit, collection_id=collection_id,
    )
    results = []
    for ref, score, components in merged:
        out = ReferenceOut.model_validate(ref).model_dump()
        out["rrf_score"] = round(score, 6)
        out["fts_rank"] = components["fts_rank"]
        out["semantic_rank"] = components["semantic_rank"]
        out["snippet"] = components["snippet"]
        results.append(out)
    return {
        "query": q,
        "total": len(results),
        "results": results,
    }


@router.get("/semantic", response_model=dict)
async def semantic_search(
    db: DB,
    current_user: CurrentUser,
    q: str = Query(..., min_length=2),
    project_id: int = Query(...),
    limit: int = Query(20, le=50),
):
    """Find references semantically similar to the query via embeddings.

    Cosine similarity over JSONB-stored embeddings (no pgvector yet). Refs
    without an embedding are skipped — call POST /references/backfill-embeddings
    after Cycle 21 lands to fill them in.
    """
    from app.schemas.reference import ReferenceOut

    import asyncio

    await require_project_access(db, project_id, current_user.id)

    try:
        query_embedding = await asyncio.wait_for(get_embedding(q.strip()), timeout=15)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Embedding provider didn't respond within 15s — check OpenAI status or Ollama daemon.",
        )
    if not query_embedding:
        raise HTTPException(
            status_code=503,
            detail="No embedding provider available. Configure OPENAI_API_KEY or set up Ollama with nomic-embed-text.",
        )

    scored = await similarity_search(db, query_embedding, project_id=project_id, limit=limit)
    results = []
    for ref, score in scored:
        out = ReferenceOut.model_validate(ref).model_dump()
        out["similarity"] = round(score, 4)
        results.append(out)
    return {
        "query": q,
        "total": len(results),
        "results": results,
    }


@router.get("", response_model=dict)
async def search(
    db: DB,
    current_user: CurrentUser,
    q: str = Query(""),
    collection_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    tag: Optional[str] = Query(None),
    read_status: Optional[str] = Query(None),
    starred: Optional[bool] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
):
    from app.schemas.reference import ReferenceOut

    # Search must be scoped to a project the user can access. Without this an
    # unscoped query returned hits from every user's library.
    if project_id is None:
        raise HTTPException(
            status_code=400,
            detail="project_id is required — search is scoped to a project you have access to.",
        )
    await require_project_access(db, project_id, current_user.id)

    refs, snippets, total = await full_text_search(
        db, q, collection_id, project_id, source_type, limit, offset,
        year_from=year_from, year_to=year_to,
        tag=tag, read_status=read_status, starred=starred,
    )
    results = []
    for ref, snippet in zip(refs, snippets):
        out = ReferenceOut.model_validate(ref).model_dump()
        out["snippet"] = snippet
        results.append(out)
    return {
        "total": total,
        "results": results,
        "query": q,
        "limit": limit,
        "offset": offset,
    }
