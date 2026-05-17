"""
Living literature review — project-level synthesis of the whole library.

Unlike Digest (which is "what's new in window X"), this is evergreen: a
markdown document covering themes, methods, consensus, disagreements, and
reading recommendations across the entire body of work. Re-generated on
demand; previous versions are retained.

Citation pattern matches the librarian's: refs are cited inline as `[id]`
and resolved client-side against the library.
"""
import logging
import re
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.literature_review import LiteratureReview
from app.models.project import Project
from app.models.reference import Reference, ReferenceTag
from app.services.llm import complete_text

logger = logging.getLogger(__name__)

# Cap refs in the prompt to keep within context budget. Prioritise:
#   1. Starred references
#   2. References with summaries
#   3. Recently added
MAX_REFS_IN_PROMPT = 40
MAX_SUMMARY_CHARS = 600

CITATION_RE = re.compile(r"\[(\d+)\]")


async def _select_seed_references(db: AsyncSession, project_id: int) -> list[Reference]:
    """Choose the most-informative subset of references for the synthesis prompt.

    Starred refs always win. Among the rest, prefer refs that have a non-empty
    summary (Alexandria can synthesise) over those without. Most recent first
    inside each bucket so newer work isn't drowned out.
    """
    starred_stmt = (
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(Reference.project_id == project_id, Reference.is_starred.is_(True))
        .order_by(Reference.created_at.desc())
        .limit(MAX_REFS_IN_PROMPT)
    )
    starred = (await db.execute(starred_stmt)).scalars().all()
    remaining = max(0, MAX_REFS_IN_PROMPT - len(starred))

    rest = []
    if remaining > 0:
        # Refs with summaries first, then anything else; exclude already-picked starred.
        # Conditionally add the exclusion filter — passing a plain True to .where()
        # is invalid in SQLAlchemy 2.x and was flagged in critical review.
        starred_ids = {r.id for r in starred}
        rest_stmt = (
            select(Reference)
            .options(selectinload(Reference.tags))
            .where(Reference.project_id == project_id)
            .order_by(Reference.summary.is_(None).asc(), Reference.created_at.desc())
            .limit(remaining)
        )
        if starred_ids:
            rest_stmt = rest_stmt.where(Reference.id.notin_(starred_ids))
        rest = (await db.execute(rest_stmt)).scalars().all()

    return list(starred) + list(rest)


async def _library_overview(db: AsyncSession, project_id: int) -> dict:
    """Counts + top tags for the project — same shape as Alexandria's snapshot."""
    total = (await db.execute(
        select(func.count(Reference.id)).where(Reference.project_id == project_id)
    )).scalar_one()
    by_type = {
        row[0]: row[1]
        for row in (await db.execute(
            select(Reference.source_type, func.count(Reference.id))
            .where(Reference.project_id == project_id)
            .group_by(Reference.source_type)
        )).all()
    }
    top_tags = [
        {"tag": row[0], "count": row[1]}
        for row in (await db.execute(
            select(ReferenceTag.tag, func.count(ReferenceTag.id))
            .join(Reference, Reference.id == ReferenceTag.reference_id)
            .where(Reference.project_id == project_id)
            .group_by(ReferenceTag.tag)
            .order_by(func.count(ReferenceTag.id).desc())
            .limit(20)
        )).all()
    ]
    return {"total": total, "by_type": by_type, "top_tags": top_tags}


def _ref_for_prompt(ref: Reference) -> dict:
    summary = (ref.summary or ref.abstract or "")[:MAX_SUMMARY_CHARS]
    return {
        "id": ref.id,
        "title": ref.title[:200],
        "year": ref.year,
        "authors": (ref.authors or "")[:120],
        "tags": [t.tag for t in ref.tags][:6],
        "summary": summary,
    }


def _extract_cited_ids(markdown: str, valid_ids: set[int]) -> list[int]:
    """Return unique ref ids the model actually cited, in document order, filtered to real ids."""
    seen: list[int] = []
    for match in CITATION_RE.finditer(markdown):
        try:
            rid = int(match.group(1))
        except ValueError:
            continue
        if rid in valid_ids and rid not in seen:
            seen.append(rid)
    return seen


async def generate(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    model: Optional[str] = None,
) -> LiteratureReview:
    """Generate a fresh literature review and persist it as a new version.

    Raises ValueError if there's nothing to synthesise (< 3 references with
    summaries) so the caller can surface a friendly message instead of
    saving an empty review.
    """
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    project_settings = project.settings or {}
    model = (
        model
        or project_settings.get("librarian_model")
        or settings.default_librarian_model
    )

    seed_refs = await _select_seed_references(db, project_id)
    if len(seed_refs) < 3:
        raise ValueError(
            "Not enough references to synthesise yet — add at least 3 references "
            "before generating a literature review."
        )

    overview = await _library_overview(db, project_id)
    refs_for_prompt = [_ref_for_prompt(r) for r in seed_refs]
    valid_ids = {r.id for r in seed_refs}

    prompt = f"""You are Alexandria, the research librarian for "{project.name}".

You are writing a LIVING LITERATURE REVIEW of this project's library — an evergreen synthesis of what the corpus collectively shows, NOT a recap of recent additions. This document gets regenerated periodically and is meant to be the single page a researcher reads to orient themselves in the library.

LIBRARY OVERVIEW
- Total references: {overview['total']}
- By source type: {", ".join(f"{n} {t.replace('_', ' ')}" for t, n in overview['by_type'].items()) or "(empty)"}
- Top tags: {", ".join(f"{t['tag']} ({t['count']})" for t in overview['top_tags'][:12]) or "(none)"}

REFERENCES (use these `id` values when citing — do not invent ids):
{_format_refs_for_prompt(refs_for_prompt)}

Write a markdown document with these sections (use `##` headers):

## Overview
Two to four sentences capturing what this library is about and the dominant questions it engages with.

## Major themes
Three to six themes you see across the corpus. For each: a short heading (`### Theme name`) followed by a 2-4 sentence description grounded in specific references. Cite refs inline as `[12]` where 12 is the reference's id from the list above. A theme with no citations isn't a theme — leave it out.

## Methods and approaches
What techniques, datasets, or methodologies recur across the body of work? Cite the refs that exemplify each.

## Areas of consensus
Claims that multiple references agree on. Cite the supporting refs (at least two per claim).

## Open questions and disagreements
Where refs contradict, where gaps remain, or what the corpus doesn't yet answer well.

## Reading recommendations
Three to five must-reads for someone new to this library, with a one-sentence reason for each. Cite the ref's id.

Citation rules:
- Cite inline as `[id]`. The reader will see the actual title rendered after this is processed; you don't need to repeat titles.
- Only cite ids from the REFERENCES list above. Don't invent ids.
- Don't list a "References" section at the end — citations are inline.

Return the markdown document only. No frontmatter, no JSON, no code fences."""

    raw_content = await complete_text(model, prompt, max_tokens=3000)
    content = raw_content.strip()
    # Strip stray markdown fences a smaller model sometimes wraps the output in
    if content.startswith("```"):
        content = content.split("```", 2)[1] if content.count("```") >= 2 else content[3:]
        if content.lower().startswith("markdown"):
            content = content[8:]
        content = content.strip()
    if not content:
        raise ValueError(
            f"The model ({model}) returned an empty response. Try switching to a more capable model."
        )

    cited_ids = _extract_cited_ids(content, valid_ids)

    # Next version number for this project
    last_version = (await db.execute(
        select(func.coalesce(func.max(LiteratureReview.version), 0))
        .where(LiteratureReview.project_id == project_id)
    )).scalar_one()

    review = LiteratureReview(
        project_id=project_id,
        version=last_version + 1,
        title=f"Literature review v{last_version + 1} — {project.name}",
        content=content,
        cited_reference_ids=cited_ids,
        model_used=model,
        ref_count_at_generation=overview["total"],
        created_by=user_id,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    logger.info(
        f"Generated literature review v{review.version} for project {project_id}: "
        f"{len(cited_ids)} refs cited out of {len(seed_refs)} seeded"
    )
    return review


def _format_refs_for_prompt(refs: list[dict]) -> str:
    """Compact, human/LLM-readable rendering of the seed references."""
    lines = []
    for r in refs:
        head = f"[{r['id']}] {r['title']}"
        if r["year"]:
            head += f" ({r['year']})"
        if r["authors"]:
            head += f" — {r['authors']}"
        if r["tags"]:
            head += f"\n    tags: {', '.join(r['tags'])}"
        if r["summary"]:
            head += f"\n    summary: {r['summary']}"
        lines.append(head)
    return "\n".join(lines)


async def latest(db: AsyncSession, project_id: int) -> Optional[LiteratureReview]:
    """Most recent review for the project (any version)."""
    result = await db.execute(
        select(LiteratureReview)
        .where(LiteratureReview.project_id == project_id)
        .order_by(LiteratureReview.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def history(db: AsyncSession, project_id: int, limit: int = 10) -> list[LiteratureReview]:
    """Recent versions in reverse-chronological order."""
    result = await db.execute(
        select(LiteratureReview)
        .where(LiteratureReview.project_id == project_id)
        .order_by(LiteratureReview.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
