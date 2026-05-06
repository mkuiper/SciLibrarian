from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SearchMonitorCreate(BaseModel):
    name: str
    query: str
    sources: str = "arxiv,semantic_scholar"
    frequency: str = "weekly"
    project_id: Optional[int] = None


class SearchMonitorUpdate(BaseModel):
    name: Optional[str] = None
    query: Optional[str] = None
    sources: Optional[str] = None
    frequency: Optional[str] = None
    enabled: Optional[bool] = None


class SearchMonitorOut(BaseModel):
    id: int
    user_id: int
    project_id: Optional[int]
    name: str
    query: str
    sources: str
    frequency: str
    enabled: bool
    last_run: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
