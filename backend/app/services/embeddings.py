"""
Semantic search using pgvector.

Embeddings are generated via LiteLLM's embedding API, which supports:
  - OpenAI (text-embedding-3-small, text-embedding-ada-002)
  - Ollama (nomic-embed-text, mxbai-embed-large)
  - Google (models/embedding-001)

The embedding is stored alongside each reference. When a reference is ingested,
its embedding is generated asynchronously and stored in the Reference.embedding column.

pgvector must be enabled in PostgreSQL:
  CREATE EXTENSION IF NOT EXISTS vector;

The Reference model gains an embedding column (Vector(1536) for OpenAI,
Vector(768) for most open-source models).

Design choice: we use 1536 dimensions (OpenAI default) and pad/truncate if needed.
For Ollama models, we use whatever dimension they produce and store it as-is.
The search uses cosine similarity (<=> operator in pgvector).
"""
import litellm
from app.config import settings


EMBEDDING_MODEL_DEFAULTS = {
    "openai": "text-embedding-3-small",
    "ollama": "ollama/nomic-embed-text",
    "google": "models/embedding-001",
}


async def get_embedding(text: str, model: str | None = None) -> list[float]:
    """Generate an embedding for the given text using LiteLLM."""
    if not model:
        if settings.openai_api_key:
            model = EMBEDDING_MODEL_DEFAULTS["openai"]
        elif settings.ollama_base_url:
            model = EMBEDDING_MODEL_DEFAULTS["ollama"]
        else:
            return []

    kwargs: dict = {}
    if model.startswith("ollama/"):
        kwargs["api_base"] = settings.ollama_base_url
    elif model.startswith("models/") and settings.gemini_api_key:
        kwargs["api_key"] = settings.gemini_api_key

    truncated = text[:8000]

    try:
        response = await litellm.aembedding(model=model, input=[truncated], **kwargs)
        return response.data[0]["embedding"]
    except Exception:
        return []


async def similarity_search(
    db,
    query_embedding: list[float],
    limit: int = 20,
    collection_id: int | None = None,
    project_id: int | None = None,
) -> list:
    """
    Find references most similar to the query embedding using cosine distance.
    Requires pgvector extension and the embedding column on the Reference table.
    Falls back gracefully if embedding column doesn't exist yet.
    """
    if not query_embedding:
        return []

    try:
        from sqlalchemy import text as sql_text
        conditions = ["embedding IS NOT NULL"]
        params: dict = {"embedding": str(query_embedding), "limit": limit}

        if collection_id:
            conditions.append("collection_id = :collection_id")
            params["collection_id"] = collection_id
        if project_id:
            conditions.append("project_id = :project_id")
            params["project_id"] = project_id

        where = " AND ".join(conditions)
        q = sql_text(f"""
            SELECT id, title, authors, year, source_type, abstract, summary, url, file_name,
                   collection_id, created_at,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM references
            WHERE {where}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """)
        result = await db.execute(q, params)
        return result.mappings().all()
    except Exception:
        return []
