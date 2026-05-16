from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.dependencies import DB, CurrentUser
from app.models.project import Project, Digest, WatchRequest
from app.models.collection import Collection
from app.models.reference import Reference
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
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cols_result = await db.execute(select(Collection).where(Collection.project_id == project_id))
    raw_collections = cols_result.scalars().all()

    # Per-collection ref counts for the prompt
    count_rows = await db.execute(
        select(Reference.collection_id, func.count(Reference.id))
        .where(Reference.project_id == project_id)
        .group_by(Reference.collection_id)
    )
    ref_counts = {row[0]: row[1] for row in count_rows}

    collections_for_prompt = [
        {
            "id": c.id, "name": c.name, "description": c.description,
            "parent_id": c.parent_id, "ref_count": ref_counts.get(c.id, 0),
        }
        for c in raw_collections
    ]
    collection_ids = {c.id for c in raw_collections}
    collection_names = {c.id: c.name for c in raw_collections}

    # Track which collections have children — used to reject unsafe merges later
    has_children: set[int] = set()
    for c in raw_collections:
        if c.parent_id is not None:
            has_children.add(c.parent_id)

    refs_result = await db.execute(
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(Reference.project_id == project_id)
        .order_by(Reference.created_at.desc())
        .limit(50)
    )
    raw_refs = refs_result.scalars().all()
    ref_titles = {r.id: r.title for r in raw_refs}
    ref_years = {r.id: r.year for r in raw_refs}

    refs_for_prompt = [
        {
            "id": r.id, "title": r.title[:140], "year": r.year,
            "collection_id": r.collection_id, "tags": [t.tag for t in r.tags][:6],
        }
        for r in raw_refs
    ]

    # Use the project's configured librarian model (a global override on top of
    # that is applied inside complete_text via effective_model).
    from app.config import settings as app_settings
    project_settings = project.settings or {}
    model = project_settings.get("librarian_model") or app_settings.default_librarian_model

    suggested = await suggest_restructure(
        project.name, collections_for_prompt, refs_for_prompt, model=model,
    )
    actions_in = suggested.get("actions") or []

    # Resolve IDs and validate every action — anything pointing at an unknown
    # or out-of-project ID is marked invalid so the UI shows it but can't apply it.
    resolved_actions: list[dict] = []
    for action in actions_in:
        if not isinstance(action, dict):
            continue
        atype = action.get("type")
        out = {**action, "invalid": False, "invalid_reason": None}

        def invalidate(reason: str):
            out["invalid"] = True
            out["invalid_reason"] = reason

        if atype == "create_collection":
            parent = action.get("parent_id")
            if parent is not None and parent not in collection_ids:
                invalidate(f"parent_id {parent} doesn't belong to this project")
            populate_ids = action.get("populate_with_reference_ids") or []
            unknown_refs = [rid for rid in populate_ids if rid not in ref_titles]
            if unknown_refs:
                invalidate(f"reference IDs not in project: {unknown_refs[:5]}")
            out["reference_previews"] = [
                {"id": rid, "title": ref_titles.get(rid, "?"), "year": ref_years.get(rid)}
                for rid in populate_ids if rid in ref_titles
            ]

        elif atype == "rename_collection":
            cid = action.get("collection_id")
            if cid not in collection_ids:
                invalidate(f"collection_id {cid} not in project")
            out["current_name"] = collection_names.get(cid)

        elif atype == "move_references":
            target = action.get("target_collection_id")
            ref_ids = action.get("reference_ids") or []
            if target not in collection_ids:
                invalidate(f"target_collection_id {target} not in project")
            unknown_refs = [rid for rid in ref_ids if rid not in ref_titles]
            if unknown_refs:
                invalidate(f"reference IDs not in project: {unknown_refs[:5]}")
            out["target_collection_name"] = collection_names.get(target)
            out["reference_previews"] = [
                {"id": rid, "title": ref_titles.get(rid, "?"), "year": ref_years.get(rid)}
                for rid in ref_ids if rid in ref_titles
            ]

        elif atype == "merge_collections":
            src = action.get("source_collection_id")
            tgt = action.get("target_collection_id")
            if src not in collection_ids:
                invalidate(f"source_collection_id {src} not in project")
            elif tgt not in collection_ids:
                invalidate(f"target_collection_id {tgt} not in project")
            elif src == tgt:
                invalidate("source and target collections are the same")
            elif src in has_children:
                invalidate("source collection has sub-collections — move them out first")
            out["source_collection_name"] = collection_names.get(src)
            out["target_collection_name"] = collection_names.get(tgt)
            out["source_ref_count"] = ref_counts.get(src, 0)

        else:
            invalidate(f"unknown action type: {atype}")

        resolved_actions.append(out)

    return {
        "summary": suggested.get("summary", ""),
        "actions": resolved_actions,
    }


# ── Apply a restructure action ───────────────────────────────────────────────

class ApplyRestructureRequest(BaseModel):
    action: dict


@router.post("/{project_id}/apply-restructure-action", response_model=dict)
async def apply_restructure_action(
    project_id: int, body: ApplyRestructureRequest, db: DB, current_user: CurrentUser,
):
    """Execute one structured restructure action against the project.

    All collection / reference IDs are re-validated against the project before
    any write — the suggest endpoint validates too, but we don't trust the
    client to round-trip the action unchanged.
    """
    action = body.action
    atype = action.get("type")

    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(404, "Project not found")

    async def _collection_in_project(cid: int) -> Collection | None:
        if cid is None:
            return None
        r = await db.execute(
            select(Collection).where(Collection.id == cid, Collection.project_id == project_id)
        )
        return r.scalar_one_or_none()

    async def _ref_ids_in_project(ids: list[int]) -> list[int]:
        if not ids:
            return []
        r = await db.execute(
            select(Reference.id).where(Reference.id.in_(ids), Reference.project_id == project_id)
        )
        return [row[0] for row in r.all()]

    if atype == "create_collection":
        name = (action.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "name required")
        parent_id = action.get("parent_id")
        if parent_id is not None:
            parent = await _collection_in_project(parent_id)
            if not parent:
                raise HTTPException(400, "parent_id not in this project")
            parent_path = parent.path
        else:
            parent_path = "/"
        new_col = Collection(
            name=name,
            description=action.get("description") or "",
            parent_id=parent_id,
            project_id=project_id,
            path=parent_path,  # finalised after flush below
            created_by=current_user.id,
        )
        db.add(new_col)
        await db.flush()
        new_col.path = f"{parent_path}{new_col.id}/"

        populate_ids = action.get("populate_with_reference_ids") or []
        valid_ids = await _ref_ids_in_project(populate_ids)
        moved = 0
        if valid_ids:
            await db.execute(
                Reference.__table__.update()
                .where(Reference.id.in_(valid_ids), Reference.project_id == project_id)
                .values(collection_id=new_col.id)
            )
            moved = len(valid_ids)
        return {"ok": True, "created_collection_id": new_col.id, "moved_count": moved}

    if atype == "rename_collection":
        col = await _collection_in_project(action.get("collection_id"))
        if not col:
            raise HTTPException(400, "collection_id not in this project")
        new_name = (action.get("new_name") or "").strip()
        if not new_name:
            raise HTTPException(400, "new_name required")
        col.name = new_name
        new_desc = action.get("new_description")
        if new_desc is not None:
            col.description = new_desc
        return {"ok": True, "collection_id": col.id, "name": col.name}

    if atype == "move_references":
        target = await _collection_in_project(action.get("target_collection_id"))
        if not target:
            raise HTTPException(400, "target_collection_id not in this project")
        valid_ids = await _ref_ids_in_project(action.get("reference_ids") or [])
        if not valid_ids:
            raise HTTPException(400, "no valid reference_ids in this project")
        await db.execute(
            Reference.__table__.update()
            .where(Reference.id.in_(valid_ids), Reference.project_id == project_id)
            .values(collection_id=target.id)
        )
        return {"ok": True, "target_collection_id": target.id, "moved_count": len(valid_ids)}

    if atype == "merge_collections":
        src = await _collection_in_project(action.get("source_collection_id"))
        tgt = await _collection_in_project(action.get("target_collection_id"))
        if not src or not tgt:
            raise HTTPException(400, "source/target collection not in this project")
        if src.id == tgt.id:
            raise HTTPException(400, "source and target are the same")
        # Refuse if source has children — caller must move them out first
        kids = await db.execute(
            select(func.count(Collection.id)).where(Collection.parent_id == src.id)
        )
        if kids.scalar_one() > 0:
            raise HTTPException(400, "source collection has sub-collections — move them out first")
        # Move refs, then delete source
        await db.execute(
            Reference.__table__.update()
            .where(Reference.collection_id == src.id, Reference.project_id == project_id)
            .values(collection_id=tgt.id)
        )
        moved = (await db.execute(
            select(func.count(Reference.id)).where(Reference.collection_id == tgt.id, Reference.project_id == project_id)
        )).scalar_one()
        await db.delete(src)
        return {"ok": True, "target_collection_id": tgt.id, "merged_from_id": action.get("source_collection_id"), "target_total_refs": moved}

    raise HTTPException(400, f"unknown action type: {atype}")


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
        tag=data.tag or None,
        digest_type=data.digest_type,
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


@router.delete("/{project_id}/digests/{digest_id}", status_code=204)
async def delete_digest(project_id: int, digest_id: int, db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Digest).where(Digest.project_id == project_id, Digest.id == digest_id)
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")
    await db.delete(digest)


@router.get("/{project_id}/radar", response_model=dict)
async def project_radar(project_id: int, db: DB, current_user: CurrentUser):
    """Return a situational briefing: recent additions, emerging tags, queue and monitor state."""
    from datetime import timedelta
    from sqlalchemy import func, desc
    from app.models.reference import Reference, ReferenceTag
    from app.models.review_queue import ReviewQueueItem
    from app.models.search_monitor import SearchMonitor
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    new_7d = (await db.execute(
        select(func.count(Reference.id)).where(
            Reference.project_id == project_id,
            Reference.created_at >= week_ago,
        )
    )).scalar_one()

    recent_result = await db.execute(
        select(Reference)
        .where(Reference.project_id == project_id)
        .order_by(Reference.created_at.desc())
        .limit(6)
    )
    recent_refs = [
        {"id": r.id, "title": r.title, "source_type": r.source_type,
         "created_at": r.created_at.isoformat()}
        for r in recent_result.scalars().all()
    ]

    tags_result = await db.execute(
        select(ReferenceTag.tag, func.count(ReferenceTag.id).label("cnt"))
        .join(Reference, ReferenceTag.reference_id == Reference.id)
        .where(Reference.project_id == project_id, Reference.created_at >= month_ago)
        .group_by(ReferenceTag.tag)
        .order_by(desc("cnt"))
        .limit(8)
    )
    recent_tags = [{"tag": row[0], "count": row[1]} for row in tags_result.all()]

    pending_queue = (await db.execute(
        select(func.count(ReviewQueueItem.id)).where(
            ReviewQueueItem.project_id == project_id,
            ReviewQueueItem.status == "pending",
        )
    )).scalar_one()

    active_monitors = (await db.execute(
        select(func.count(SearchMonitor.id)).where(
            SearchMonitor.project_id == project_id,
            SearchMonitor.enabled.is_(True),
        )
    )).scalar_one()

    return {
        "new_refs_7d": new_7d,
        "recent_refs": recent_refs,
        "recent_tags": recent_tags,
        "pending_queue": pending_queue,
        "active_monitors": active_monitors,
    }


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


@router.get("/{project_id}/bibtex")
async def export_project_bibtex(project_id: int, db: DB, current_user: CurrentUser):
    from app.routers.references import _to_bibtex

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    refs = (await db.execute(
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(Reference.project_id == project_id)
    )).scalars().all()

    body = "\n\n".join(_to_bibtex(ref) for ref in refs)
    return Response(
        content=body,
        media_type="text/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="project_{project_id}.bib"'},
    )
