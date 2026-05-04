import json
from typing import AsyncIterator

import anthropic
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.reference import Reference, ReferenceTag


SYSTEM_PROMPT = """You are the SciLibrarian — an expert AI research librarian for the Australian AI Safety Institute.
Your role is to help researchers find, understand, and synthesise information from the reference library.

You have access to search the reference database. When answering questions:
- Search the library for relevant references
- Cite specific papers/documents using their titles
- Synthesise information across multiple sources when helpful
- Flag gaps where the library lacks coverage
- Be precise about what you know from the library vs your training knowledge

The library focuses on AI safety: technical papers, evaluations, model cards, government policies, and regulatory frameworks."""


async def search_references_for_librarian(db: AsyncSession, query: str, limit: int = 8) -> list[dict]:
    terms = query.lower().split()
    conditions = []
    for term in terms[:5]:
        conditions.append(
            or_(
                func.lower(Reference.title).contains(term),
                func.lower(Reference.abstract).contains(term),
                func.lower(Reference.summary).contains(term),
                func.lower(Reference.authors).contains(term),
            )
        )
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


async def chat_with_librarian(
    db: AsyncSession,
    messages: list[dict],
    model: str = "claude-sonnet-4-6",
) -> AsyncIterator[str]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    tools = [
        {
            "name": "search_library",
            "description": "Search the reference library for relevant documents. Use this for every user query before answering.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms to find relevant references"},
                },
                "required": ["query"],
            },
        }
    ]

    api_messages = list(messages)

    while True:
        response = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=api_messages,
        )

        if response.stop_reason == "tool_use":
            tool_use_block = next(b for b in response.content if b.type == "tool_use")
            query = tool_use_block.input["query"]
            results = await search_references_for_librarian(db, query)

            api_messages.append({"role": "assistant", "content": response.content})
            api_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": json.dumps(results),
                }],
            })
            continue

        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        yield text
        break
