from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class ReferenceCreate(BaseModel):
    title: str
    authors: Optional[str] = None
    year: Optional[int] = None
    source_type: str = "paper"
    abstract: Optional[str] = None
    url: Optional[str] = None
    collection_id: Optional[int] = None
    tags: list[str] = []


class ReferenceUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    source_type: Optional[str] = None
    abstract: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None
    collection_id: Optional[int] = None
    tags: Optional[list[str]] = None


class ReferenceTagOut(BaseModel):
    tag: str
    model_config = {"from_attributes": True}


class ReferenceOut(BaseModel):
    id: int
    title: str
    authors: Optional[str]
    year: Optional[int]
    source_type: str
    abstract: Optional[str]
    summary: Optional[str]
    url: Optional[str]
    file_name: Optional[str]
    collection_id: Optional[int]
    created_by: int
    created_at: datetime
    updated_at: datetime
    extra_metadata: Optional[dict[str, Any]]
    tags: list[ReferenceTagOut] = []

    model_config = {"from_attributes": True}
