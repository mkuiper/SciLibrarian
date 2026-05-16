from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class ReviewQueueItemOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    title: str
    url: Optional[str]
    source: str
    search_query: Optional[str]
    monitor_id: Optional[int]
    status: str
    abstract: Optional[str]
    authors: Optional[str]
    year: Optional[int]
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    extra_metadata: Optional[dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDecision(BaseModel):
    action: str
    collection_id: Optional[int] = None
