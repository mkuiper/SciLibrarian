"""
Citation graph lookup via Semantic Scholar.

For any reference that has a DOI or arXiv ID, fetch:
  - papers this reference cites (`references`)
  - papers that cite this reference (`cited_by`)

Architecture notes (informed by Cycle 15 critical review):

* The cache stores raw Semantic Scholar paper lists only. The "in_library_id"
  matching is recomputed on every call so adding a paper to the library
  immediately flips its row from "Add" to "in library" without waiting for the
  TTL to expire.
* Cache is bounded (MAX_CACHE_ENTRIES, FIFO-by-timestamp eviction) so the
  process can run indefinitely without leaking.
* An asyncio.Lock per key prevents dogpile / thundering-herd on cold misses.
* `/references` and `/citations` are fetched in parallel with asyncio.gather.
* HTTP / network errors are caught and returned as a structured `error` payload
  so the UI surfaces "couldn't reach Semantic Scholar" rather than a 500.

These are all known limitations at single-worker scale; multi-worker deploys
will need a shared cache (Redis) since each worker holds its own dict.
"""
import asyncio
import logging
import time
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.reference import Reference
from app.services.ingestion import normalise_doi, normalise_arxiv_id

logger = logging.getLogger(__name__)

# (ref_id, project_id?) → (timestamp, raw_payload {source, references, cited_by})
_cache: dict[tuple[int, Optional[int]], tuple[float, dict]] = {}
_locks: dict[tuple[int, Optional[int]], asyncio.Lock] = {}

_CACHE_TTL = 3600           # 1 hour
_MAX_CACHE_ENTRIES = 200    # bound process memory
_EVICT_BATCH = 40
_MAX_PER_LIST = 50
_S2_BASE = "https://api.semanticscholar.org/graph/v1"


def _semantic_scholar_id(ref: Reference) -> str | None:
    """Build the Semantic Scholar paper identifier for this reference, if possible."""
    if ref.doi:
        return f"DOI:{ref.doi}"
    if ref.arxiv_id:
        return f"ARXIV:{ref.arxiv_id}"
    return None


async def _fetch_list(client: httpx.AsyncClient, s2_id: str, kind: str, max_results: int = _MAX_PER_LIST) -> list[dict]:
    """Fetch `references` or `citations` from S2 for the given paper ID.

    Returns an empty list on rate-limit, 404, or any non-200; the caller decides
    whether to surface that as an error to the user.
    """
    url = f"{_S2_BASE}/paper/{s2_id}/{kind}"
    params = {"fields": "title,authors,year,externalIds", "limit": max_results}
    headers = {"Accept": "application/json"}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    resp = await client.get(url, params=params, headers=headers)
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        logger.warning(f"Semantic Scholar {kind} for {s2_id}: {resp.status_code} {resp.text[:200]}")
        # Raise so the caller can convert to a user-visible error
        resp.raise_for_status()
    return resp.json().get("data", [])


def _paper_from_row(row: dict, key: str) -> dict:
    """Normalise an S2 response item into our shape.

    S2 wraps the paper in either `citingPaper` (for /citations) or `citedPaper` (for /references).
    """
    paper = row.get(key) or {}
    ext = paper.get("externalIds") or {}
    doi = normalise_doi(ext.get("DOI"))
    arxiv_id = normalise_arxiv_id(ext.get("ArXiv"))
    authors = ", ".join(a.get("name", "") for a in (paper.get("authors") or [])[:5])
    return {
        "title": paper.get("title") or "",
        "authors": authors or None,
        "year": paper.get("year"),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "semantic_scholar_id": paper.get("paperId"),
        "in_library_id": None,  # resolved per request, NOT cached
    }


async def _library_id_lookup(db: AsyncSession, project_id: Optional[int]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (doi → ref.id, arxiv_id → ref.id) maps scoped to the project."""
    stmt = select(Reference.id, Reference.doi, Reference.arxiv_id)
    if project_id is not None:
        stmt = stmt.where(Reference.project_id == project_id)
    rows = (await db.execute(stmt)).all()
    by_doi = {r[1]: r[0] for r in rows if r[1]}
    by_arxiv = {r[2]: r[0] for r in rows if r[2]}
    return by_doi, by_arxiv


def _resolve_in_library(papers: list[dict], by_doi: dict, by_arxiv: dict) -> None:
    """Mutate each paper to set in_library_id when its DOI or arxiv_id matches a library ref."""
    for p in papers:
        p["in_library_id"] = None  # reset — papers may be replayed from cache
        if p["doi"] and p["doi"] in by_doi:
            p["in_library_id"] = by_doi[p["doi"]]
        elif p["arxiv_id"] and p["arxiv_id"] in by_arxiv:
            p["in_library_id"] = by_arxiv[p["arxiv_id"]]


def _evict_if_full() -> None:
    """Bounded cache: when over the limit, drop the oldest _EVICT_BATCH entries."""
    if len(_cache) <= _MAX_CACHE_ENTRIES:
        return
    oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:_EVICT_BATCH]
    for k, _ in oldest:
        _cache.pop(k, None)
        _locks.pop(k, None)


async def _fetch_raw(s2_id: str) -> dict:
    """Make both Semantic Scholar calls in parallel and return raw paper lists."""
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        refs_task = _fetch_list(client, s2_id, "references")
        cites_task = _fetch_list(client, s2_id, "citations")
        refs_data, cites_data = await asyncio.gather(refs_task, cites_task)

    references = [p for p in (_paper_from_row(r, "citedPaper") for r in refs_data) if p["title"]]
    cited_by = [p for p in (_paper_from_row(r, "citingPaper") for r in cites_data) if p["title"]]
    return {"references": references, "cited_by": cited_by}


async def fetch_citations(db: AsyncSession, ref: Reference) -> dict:
    """Return {source, references, cited_by} for one library reference.

    Library-match state (`in_library_id`) is recomputed on every call so the
    "Add" → "in library" transition is immediate after a user adds a paper.
    """
    s2_id = _semantic_scholar_id(ref)
    if not s2_id:
        return {
            "error": "This reference has no DOI or arXiv ID. Citation lookup requires one — try re-processing the reference or adding a DOI manually.",
            "references": [],
            "cited_by": [],
        }

    cache_key = (ref.id, ref.project_id)
    now = time.time()

    # Fast path: cached raw payload still valid
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL:
        raw = cached[1]
    else:
        # Lock per key to prevent dogpile when multiple requests miss together
        lock = _locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            # Re-check — another request may have populated the cache while we waited
            cached = _cache.get(cache_key)
            if cached and now - cached[0] < _CACHE_TTL:
                raw = cached[1]
            else:
                try:
                    raw = await _fetch_raw(s2_id)
                except (httpx.HTTPStatusError, httpx.RequestError) as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status == 429:
                        msg = "Semantic Scholar rate-limited this request. Try again in a minute — or set SEMANTIC_SCHOLAR_API_KEY in .env for higher limits."
                    else:
                        msg = f"Couldn't reach Semantic Scholar ({status or e.__class__.__name__}). Try again shortly."
                    logger.warning(f"fetch_citations failed for ref {ref.id}: {e}")
                    return {"error": msg, "references": [], "cited_by": []}
                _cache[cache_key] = (now, raw)
                _evict_if_full()

    # Library-match state is recomputed every call — never cached.
    references = [dict(p) for p in raw["references"]]
    cited_by = [dict(p) for p in raw["cited_by"]]
    by_doi, by_arxiv = await _library_id_lookup(db, ref.project_id)
    _resolve_in_library(references, by_doi, by_arxiv)
    _resolve_in_library(cited_by, by_doi, by_arxiv)

    return {
        "source": {
            "doi": ref.doi,
            "arxiv_id": ref.arxiv_id,
            "lookup_used": "doi" if ref.doi else "arxiv_id",
        },
        "references": references,
        "cited_by": cited_by,
    }
