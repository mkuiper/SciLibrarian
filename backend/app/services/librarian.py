"""
Alexandria — the SciLibrarian agent.

For models that support tool use (Claude, GPT-4o, Gemini 1.5+), Alexandria
searches the library via function calling. For models that don't (most Ollama
models), search results are pre-fetched and injected into context automatically.
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
Your role is to help researchers find, understand, and synthesise information from the reference library.

When answering questions:
- Search the library for relevant references before answering
- Cite specific papers/documents by their exact titles
- Synthesise information across multiple sources when helpful
- Flag gaps where the library lacks coverage on a topic
- Be precise about what comes from the library vs your training knowledge
- Keep responses focused and actionable for researchers

The library focuses on AI safety: technical papers, evaluations, model cards, government policies, and regulatory frameworks."""


async def search_references(db: AsyncSession, query: str, limit: int = 8) -> list[dict]:
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
        .limit(limit)
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


async def chat(
    db: AsyncSession,
    messages: list[dict],
    model: str = "claude-sonnet-4-6",
    system_prompt: str | None = None,
) -> AsyncIterator[str]:
    """
    Stream a response from Alexandria.
    Uses tool-calling for capable models; context injection for others.
    """
    system = system_prompt or DEFAULT_SYSTEM_PROMPT

    if model_supports_tools(model):
        async for chunk in _chat_with_tools(db, messages, model, system):
            yield chunk
    else:
        async for chunk in _chat_with_context(db, messages, model, system):
            yield chunk


async def _chat_with_tools(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
) -> AsyncIterator[str]:
    """Tool-use path: Alexandria searches via function calling."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_library",
                "description": "Search the reference library. Always call this before answering a research question.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search terms"},
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    api_messages = [{"role": "system", "content": system}] + list(messages)
    kwargs = _build_kwargs(model)

    while True:
        response = await litellm.acompletion(
            model=model,
            messages=api_messages,
            max_tokens=2048,
            tools=tools,
            tool_choice="auto",
            **kwargs,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or (
            choice.message.tool_calls and len(choice.message.tool_calls) > 0
        ):
            tool_call = choice.message.tool_calls[0]
            query = json.loads(tool_call.function.arguments).get("query", "")
            results = await search_references(db, query)

            api_messages.append(choice.message)
            api_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(results),
            })
            continue

        text = choice.message.content or ""
        yield text
        break


async def _chat_with_context(
    db: AsyncSession,
    messages: list[dict],
    model: str,
    system: str,
) -> AsyncIterator[str]:
    """Context-injection path for models without tool-use (e.g. Ollama)."""
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    results = await search_references(db, last_user[:200])

    if results:
        context_block = "\n\nRelevant library references:\n" + json.dumps(results, indent=2)
        augmented_system = system + context_block
    else:
        augmented_system = system + "\n\nThe library has no references matching this query yet."

    async for chunk in stream_text(model, list(messages), system=augmented_system):
        yield chunk
