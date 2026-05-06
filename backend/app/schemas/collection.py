from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    project_id: Optional[int] = None


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CollectionOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    parent_id: Optional[int]
    project_id: Optional[int]
    path: str
    created_by: int
    created_at: datetime
    reference_count: int = 0
    children: list["CollectionOut"] = []

    model_config = {"from_attributes": True}


CollectionOut.model_rebuild()
