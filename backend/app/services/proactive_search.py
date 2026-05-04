import httpx
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        published_el = entry.find("atom:published", ns)
        link_el = entry.find("atom:id", ns)
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]

        year = None
        if published_el is not None and published_el.text:
            try:
                year = int(published_el.text[:4])
            except ValueError:
                pass

        results.append({
            "title": title_el.text.strip() if title_el is not None else "",
            "abstract": summary_el.text.strip() if summary_el is not None else "",
            "authors": ", ".join(authors),
            "year": year,
            "url": link_el.text.strip() if link_el is not None else "",
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
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return []

    data = resp.json()
    results = []
    for paper in data.get("data", []):
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


async def run_monitor(db: AsyncSession, monitor: SearchMonitor) -> int:
    all_results = []
    sources = [s.strip() for s in monitor.sources.split(",")]

    if "arxiv" in sources:
        try:
            all_results.extend(await search_arxiv(monitor.query))
        except Exception:
            pass

    if "semantic_scholar" in sources:
        try:
            all_results.extend(await search_semantic_scholar(monitor.query))
        except Exception:
            pass

    added = 0
    for item in all_results:
        if not item.get("title"):
            continue
        queue_item = ReviewQueueItem(
            title=item["title"],
            url=item.get("url"),
            source=item["source"],
            search_query=monitor.query,
            monitor_id=monitor.id,
            abstract=item.get("abstract"),
            authors=item.get("authors"),
            year=item.get("year"),
            status="pending",
        )
        db.add(queue_item)
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
