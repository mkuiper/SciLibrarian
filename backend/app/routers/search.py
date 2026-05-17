from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.dependencies import DB, CurrentUser
from app.services.access import require_project_access
from app.services.search import full_text_search

router = APIRouter(prefix="/search", tags=["search"])


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
