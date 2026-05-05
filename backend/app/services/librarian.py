"""
Alexandria — the SciLibrarian agent.

Tools available to Alexandria during chat:
  - search_library: full-text search across the reference database
  - get_full_text: retrieve the complete extracted text of a specific reference
  - web_search: DuckDuckGo web search for current events, policy docs, news
  - lookup_paper: fetch paper metadata from arXiv by ID or search query

For models without tool use (most Ollama models), search results are
pre-fetched and injected into the system prompt automatically.
"""
import json
from typing import AsyncIterator

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reference import Reference
from app.services.llm import complete, stream_text, model_supports_tools, _build_kwargs
import litellm

DEFAULT_SYSTEM_PROMPT = """You are Alexandria, an expert AI research librarian.
Your role is to help researchers find, understand, and synthesise information.

You have access to tools: always search the library before answering research questions.
When the library lacks coverage, use web_search to supplement — but clearly distinguish library sources from web sources.

When answering:
- Cite library references by exact title
- Synthesise across multiple sources
- Flag gaps in library coverage
- Note when you are drawing on web search vs the library"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_library",
            "description": "Search the reference library for relevant documents. Use this first for any research question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_full_text",
            "description": "Retrieve the full extracted text of a specific reference from the library by its ID. Use when you need more detail than the summary provides.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": "integer", "description": "The ID of the reference"},
                },
                "required": ["reference_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, policy documents, government reports, or news not in the library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search query"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_paper",
            "description": "Look up a specific paper on arXiv by ID (e.g. '2212.08073') or by title/author search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "arXiv ID or search terms"},
                },
                "required": ["query"],
            },
        },
    },
]


async def _tool_search_library(db: AsyncSession, query: str) -> list[dict]:
    terms = query.lower().split()
    conditions = []
    for term in terms[:6]:
        conditions.append(
            or_(
                func.lower(Reference.title).contains(term),
                func.lower(Reference.abstract).contains(term),
                func.lower(Reference.summary).contains(term),
                func.lower(Reference.authors).contains(term),
                func.lower(Reference.full_text).contains(term),
            )
        )
    if not conditions:
        return []
    stmt = (
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(or_(*conditions))
        .order_by(Reference.created_at.desc())
        .limit(8)
    )
    result = await db.execute(stmt)
    refs = result.scalars().all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "authors": r.authors,
            "year": r.year,
            "source_type": r.source_type,
            "abstract": r.abstract,
            "summary": r.summary,
            "tags": [t.tag for t in r.tags],
        }
        for r in refs
    ]


async def _tool_get_full_text(db: AsyncSession, reference_id: int) -> dict:
    result = await db.execute(select(Reference).where(Reference.id == reference_id))
    ref = result.scalar_one_or_none()
    if not ref:
        return {"error": f"Reference {reference_id} not found"}
    return {
        "id": ref.id,
        "title": ref.title,
        "full_text": (ref.full_text or "")[:12000],
    }


async def _tool_web_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                })
        return results
    except Exception as e:
        return [{"error": str(e)}]


async def _tool_lookup_paper(query: str) -> list[dict]:
    import httpx
    import xml.etree.ElementTree as ET

    # If it looks like an arXiv ID, fetch directly
    q = query.strip()
    if q.replace(".", "").replace("/", "").isdigit() or q.startswith("abs/"):
        url = f"https://export.arxiv.org/abs/{q.lstrip('abs/')}"
        params = {"search_query": f"id:{q.lstrip('abs/')}", "max_results": 1}
    else:
        params = {"search_query": f"all:{q}", "max_results": 5, "sortBy": "relevance"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://export.arxiv.org/api/query", params=params)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        results = []
        for entry in root.findall("atom:entry", ns):
            results.append({
                "title": (entry.find("atom:title", ns).text or "").strip(),
                "authors": ", ".join(
                    a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)
                    if a.find("atom:name", ns) is not None
                ),
                "summary": (entry.find("atom:summary", ns).text or "").strip()[:500],
                "url": (entry.find("atom:id", ns).text or "").strip(),
                "published": (entry.find("atom:published", ns).text or "")[:10],
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


async def _dispatch_tool(db: AsyncSession, tool_name: str, tool_input: dict) -> str:
    if tool_name == "search_library":
        result = await _tool_search_library(db, tool_input.get("query", ""))
    elif tool_name == "get_full_text":
        result = await _tool_get_full_text(db, tool_input.get("reference_id", 0))
    elif tool_name == "web_search":
        result = await _tool_web_search(tool_input.get("query", ""), tool_input.get("max_results", 5))
    elif tool_name == "lookup_paper":
        result = await _tool_lookup_paper(tool_input.get("query", ""))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result)


async def chat(
    db: AsyncSession,
    messages: list[dict],
    model: str = "claude-sonnet-4-6",
    system_prompt: str | None = None,
    project_settings: dict | None = None,
) -> AsyncIterator[str]:
    system = system_prompt or DEFAULT_SYSTEM_PROMPT
    if model_supports_tools(model):
        async for chunk in _chat_with_tools(db, messages, model, system, project_settings):
            yield chunk
    else:
        async for chunk in _chat_with_context(db, messages, model, system, project_settings):
            yield chunk


async def _chat_with_tools(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
    project_settings: dict | None = None,
) -> AsyncIterator[str]:
    api_messages = [{"role": "system", "content": system}] + list(messages)
    kwargs = _build_kwargs(model, project_settings=project_settings)
    max_tool_rounds = 6

    for _ in range(max_tool_rounds):
        response = await litellm.acompletion(
            model=model,
            messages=api_messages,
            max_tokens=2048,
            tools=TOOLS,
            tool_choice="auto",
            **kwargs,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or (
            choice.message.tool_calls and len(choice.message.tool_calls) > 0
        ):
            api_messages.append(choice.message)
            for tool_call in choice.message.tool_calls:
                tool_input = json.loads(tool_call.function.arguments)
                tool_result = await _dispatch_tool(db, tool_call.function.name, tool_input)
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
            continue

        yield choice.message.content or ""
        break


async def _chat_with_context(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
    project_settings: dict | None = None,
) -> AsyncIterator[str]:
    """Context-injection for models without tool use (most Ollama models)."""
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    results = await _tool_search_library(db, last_user[:200])

    if results:
        context = "\n\nRelevant library references (auto-retrieved):\n" + json.dumps(results, indent=2)
        augmented = system + context
    else:
        augmented = system + "\n\n(No matching references found in the library for this query.)"

    async for chunk in stream_text(model, list(messages), system=augmented):
        yield chunk
