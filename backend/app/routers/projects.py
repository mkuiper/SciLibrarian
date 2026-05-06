from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
from app.models.project import Project, Digest, WatchRequest
from app.models.collection import Collection
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut,
    DigestCreate, DigestOut,
    WatchRequestCreate, WatchRequestOut,
)
from app.services.project_setup import generate_initial_structure, suggest_restructure
from app.services.digest import generate_digest

router = APIRouter(prefix="/projects", tags=["projects"])


def _default_structure(name: str, domains: list[str]) -> dict:
    """Fallback structure when Alexandria is unavailable."""
    return {
        "welcome_message": (
            f"Welcome to {name}. Your library is ready — add references using the "
            "Add button, set up search monitors, and ask me anything via the chat panel."
        ),
        "collections": [
            {"name": "Papers & Preprints",  "description": "Academic papers and preprints", "children": []},
            {"name": "Policy & Governance", "description": "Policy documents and regulatory frameworks", "children": []},
            {"name": "Reports & Reviews",   "description": "Technical reports, surveys and reviews", "children": []},
            {"name": "Data & Datasets",     "description": "Datasets, benchmarks and evaluation data", "children": []},
        ],
        "suggested_watch_queries": [],
        "initial_guidance": (
            "Start by adding references — upload PDFs, paste URLs, or email them to your "
            "ingestion address. Use the Monitors page to set up automated searches."
        ),
    }


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, db: DB, current_user: CurrentUser):
    domain_str = ", ".join(data.domains) if data.domains else ""

    # Try to have Alexandria design the structure; fall back gracefully if unavailable
    try:
        structure = await generate_initial_structure(
            name=data.name,
            description=data.description,
            domain=domain_str,
            goals=data.goals or "",
        )
    except Exception:
        structure = _default_structure(data.name, data.domains)

    project = Project(
        name=data.name,
        description=data.description,
        domain=domain_str or None,
        domains=data.domains,
        goals=data.goals,
        initial_structure=structure,
        created_by=current_user.id,
    )
    db.add(project)
    await db.flush()

    for col_data in structure.get("collections", []):
        parent = Collection(
            name=col_data["name"],
            description=col_data.get("description"),
            project_id=project.id,
            created_by=current_user.id,
            path="/",
        )
        db.add(parent)
        await db.flush()
        parent.path = f"/{parent.id}/"

        for child_data in col_data.get("children", []):
            child = Collection(
                name=child_data["name"],
                description=child_data.get("description"),
                project_id=project.id,
                parent_id=parent.id,
                created_by=current_user.id,
                path=f"/{parent.id}/",
            )
            db.add(child)
            await db.flush()
            child.path = f"/{parent.id}/{child.id}/"

    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: DB, current_user: CurrentUser):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: DB, current_user: CurrentUser):
    """Delete a project and all its collections, references, digests, monitors and watch requests."""
    from app.models.reference import Reference, ReferenceTag
    from app.models.collection import Collection
    from app.models.review_queue import ReviewQueueItem
    from sqlalchemy import delete as sql_delete

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete in dependency order
    # 1. Reference tags for refs in this project
    refs_result = await db.execute(select(Reference.id).where(Reference.project_id == project_id))
    ref_ids = [r[0] for r in refs_result]
    if ref_ids:
        await db.execute(sql_delete(ReferenceTag).where(ReferenceTag.reference_id.in_(ref_ids)))

    # 2. References
    await db.execute(sql_delete(Reference).where(Reference.project_id == project_id))

    # 3. Collections
    await db.execute(sql_delete(Collection).where(Collection.project_id == project_id))

    # 4. Project itself (cascades digests, watch requests via FK)
    await db.delete(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, data: ProjectUpdate, db: DB, current_user: CurrentUser):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(project, field, val)
    await db.flush()
    await db.refresh(project)
    return project


@router.post("/{project_id}/restructure-suggestions", response_model=dict)
async def restructure_suggestions(project_id: int, db: DB, current_user: CurrentUser):
    from app.models.reference import Reference
    from sqlalchemy.orm import selectinload

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cols_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
    collections = [{"id": c.id, "name": c.name, "parent_id": c.parent_id} for c in cols_result.scalars().all()]

    refs_result = await db.execute(
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(Reference.project_id == project_id)
        .order_by(Reference.created_at.desc())
        .limit(30)
    )
    refs = [
        {"title": r.title, "source_type": r.source_type, "collection_id": r.collection_id, "tags": [t.tag for t in r.tags]}
        for r in refs_result.scalars().all()
    ]

    return await suggest_restructure(project.name, collections, refs)


@router.post("/{project_id}/digests", response_model=DigestOut, status_code=201)
async def create_digest(project_id: int, data: DigestCreate, db: DB, current_user: CurrentUser):
    digest = await generate_digest(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        period_start=data.period_start,
        period_end=data.period_end,
        model=data.model,
        collection_id=data.collection_id,
    )

    if data.send_email:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        recipients = (project.settings or {}).get("digest_recipients", []) if project else []
        if recipients:
            from app.services.email_service import send_digest
            await send_digest(recipients, digest.title, digest.content)

    return digest


@router.get("/{project_id}/digests", response_model=list[DigestOut])
async def list_digests(project_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Digest)
        .where(Digest.project_id == project_id)
        .order_by(Digest.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{project_id}/digests/{digest_id}", response_model=DigestOut)
async def get_digest(project_id: int, digest_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Digest).where(Digest.project_id == project_id, Digest.id == digest_id)
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")
    return digest


@router.post("/{project_id}/watch-requests", response_model=WatchRequestOut, status_code=201)
async def create_watch_request(project_id: int, data: WatchRequestCreate, db: DB, current_user: CurrentUser):
    req = WatchRequest(
        project_id=project_id,
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)

    # Auto-create a monitor so the watch request actually runs searches
    from app.models.search_monitor import SearchMonitor
    keywords = data.keywords or data.description[:100]
    monitor = SearchMonitor(
        user_id=current_user.id,
        project_id=project_id,
        name=f"Watch: {data.description[:60]}",
        query=keywords,
        sources="arxiv,semantic_scholar,openalex,web,huggingface",
        frequency="weekly",
        enabled=True,
    )
    db.add(monitor)
    await db.flush()

    return req


@router.get("/{project_id}/watch-requests", response_model=list[WatchRequestOut])
async def list_watch_requests(project_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(WatchRequest)
        .where(WatchRequest.project_id == project_id)
        .order_by(WatchRequest.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{project_id}/watch-requests/{req_id}", status_code=204)
async def delete_watch_request(project_id: int, req_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(WatchRequest).where(WatchRequest.id == req_id, WatchRequest.project_id == project_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Watch request not found")
    await db.delete(req)


class ProjectSettingsUpdate(BaseModel):
    librarian_model: str | None = None
    ingestion_model: str | None = None
    digest_model: str | None = None
    librarian_system_prompt: str | None = None
    ollama_base_url: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    digest_recipients: list[str] | None = None


@router.patch("/{project_id}/settings", response_model=ProjectOut)
async def update_project_settings(
    project_id: int, data: ProjectSettingsUpdate, db: DB, current_user: CurrentUser
):
    """Update AI model and prompt settings for a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current = dict(project.settings or {})
    for field, val in data.model_dump(exclude_none=True).items():
        current[field] = val
    project.settings = current

    await db.flush()
    await db.refresh(project)
    return project
