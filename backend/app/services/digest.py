"""
Digest generation — synthesises your library into a focused research report.

Digest types:
  - state_of_art  : broad synthesis — themes, contradictions, coverage gaps (default)
  - reading_list  : ranked prioritised reading list with rationale
  - whats_new     : focused on additions since the last digest, minimal background

Scope options:
  - Entire project  (collection_id=None, tag=None)
  - Single collection (collection_id set)
  - Tag-focused     (tag set — cross-collection synthesis on a theme)
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, Digest
from app.models.collection import Collection
from app.models.reference import Reference
from app.services.llm import complete_text


async def generate_digest(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    period_start: datetime,
    period_end: datetime,
    model: str = "claude-sonnet-4-6",
    collection_id: Optional[int] = None,
    tag: Optional[str] = None,
    digest_type: str = "state_of_art",
) -> Digest:
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Resolve scope label and reference filter
    scope_label = "project"
    scope_name = project.name

    if tag:
        scope_label = "topic"
        scope_name = tag
    elif collection_id:
        col_result = await db.execute(select(Collection).where(Collection.id == collection_id))
        col = col_result.scalar_one_or_none()
        if col:
            scope_label = "collection"
            scope_name = col.name

    # Build the reference filter
    if tag:
        # Tag-focused: join via reference_tags
        from app.models.reference import ReferenceTag
        from sqlalchemy import and_
        tagged_ids_result = await db.execute(
            select(ReferenceTag.reference_id).where(ReferenceTag.tag == tag.lower().strip())
        )
        tagged_ids = [row[0] for row in tagged_ids_result]
        base_filter = [Reference.project_id == project_id, Reference.id.in_(tagged_ids)]
    elif collection_id:
        # Collect refs in this collection and all its children
        child_ids = await _get_collection_subtree(db, collection_id)
        base_filter = [Reference.collection_id.in_(child_ids)]
    else:
        base_filter = [Reference.project_id == project_id]

    new_refs_result = await db.execute(
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(*base_filter, Reference.created_at >= period_start, Reference.created_at <= period_end)
        .order_by(Reference.created_at.desc())
    )
    new_refs = new_refs_result.scalars().all()

    all_refs_result = await db.execute(
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(*base_filter)
        .order_by(Reference.created_at.desc())
        .limit(100)
    )
    all_refs = all_refs_result.scalars().all()

    source_material = _build_source_material(all_refs)
    new_refs_data = _build_source_material(new_refs, brief=True)

    all_tags: dict[str, int] = {}
    for r in all_refs:
        for t in r.tags:
            all_tags[t.tag] = all_tags.get(t.tag, 0) + 1
    top_topics = sorted(all_tags.items(), key=lambda x: -x[1])[:12]

    prompt = _build_prompt(
        project=project,
        scope_label=scope_label,
        scope_name=scope_name,
        period_start=period_start,
        period_end=period_end,
        new_refs=new_refs,
        new_refs_data=new_refs_data,
        all_refs=all_refs,
        source_material=source_material,
        top_topics=top_topics,
        digest_type=digest_type,
    )

    content = await complete_text(model, prompt, max_tokens=4000)

    # Title includes digest type when not the default
    type_label = {"reading_list": " — Reading List", "whats_new": " — What's New"}.get(digest_type, "")
    if scope_label == "collection":
        title = f"Collection Digest{type_label} — {scope_name} — {period_end.strftime('%B %Y')}"
    elif scope_label == "topic":
        title = f"Topic Digest{type_label} — #{scope_name} — {period_end.strftime('%B %Y')}"
    else:
        title = f"Monthly Digest{type_label} — {period_end.strftime('%B %Y')}"

    digest = Digest(
        project_id=project_id,
        title=title,
        content=content,
        period_start=period_start,
        period_end=period_end,
        new_references=len(new_refs),
        created_by=user_id,
    )
    db.add(digest)
    await db.flush()
    await db.refresh(digest)
    return digest


async def _get_collection_subtree(db: AsyncSession, collection_id: int) -> list[int]:
    """Return collection_id plus all descendant IDs (handles nested collections)."""
    all_cols_result = await db.execute(
        select(Collection.id, Collection.parent_id)
    )
    all_cols = all_cols_result.all()
    children: dict[int, list[int]] = {}
    for cid, pid in all_cols:
        if pid is not None:
            children.setdefault(pid, []).append(cid)

    ids = []
    queue = [collection_id]
    while queue:
        current = queue.pop()
        ids.append(current)
        queue.extend(children.get(current, []))
    return ids


def _build_source_material(refs: list, brief: bool = False) -> str:
    if not refs:
        return "(none)"
    lines = []
    for r in refs[:50]:
        lines.append(f"\n**{r.title}** ({r.year or 'n.d.'}) [{r.source_type}]")
        if r.authors:
            lines.append(f"  Authors: {r.authors[:120]}")
        # Use best available content: summary → abstract → full_text snippet
        content = r.summary or r.abstract or ""
        if not content and r.full_text:
            content = r.full_text[:600]
        if content:
            limit = 150 if brief else 500
            lines.append(f"  {content[:limit]}")
    return "\n".join(lines)


def _build_prompt(
    project, scope_label, scope_name, period_start, period_end,
    new_refs, new_refs_data, all_refs, source_material, top_topics,
    digest_type: str,
) -> str:
    header = f"""You are Alexandria, the research librarian for "{project.name}".

Digest type: {digest_type}
Scope: {scope_label} "{scope_name}"
Period: {period_start.strftime('%d %B %Y')} to {period_end.strftime('%d %B %Y')}
Project description: {project.description}

NEW references added this period ({len(new_refs)}):
{new_refs_data if new_refs_data else '(none)'}

FULL library in scope ({len(all_refs)} references) — draw directly on these summaries:
{source_material}

Top topics in scope: {', '.join(f"{t}({c})" for t, c in top_topics)}
"""

    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if digest_type == "reading_list":
        return header + f"""
Generate a prioritised reading list in Markdown. Recommend what the team should read and in what order, with clear rationale for each pick. Draw on the summaries above — do not invent papers not in the library.

# Alexandria Reading List — {scope_name}
## {project.name} · {period_end.strftime('%B %Y')}

### Why This List
(1-2 sentences on selection criteria)

### Essential Reading
(Top 5-8 papers/documents — title, why it matters, what to look for)

### Recommended Reading
(Next 5-10 — brief rationale for each)

### Background Reading
(Useful context — lower priority)

### What to Find Next
(Gaps: high-value papers not yet in the library that this reading list points to)

---
*Generated by Alexandria on {now_str}*"""

    if digest_type == "whats_new":
        return header + f"""
Generate a "What's New" digest focused on recent additions. Be concise — this is a briefing, not a full synthesis.

# What's New — {scope_name}
## {project.name} · {period_end.strftime('%B %Y')}

### This Period at a Glance
(2-3 sentences: how many additions, key themes)

### Notable New Additions
(The most significant new references — what they contribute)

### Emerging Themes
(Any new patterns or directions visible in recent additions?)

### Follow-Up Recommended
(From the new additions, what should be read carefully?)

---
*Generated by Alexandria on {now_str}*"""

    # Default: state_of_art
    return header + f"""
Generate a comprehensive research digest in Markdown. Synthesise the actual content of the references above — cite papers by title, identify themes, patterns and contradictions.

# Alexandria {'Collection' if scope_label == 'collection' else ('Topic' if scope_label == 'topic' else 'Monthly')} Digest — {scope_name}
## {project.name} · {period_end.strftime('%B %Y')}

### Executive Summary
(2-3 sentences: scope, volume, key finding)

### New Additions This Period
(What was added and why it matters — or note if nothing new)

### State of the Art — Key Themes
(Synthesise what the library reveals — cite specific papers by title)

### Notable Findings
(Surprising, significant, or novel results from the references)

### Coverage Gaps
(Important areas missing from {"this collection" if scope_label == "collection" else "the library"})

### Recommended Next Steps
(What should the team prioritise acquiring next?)

---
*Generated by Alexandria on {now_str}*"""
