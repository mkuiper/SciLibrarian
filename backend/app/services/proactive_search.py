"""
Proactive search sources for Alexandria's monitors.

Free sources (no API key required):
  - arXiv: Preprints in physics, CS, maths, etc. Great for AI/ML papers.
  - Semantic Scholar: 200M+ academic papers. Free, rate-limited without key.
  - OpenAlex: 250M+ open scholarly works. Free, generous rate limit with email.

Optional (require API keys in .env):
  - SEMANTIC_SCHOLAR_API_KEY: increases rate limit to 100 req/sec
  - OPENALEX_EMAIL: increases rate limit (polite pool), add to .env
"""
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.search_monitor import SearchMonitor
from app.models.review_queue import ReviewQueueItem


async def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    import xml.etree.ElementTree as ET
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        published_el = entry.find("atom:published", ns)
        link_el = entry.find("atom:id", ns)
        authors = [
            a.find("atom:name", ns).text
            for a in entry.findall("atom:author", ns)
            if a.find("atom:name", ns) is not None
        ]
        year = None
        if published_el is not None and published_el.text:
            try:
                year = int(published_el.text[:4])
            except ValueError:
                pass
        results.append({
            "title": (title_el.text or "").strip(),
            "abstract": (summary_el.text or "").strip(),
            "authors": ", ".join(authors),
            "year": year,
            "url": (link_el.text or "").strip(),
            "source": "arxiv",
        })
    return results


async def search_semantic_scholar(query: str, max_results: int = 10) -> list[dict]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,authors,year,externalIds,openAccessPdf",
    }
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return []

    results = []
    for paper in resp.json().get("data", []):
        pdf_url = None
        if paper.get("openAccessPdf"):
            pdf_url = paper["openAccessPdf"].get("url")
        doi = (paper.get("externalIds") or {}).get("DOI")
        url_out = pdf_url or (f"https://doi.org/{doi}" if doi else None)
        results.append({
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "authors": ", ".join(a.get("name", "") for a in paper.get("authors", [])),
            "year": paper.get("year"),
            "url": url_out,
            "source": "semantic_scholar",
        })
    return results


async def search_openalex(query: str, max_results: int = 10) -> list[dict]:
    """
    OpenAlex is a free, open catalogue of 250M+ scholarly works.
    No API key required. Set OPENALEX_EMAIL in .env to use the polite pool
    (much higher rate limits).

    Docs: https://docs.openalex.org/
    """
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
        "sort": "publication_date:desc",
        "select": "id,title,abstract_inverted_index,authorships,publication_year,doi,open_access",
    }
    if settings.openalex_email:
        params["mailto"] = settings.openalex_email

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers={"User-Agent": "SciLibrarian/1.0"})
        if resp.status_code != 200:
            return []

    results = []
    for work in resp.json().get("results", []):
        title = work.get("title", "")
        if not title:
            continue

        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in (work.get("authorships") or [])[:5]
        )

        doi = work.get("doi", "")
        oa_url = (work.get("open_access") or {}).get("oa_url")
        url_out = oa_url or (doi if doi.startswith("http") else f"https://doi.org/{doi.lstrip('https://doi.org/')}" if doi else None)

        results.append({
            "title": title,
            "abstract": abstract or "",
            "authors": authors,
            "year": work.get("publication_year"),
            "url": url_out,
            "source": "openalex",
            "extra_metadata": {"openalex_id": work.get("id"), "doi": doi},
        })
    return results


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as inverted indices; reconstruct the text."""
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for word, locs in inverted_index.items():
        for pos in locs:
            positions[pos] = word
    return " ".join(positions[i] for i in sorted(positions))


SOURCES = {
    "arxiv": search_arxiv,
    "semantic_scholar": search_semantic_scholar,
    "openalex": search_openalex,
}


async def run_monitor(db: AsyncSession, monitor: SearchMonitor) -> int:
    all_results = []
    sources = [s.strip() for s in monitor.sources.split(",")]

    for source_name in sources:
        fn = SOURCES.get(source_name)
        if fn:
            try:
                all_results.extend(await fn(monitor.query))
            except Exception:
                pass

    added = 0
    for item in all_results:
        if not item.get("title"):
            continue
        db.add(ReviewQueueItem(
            title=item["title"],
            url=item.get("url"),
            source=item["source"],
            search_query=monitor.query,
            monitor_id=monitor.id,
            abstract=item.get("abstract"),
            authors=item.get("authors"),
            year=item.get("year"),
            status="pending",
            extra_metadata=item.get("extra_metadata"),
        ))
        added += 1

    monitor.last_run = datetime.now(timezone.utc)
    await db.commit()
    return added


async def run_all_due_monitors(db: AsyncSession) -> dict:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    result = await db.execute(select(SearchMonitor).where(SearchMonitor.enabled == True))
    monitors = result.scalars().all()

    ran = 0
    for monitor in monitors:
        if monitor.last_run is None:
            due = True
        elif monitor.frequency == "daily":
            due = (now - monitor.last_run) >= timedelta(days=1)
        elif monitor.frequency == "weekly":
            due = (now - monitor.last_run) >= timedelta(weeks=1)
        else:
            due = False

        if due:
            await run_monitor(db, monitor)
            ran += 1

    return {"monitors_run": ran}
