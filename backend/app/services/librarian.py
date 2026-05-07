"""
Alexandria — the SciLibrarian agent.

Uses tool calling when the model supports it; falls back to context injection otherwise.

For Ollama models: calls the native /api/chat API directly (not LiteLLM) because
LiteLLM's ollama provider cannot forward the `think` parameter, causing failures
on thinking models (qwen3.x, deepseek-r1.x).

Tools available to Alexandria:
  - search_library   — full-text search of the reference database
  - get_full_text    — retrieve complete extracted text of a reference by ID
  - web_search       — DuckDuckGo web search for current events and policy docs
  - lookup_paper     — fetch arXiv metadata by ID or search query
"""
import json
from typing import AsyncIterator

import httpx
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reference import Reference
from app.services.llm import (
    model_supports_tools, _build_kwargs, _ollama_base_url,
    _ollama_model_supports_tools, _ollama_stream,
)
import litellm

DEFAULT_SYSTEM_PROMPT = """You are Alexandria, an expert AI research librarian.
Your role is to help researchers find, understand, and synthesise information.

You have access to tools: always search the library before answering research questions.
When the library lacks coverage, use web_search to supplement — but clearly distinguish
library sources from web sources.

When citing library references, include the reference ID in brackets after the title:
e.g. "...as shown in Attention Is All You Need [42]..."
At the end of responses that draw on library content, add a "### Sources" section listing
each cited library reference on its own line as: - [ID] Title"""

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
            "description": "Retrieve the full extracted text of a specific reference by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": "integer"},
                },
                "required": ["reference_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, policy documents, or news not in the library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
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
            "description": "Look up a paper on arXiv by ID (e.g. '2212.08073') or by title/author search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

async def _search_library(db: AsyncSession, query: str, project_id: int | None = None) -> list[dict]:
    q = query.strip()
    if not q:
        return []

    doc = func.concat(
        func.coalesce(Reference.title, ''), ' ',
        func.coalesce(Reference.abstract, ''), ' ',
        func.coalesce(Reference.summary, ''),
    )
    tsvec = func.to_tsvector('english', doc)
    tsq = func.plainto_tsquery('english', q)

    stmt = (
        select(Reference)
        .options(selectinload(Reference.tags))
        .where(tsvec.op('@@')(tsq))
    )
    if project_id:
        stmt = stmt.where(Reference.project_id == project_id)
    stmt = stmt.order_by(func.ts_rank_cd(tsvec, tsq).desc()).limit(8)

    result = await db.execute(stmt)
    return [
        {
            "id": r.id, "title": r.title, "authors": r.authors, "year": r.year,
            "source_type": r.source_type, "abstract": r.abstract, "summary": r.summary,
            "tags": [t.tag for t in r.tags],
        }
        for r in result.scalars().all()
    ]


async def _get_full_text(db: AsyncSession, reference_id: int) -> dict:
    result = await db.execute(select(Reference).where(Reference.id == reference_id))
    ref = result.scalar_one_or_none()
    if not ref:
        return {"error": f"Reference {reference_id} not found"}
    return {"id": ref.id, "title": ref.title, "full_text": (ref.full_text or "")[:12000]}


async def _web_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return [
                {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
                for r in ddgs.text(query, max_results=max_results)
            ]
    except Exception as e:
        return [{"error": str(e)}]


async def _lookup_paper(query: str) -> list[dict]:
    q = query.strip()
    params = (
        {"search_query": f"id:{q.lstrip('abs/')}", "max_results": 1}
        if q.replace(".", "").replace("/", "").isdigit() or q.startswith("abs/")
        else {"search_query": f"all:{q}", "max_results": 5, "sortBy": "relevance"}
    )
    try:
        import xml.etree.ElementTree as ET
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


async def _dispatch_tool(db: AsyncSession, name: str, args: dict, project_id: int | None = None) -> str:
    if name == "search_library":
        return json.dumps(await _search_library(db, args.get("query", ""), project_id=project_id))
    if name == "get_full_text":
        return json.dumps(await _get_full_text(db, args.get("reference_id", 0)))
    if name == "web_search":
        return json.dumps(await _web_search(args.get("query", ""), args.get("max_results", 5)))
    if name == "lookup_paper":
        return json.dumps(await _lookup_paper(args.get("query", "")))
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Main chat function ────────────────────────────────────────────────────────

async def chat(
    db: AsyncSession,
    messages: list[dict],
    model: str = "claude-sonnet-4-6",
    system_prompt: str | None = None,
    project_settings: dict | None = None,
    project_id: int | None = None,
) -> AsyncIterator[str]:
    system = system_prompt or DEFAULT_SYSTEM_PROMPT
    if model.startswith("ollama/"):
        async for chunk in _ollama_chat(db, messages, model, system, project_settings, project_id=project_id):
            yield chunk
    elif model_supports_tools(model):
        async for chunk in _cloud_chat_with_tools(db, messages, model, system, project_settings, project_id=project_id):
            yield chunk
    else:
        async for chunk in _context_injection_chat(db, messages, model, system, project_settings, project_id=project_id):
            yield chunk


async def _ollama_chat(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
    project_settings: dict | None = None,
    project_id: int | None = None,
) -> AsyncIterator[str]:
    """
    Ollama chat using the native /api/chat API.
    Handles tool calling for capable models (gemma4, qwen3.x) and falls back
    to context injection for others (deepseek-r1, llama3.1).
    """
    model_name = model.replace("ollama/", "")
    supports_tools = _ollama_model_supports_tools(model_name)

    if supports_tools:
        async for chunk in _ollama_tool_loop(db, messages, model_name, system, project_settings, project_id=project_id):
            yield chunk
    else:
        # Pre-fetch library results and inject into context
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        results = await _search_library(db, last_user[:200], project_id=project_id)
        if results:
            augmented = system + "\n\nRelevant library references (auto-retrieved):\n" + json.dumps(results, indent=2)
        else:
            augmented = system + "\n\n(No matching references found for this query.)"

        async for text, _ in _ollama_stream(model_name, list(messages), augmented,
                                             project_settings=project_settings):
            if text:
                yield text


async def _ollama_tool_loop(
    db: AsyncSession,
    messages: list[dict],
    model_name: str,
    system: str,
    project_settings: dict | None = None,
    project_id: int | None = None,
) -> AsyncIterator[str]:
    """Ollama tool-calling loop: handle tool calls, then stream final response."""
    from app.services.llm import _ollama_complete

    current_messages = list(messages)
    max_rounds = 5

    for _ in range(max_rounds):
        result = await _ollama_complete(
            model_name, current_messages, system,
            tools=TOOLS, project_settings=project_settings,
        )
        msg = result.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            # Final text response — now stream it
            final_messages = current_messages + [{"role": "assistant", "content": msg.get("content", "")}]
            # Actually just yield the content we already have
            yield msg.get("content", "")
            return

        # Execute tool calls
        current_messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function", {})
            try:
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
            except Exception:
                args = {}
            tool_result = await _dispatch_tool(db, fn.get("name", ""), args, project_id=project_id)
            current_messages.append({
                "role": "tool",
                "content": tool_result,
            })

    # Fallback: stream whatever we have
    async for text, _ in _ollama_stream(model_name, current_messages, system,
                                         project_settings=project_settings):
        if text:
            yield text


async def _cloud_chat_with_tools(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
    project_settings: dict | None = None,
    project_id: int | None = None,
) -> AsyncIterator[str]:
    """Cloud provider chat with tool use (Claude, GPT-4o, Gemini)."""
    api_messages = [{"role": "system", "content": system}] + list(messages)
    kwargs = _build_kwargs(model, project_settings=project_settings)
    max_rounds = 6

    for _ in range(max_rounds):
        response = await litellm.acompletion(
            model=model, messages=api_messages, max_tokens=2048,
            tools=TOOLS, tool_choice="auto", **kwargs,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or (
            choice.message.tool_calls and len(choice.message.tool_calls) > 0
        ):
            api_messages.append(choice.message)
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                result = await _dispatch_tool(db, tc.function.name, args, project_id=project_id)
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            continue

        yield choice.message.content or ""
        return


async def _context_injection_chat(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
    project_settings: dict | None = None,
    project_id: int | None = None,
) -> AsyncIterator[str]:
    """Context injection for models without tool use."""
    from app.services.llm import stream_text
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    results = await _search_library(db, last_user[:200], project_id=project_id)
    if results:
        augmented = system + "\n\nRelevant library references:\n" + json.dumps(results, indent=2)
    else:
        augmented = system + "\n\n(No matching library references found.)"
    async for chunk in stream_text(model, list(messages), augmented, project_settings=project_settings):
        yield chunk
