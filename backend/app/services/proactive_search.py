"""
Proactive search sources for Alexandria's monitors.

Each monitor run:
  1. Searches across all configured sources
  2. Alexandria filters results for relevance to the monitor's intent
  3. Deduplicates against the library and existing queue
  4. Adds only relevant, new items to the review queue

Free sources (no API key required):
  - arXiv: Preprints in physics, CS, maths, etc. Great for AI/ML papers.
  - Semantic Scholar: 200M+ academic papers. Free, rate-limited without key.
  - OpenAlex: 250M+ open scholarly works. Free, generous rate limit with email.
  - DuckDuckGo: General web search — good for government docs, news, policy.
  - Hugging Face: Model hub — model cards, datasets, spaces. Best source for
    AI model cards (Claude, GPT, Gemini, Llama, etc.).

Optional (require API keys in .env):
  - SEMANTIC_SCHOLAR_API_KEY: increases rate limit to 100 req/sec
  - OPENALEX_EMAIL: increases rate limit (polite pool), add to .env
"""
import json
import logging
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.search_monitor import SearchMonitor
from app.models.review_queue import ReviewQueueItem
from app.services.ingestion import extract_ids_from_url, normalise_doi, normalise_arxiv_id

logger = logging.getLogger(__name__)


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
        link = (link_el.text or "").strip()
        _, arxiv_id = extract_ids_from_url(link)
        results.append({
            "title": (title_el.text or "").strip(),
            "abstract": (summary_el.text or "").strip(),
            "authors": ", ".join(authors),
            "year": year,
            "url": link,
            "source": "arxiv",
            "arxiv_id": arxiv_id,
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
        ext = paper.get("externalIds") or {}
        doi = normalise_doi(ext.get("DOI"))
        arxiv_id = normalise_arxiv_id(ext.get("ArXiv"))
        url_out = pdf_url or (f"https://doi.org/{doi}" if doi else None)
        results.append({
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "authors": ", ".join(a.get("name", "") for a in paper.get("authors", [])),
            "year": paper.get("year"),
            "url": url_out,
            "source": "semantic_scholar",
            "doi": doi,
            "arxiv_id": arxiv_id,
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

        doi_raw = work.get("doi", "")
        doi = normalise_doi(doi_raw)
        oa_url = (work.get("open_access") or {}).get("oa_url")
        url_out = oa_url or (doi_raw if doi_raw and doi_raw.startswith("http") else (f"https://doi.org/{doi}" if doi else None))

        results.append({
            "title": title,
            "abstract": abstract or "",
            "authors": authors,
            "year": work.get("publication_year"),
            "url": url_out,
            "source": "openalex",
            "doi": doi,
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


async def search_web(query: str, max_results: int = 10) -> list[dict]:
    """
    Web search for policy docs, model cards, news, reports.
    Uses Brave Search API if BRAVE_SEARCH_API_KEY is set (recommended —
    more reliable from server/Docker environments). Falls back to DuckDuckGo.

    Note: DuckDuckGo aggressively rate-limits server IPs. If monitors return
    few web results, set BRAVE_SEARCH_API_KEY in .env (free tier: 2000/month).
    """
    if settings.brave_search_api_key:
        return await _search_brave(query, max_results)
    return await _search_duckduckgo(query, max_results)


async def _search_brave(query: str, max_results: int) -> list[dict]:
    """Brave Search API — reliable, no rate-limit issues, free tier 2000/month."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": min(max_results, 20)},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": settings.brave_search_api_key,
                },
            )
        if resp.status_code != 200:
            logger.warning(f"Brave Search returned {resp.status_code} for '{query[:50]}'")
            return []
        results = []
        for r in resp.json().get("web", {}).get("results", []):
            results.append({
                "title": r.get("title", ""),
                "abstract": r.get("description", ""),
                "authors": None,
                "year": None,
                "url": r.get("url"),
                "source": "web",
            })
        return results
    except Exception as e:
        logger.debug(f"Brave Search failed: {e}")
        return []


async def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo async search with retry on rate limit."""
    import asyncio
    try:
        from duckduckgo_search import AsyncDDGS
        from duckduckgo_search.exceptions import RatelimitException
    except ImportError:
        logger.debug("duckduckgo_search not available")
        return []

    for attempt in range(3):
        try:
            async with AsyncDDGS() as ddgs:
                raw = await ddgs.atext(query, max_results=max_results)
            return [{
                "title": r.get("title", ""),
                "abstract": r.get("body", ""),
                "authors": None,
                "year": None,
                "url": r.get("href"),
                "source": "web",
            } for r in (raw or [])]
        except RatelimitException:
            if attempt < 2:
                wait = 3 * (2 ** attempt)  # 3s, 6s
                logger.debug(f"DuckDuckGo rate limited, retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.warning(
                    f"DuckDuckGo rate limited after 3 attempts for '{query[:50]}'. "
                    "Set BRAVE_SEARCH_API_KEY in .env for reliable web search."
                )
        except Exception as e:
            logger.debug(f"DuckDuckGo search failed: {e}")
            break
    return []


async def search_huggingface(query: str, max_results: int = 10) -> list[dict]:
    """
    Hugging Face model hub search — returns community model cards.
    Note: proprietary models (Claude, GPT-4, Gemini) are NOT on HuggingFace.
    Best for: open-weight models, fine-tunes, community evaluations.
    """
    results = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://huggingface.co/api/models",
                params={"search": query, "limit": max_results, "full": "true"},
                headers={"User-Agent": "SciLibrarian/1.0"},
            )
        if resp.status_code != 200:
            return []
        for m in resp.json():
            model_id = m.get("id", "")
            if not model_id:
                continue
            author = m.get("author", "")
            pipeline_tag = m.get("pipeline_tag") or ""
            tags = m.get("tags") or []
            # Build a useful description from available metadata
            # (cardData is not returned by the public API)
            content_tags = [t for t in tags if not t.startswith(("license:", "language:", "dataset:"))][:8]
            abstract_parts = []
            if pipeline_tag:
                abstract_parts.append(f"Task: {pipeline_tag}")
            if content_tags:
                abstract_parts.append(f"Tags: {', '.join(content_tags)}")
            results.append({
                "title": f"HF model: {model_id}",
                "abstract": ". ".join(abstract_parts),
                "authors": author or None,
                "year": None,
                "url": f"https://huggingface.co/{model_id}",
                "source": "huggingface",
            })
    except Exception as e:
        logger.debug(f"Hugging Face model search failed: {e}")
    return results


SOURCES = {
    "arxiv": search_arxiv,
    "semantic_scholar": search_semantic_scholar,
    "openalex": search_openalex,
    "web": search_web,
    "huggingface": search_huggingface,
}


async def expand_query(monitor_name: str, query: str, model: str | None = None) -> list[str]:
    """
    Ask Alexandria to generate 3-5 effective search query variants.
    Returns the original query plus variants for broader coverage.
    """
    from app.services.llm import complete_text
    model = model or settings.default_librarian_model
    prompt = f"""Generate 3-5 effective search queries for finding papers, reports, model cards, technical documents, and web pages related to:

Monitor: {monitor_name}
Core query: {query}

Return a JSON array of search query strings only. Each should be:
- Specific enough to return relevant results
- Varied (different phrasings, synonyms, related concepts, author names if relevant)
- Suitable for both academic databases and general web search

Example format: ["query 1", "query 2", "query 3"]
Return the JSON array only, no other text."""

    try:
        raw = await complete_text(model, prompt, max_tokens=300)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        variants = json.loads(raw)
        if isinstance(variants, list) and all(isinstance(q, str) for q in variants):
            all_queries = [query] + [v for v in variants if v != query]
            logger.info(f"Query expansion: '{query}' → {all_queries[:5]}")
            return all_queries[:5]
    except Exception as e:
        logger.debug(f"Query expansion failed: {e}")
    return [query]


async def filter_by_relevance(
    results: list[dict], monitor_name: str, query: str, model: str | None = None
) -> list[dict]:
    """
    Ask Alexandria to evaluate each result for relevance to the monitor's intent.
    Returns only the results she considers relevant.
    Falls back to returning all results if the model produces an unusable response.
    """
    if not results:
        return []
    if len(results) <= 3:
        return results

    from app.services.llm import complete_text
    model = model or settings.default_librarian_model

    items = []
    for i, r in enumerate(results):
        source = r.get("source", "")
        abstract = (r.get("abstract") or "")[:200]
        items.append(f'{i} [{source}]: "{r.get("title", "")}" — {abstract}')

    prompt = f"""You are a research librarian evaluating search results.

Monitor topic: {monitor_name}
Search intent: {query}

Results (index [source]: title — description):
{chr(10).join(items)}

Return a JSON array of index numbers for results that are relevant to the monitor topic.
Include results that directly match OR are closely related to the topic.
Model cards, technical reports, blog posts, and web pages count as valid — not just academic papers.
Exclude only clearly off-topic or spam results.
Return the JSON array only, e.g. [0, 2, 5]. Return all indices if most results are relevant."""

    try:
        raw = await complete_text(model, prompt, max_tokens=200)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        indices = json.loads(raw)
        if isinstance(indices, list) and len(indices) > 0:
            valid = [results[i] for i in indices if isinstance(i, int) and 0 <= i < len(results)]
            logger.info(f"Relevance filter: {len(results)} → {len(valid)} results kept (indices: {indices})")
            return valid
        elif isinstance(indices, list) and len(indices) == 0:
            # Model explicitly returned empty — log and fall back to passing all through
            # rather than silently dropping everything
            logger.warning(f"Relevance filter returned empty for '{monitor_name}' — passing all {len(results)} results through")
            return results
    except Exception as e:
        logger.debug(f"Relevance filtering failed ({e}), returning all results")
    return results


async def _is_duplicate(
    db: AsyncSession,
    title: str,
    url: str | None,
    doi: str | None = None,
    arxiv_id: str | None = None,
) -> bool:
    """
    Check if this item is already in the library or the pending queue.
    Matches on DOI, arXiv ID, URL, or normalised title.
    """
    from app.models.reference import Reference
    from sqlalchemy import func

    norm_title = title.strip().lower()

    if doi:
        if (await db.execute(select(Reference).where(Reference.doi == doi))).scalar_one_or_none():
            return True
        if (await db.execute(
            select(ReviewQueueItem).where(ReviewQueueItem.doi == doi, ReviewQueueItem.status == "pending")
        )).scalar_one_or_none():
            return True

    if arxiv_id:
        if (await db.execute(select(Reference).where(Reference.arxiv_id == arxiv_id))).scalar_one_or_none():
            return True
        if (await db.execute(
            select(ReviewQueueItem).where(ReviewQueueItem.arxiv_id == arxiv_id, ReviewQueueItem.status == "pending")
        )).scalar_one_or_none():
            return True

    if url:
        existing_ref = await db.execute(select(Reference).where(Reference.url == url))
        if existing_ref.scalar_one_or_none():
            return True
        existing_queue = await db.execute(
            select(ReviewQueueItem).where(ReviewQueueItem.url == url, ReviewQueueItem.status == "pending")
        )
        if existing_queue.scalar_one_or_none():
            return True

    existing_title_ref = await db.execute(
        select(Reference).where(func.lower(func.trim(Reference.title)) == norm_title)
    )
    if existing_title_ref.scalar_one_or_none():
        return True

    existing_title_queue = await db.execute(
        select(ReviewQueueItem).where(
            func.lower(func.trim(ReviewQueueItem.title)) == norm_title,
            ReviewQueueItem.status == "pending",
        )
    )
    if existing_title_queue.scalar_one_or_none():
        return True

    return False


async def run_monitor(db: AsyncSession, monitor: SearchMonitor, model: str | None = None) -> int:
    sources = [s.strip() for s in monitor.sources.split(",")]
    model = model or settings.default_librarian_model

    # Step 1: Expand the query into variants for better coverage
    queries = await expand_query(monitor.name, monitor.query, model)
    logger.info(f"Monitor '{monitor.name}': running {len(queries)} query variants across {sources}")

    # Step 2: Search all sources with all query variants
    seen_titles: set[str] = set()
    all_results: list[dict] = []
    for query in queries:
        for source_name in sources:
            fn = SOURCES.get(source_name)
            if not fn:
                logger.warning(f"Unknown source '{source_name}' — skipping")
                continue
            try:
                source_results = await fn(query)
                new_count = 0
                for result in source_results:
                    title_key = result.get("title", "").strip().lower()
                    if title_key and title_key not in seen_titles:
                        seen_titles.add(title_key)
                        all_results.append(result)
                        new_count += 1
                logger.info(f"  {source_name} / '{query[:50]}': {len(source_results)} returned, {new_count} new")
            except Exception as e:
                logger.warning(f"Source {source_name} failed for query '{query}': {e}")

    if not all_results:
        monitor.last_run = datetime.now(timezone.utc)
        await db.commit()
        return 0

    # Step 3: Alexandria filters for genuine relevance
    relevant = await filter_by_relevance(all_results, monitor.name, monitor.query, model)

    # Step 3.5: Filter out anything matching the monitor's negative keywords (learned from rejects)
    if monitor.negative_keywords:
        neg = [k.strip().lower() for k in monitor.negative_keywords.split(",") if k.strip()]
        if neg:
            before = len(relevant)
            relevant = [
                r for r in relevant
                if not any(k in (r.get("title", "") + " " + (r.get("abstract") or "")).lower() for k in neg)
            ]
            if before != len(relevant):
                logger.info(f"Monitor '{monitor.name}': negative_keywords dropped {before - len(relevant)} of {before} results")

    # Step 4: Deduplicate against library + existing queue, then add
    added = 0
    skipped_duplicates = 0
    for item in relevant:
        if not item.get("title"):
            continue
        item_doi = normalise_doi(item.get("doi"))
        item_arxiv = normalise_arxiv_id(item.get("arxiv_id"))
        if not item_doi or not item_arxiv:
            url_doi, url_arxiv = extract_ids_from_url(item.get("url"))
            item_doi = item_doi or url_doi
            item_arxiv = item_arxiv or url_arxiv
        if await _is_duplicate(db, item["title"], item.get("url"), doi=item_doi, arxiv_id=item_arxiv):
            skipped_duplicates += 1
            continue
        db.add(ReviewQueueItem(
            title=item["title"],
            url=item.get("url"),
            source=item["source"],
            search_query=monitor.query,
            monitor_id=monitor.id,
            project_id=monitor.project_id,
            abstract=item.get("abstract"),
            authors=item.get("authors"),
            year=item.get("year"),
            doi=item_doi,
            arxiv_id=item_arxiv,
            status="pending",
            extra_metadata=item.get("extra_metadata"),
        ))
        added += 1

    monitor.last_run = datetime.now(timezone.utc)
    await db.commit()
    logger.info(f"Monitor '{monitor.name}': {len(all_results)} found → {len(relevant)} relevant → {added} added to queue ({skipped_duplicates} duplicates skipped)")
    return added


async def suggest_monitor_improvements(
    db: AsyncSession, monitor: SearchMonitor, model: str | None = None
) -> dict:
    """
    Ask Alexandria to refine the monitor based on recent approve/reject decisions.

    Returns:
        {refined_query, negative_keywords: [str], reasoning, samples: {approved: [...], rejected: [...]}}

    Caller decides what to apply — the suggestion is advisory.
    """
    from app.services.llm import complete_text
    model = model or settings.default_librarian_model

    approved_stmt = (
        select(ReviewQueueItem)
        .where(ReviewQueueItem.monitor_id == monitor.id, ReviewQueueItem.status == "approved")
        .order_by(ReviewQueueItem.reviewed_at.desc().nulls_last())
        .limit(10)
    )
    rejected_stmt = (
        select(ReviewQueueItem)
        .where(ReviewQueueItem.monitor_id == monitor.id, ReviewQueueItem.status == "rejected")
        .order_by(ReviewQueueItem.reviewed_at.desc().nulls_last())
        .limit(10)
    )
    approved = (await db.execute(approved_stmt)).scalars().all()
    rejected = (await db.execute(rejected_stmt)).scalars().all()

    if len(approved) + len(rejected) < 3:
        return {
            "refined_query": None,
            "negative_keywords": [],
            "reasoning": "Not enough decisions yet — review at least 3 items before refining.",
            "samples": {"approved": [], "rejected": []},
        }

    def sample(item):
        return {
            "title": item.title,
            "abstract": (item.abstract or "")[:300],
            "reason": (getattr(item, "rejection_reason", None) or "").strip(),
        }

    approved_samples = [sample(i) for i in approved]
    rejected_samples = [sample(i) for i in rejected]

    def _rejected_line(r):
        return f"- {r['title']}" + (f"  (reason: {r['reason']})" if r['reason'] else "")

    prompt = f"""You are tuning a literature search monitor for a researcher.

Monitor name: {monitor.name}
Current query: {monitor.query}
Existing negative keywords: {monitor.negative_keywords or '(none)'}

APPROVED items (researcher kept these):
{chr(10).join(f"- {a['title']}" for a in approved_samples) or '(none yet)'}

REJECTED items (researcher discarded these — when a reason is given, weight it heavily):
{chr(10).join(_rejected_line(r) for r in rejected_samples) or '(none yet)'}

Suggest a query refinement and negative-keyword list that would surface more items like the approved ones and fewer like the rejected ones. When rejection reasons are present, use them to identify the specific patterns the researcher wants to exclude.

Rules:
- Keep the refined query close to the original — don't change the core topic.
- Negative keywords should be specific terms (not generic words). Aim for 3-8 terms.
- Skip negative keywords if rejections were too varied to draw a pattern.
- Be honest: if there isn't enough signal, say so.

Return JSON only, no markdown:
{{"refined_query": "...", "negative_keywords": ["...", "..."], "reasoning": "one short paragraph"}}"""

    raw = await complete_text(model, prompt, max_tokens=600)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "refined_query": None,
            "negative_keywords": [],
            "reasoning": "Couldn't parse model output — try running this again.",
            "samples": {"approved": approved_samples, "rejected": rejected_samples},
        }

    return {
        "refined_query": parsed.get("refined_query") if parsed.get("refined_query") != monitor.query else None,
        "negative_keywords": [k for k in (parsed.get("negative_keywords") or []) if isinstance(k, str) and k.strip()],
        "reasoning": parsed.get("reasoning", "")[:600],
        "samples": {"approved": approved_samples, "rejected": rejected_samples},
    }


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
