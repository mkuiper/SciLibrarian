from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str
    domains: list[str] = []
    goals: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domains: Optional[list[str]] = None
    goals: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    domain: Optional[str]   # legacy single-domain field
    domains: list[str] = []
    goals: Optional[str]
    initial_structure: Optional[dict[str, Any]]
    settings: Optional[dict[str, Any]]
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DigestOut(BaseModel):
    id: int
    project_id: int
    title: str
    content: str
    period_start: datetime
    period_end: datetime
    new_references: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DigestCreate(BaseModel):
    period_start: datetime
    period_end: datetime
    model: str = "claude-sonnet-4-6"
    collection_id: Optional[int] = None
    tag: Optional[str] = None
    digest_type: str = "state_of_art"  # state_of_art | reading_list | whats_new
    send_email: bool = False


class WatchRequestCreate(BaseModel):
    description: str
    keywords: Optional[str] = None
    source_types: Optional[str] = None


class WatchRequestOut(BaseModel):
    id: int
    project_id: int
    user_id: int
    description: str
    keywords: Optional[str]
    source_types: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
