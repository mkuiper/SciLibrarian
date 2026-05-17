"""
Semantic search via embeddings (Cycle 21).

Embeddings are generated through LiteLLM, which supports:
  - OpenAI (text-embedding-3-small, text-embedding-ada-002)
  - Ollama (nomic-embed-text, mxbai-embed-large)
  - Google (models/embedding-001)

Storage today is a plain JSONB array on `references.embedding` — no pgvector.
That's deliberate: pgvector isn't in the postgres:16-alpine image the project
currently uses, and swapping the image overnight without supervision is risky.
JSONB + Python-side cosine is correct at this scale (hundreds of refs) and
will be invisible to switch to pgvector once the image moves to
pgvector/pgvector:pg16 — at that point `similarity_search` can be rewritten
to push the cosine to the DB.

Dimensions: not enforced. Refs embedded by different models won't compare to
each other — `similarity_search` silently filters refs whose embedding length
doesn't match the query's.
"""
import asyncio
import logging
import math

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.config import settings
from app.models.reference import Reference

logger = logging.getLogger(__name__)


EMBEDDING_MODEL_DEFAULTS = {
    "openai": "text-embedding-3-small",
    "ollama": "ollama/nomic-embed-text",
    "google": "models/embedding-001",
}


def _pick_default_model() -> str | None:
    if settings.openai_api_key:
        return EMBEDDING_MODEL_DEFAULTS["openai"]
    if settings.ollama_base_url:
        return EMBEDDING_MODEL_DEFAULTS["ollama"]
    if settings.gemini_api_key:
        return EMBEDDING_MODEL_DEFAULTS["google"]
    return None


async def get_embedding(text: str, model: str | None = None) -> list[float]:
    """Generate an embedding for the given text using LiteLLM. Returns [] on failure."""
    if not text or not text.strip():
        return []
    if not model:
        model = _pick_default_model()
        if not model:
            return []

    kwargs: dict = {}
    if model.startswith("ollama/"):
        kwargs["api_base"] = settings.ollama_base_url
    elif model.startswith("models/") and settings.gemini_api_key:
        kwargs["api_key"] = settings.gemini_api_key

    truncated = text[:8000]
    try:
        response = await litellm.aembedding(model=model, input=[truncated], **kwargs)
        return list(response.data[0]["embedding"])
    except Exception as e:
        logger.warning(f"get_embedding failed for model={model}: {e}")
        return []


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Caller already checked that lengths match."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def similarity_search(
    db: AsyncSession,
    query_embedding: list[float],
    project_id: int | None = None,
    collection_id: int | None = None,
    limit: int = 20,
) -> list[tuple[Reference, float]]:
    """Return (ref, similarity) tuples sorted by cosine similarity descending.

    Python-side. Project_id is strongly recommended — without it we'd materialise
    every embedded ref in memory.
    """
    if not query_embedding:
        return []

    # Defer full_text so similarity_search doesn't drag ~50KB/ref into memory
    # for every embedded ref. Critical-review finding from Cycle 21.
    stmt = (
        select(Reference)
        .options(selectinload(Reference.tags), defer(Reference.full_text))
        .where(Reference.embedding.isnot(None))
    )
    if project_id is not None:
        stmt = stmt.where(Reference.project_id == project_id)
    if collection_id is not None:
        stmt = stmt.where(Reference.collection_id == collection_id)

    refs = (await db.execute(stmt)).scalars().all()
    qdim = len(query_embedding)

    scored: list[tuple[Reference, float]] = []
    dim_mismatches = 0
    for ref in refs:
        emb = ref.embedding
        if not emb or not isinstance(emb, list):
            continue
        if len(emb) != qdim:
            dim_mismatches += 1
            continue
        scored.append((ref, _cosine(query_embedding, emb)))

    if dim_mismatches:
        logger.info(
            f"similarity_search: skipped {dim_mismatches} refs whose embedding dim "
            f"differs from the query ({qdim}); embed with a single model for best results"
        )

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def embedding_input(ref: Reference) -> str:
    """Compose the text used to embed a reference. Stable across ingest + backfill."""
    parts = [ref.title or ""]
    if ref.abstract:
        parts.append(ref.abstract)
    if ref.summary:
        parts.append(ref.summary)
    return "\n\n".join(p for p in parts if p)


async def maybe_embed_reference(ref: Reference, model: str | None = None) -> list[float]:
    """Best-effort embedding for a reference — returns [] on any failure."""
    text = embedding_input(ref)
    if not text:
        return []
    return await get_embedding(text, model=model)
