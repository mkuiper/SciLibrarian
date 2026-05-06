from typing import Optional
from fastapi import APIRouter, Query

from app.dependencies import DB, CurrentUser
from app.schemas.reference import ReferenceOut
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
    limit: int = Query(20, le=100),
    offset: int = Query(0),
):
    refs, total = await full_text_search(db, q, collection_id, project_id, source_type, limit, offset)
    return {
        "total": total,
        "results": [ReferenceOut.model_validate(r) for r in refs],
        "query": q,
        "limit": limit,
        "offset": offset,
    }
