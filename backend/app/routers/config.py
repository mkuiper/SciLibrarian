"""
System configuration endpoint — returns provider status, live Ollama model list,
and model capability info.
"""
import httpx
from fastapi import APIRouter

from app.config import settings
from app.dependencies import CurrentUser
from app.services.llm import PROVIDER_MODELS, get_ollama_models

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/status")
async def system_status(current_user: CurrentUser):
    """Return status of all configured AI providers and search sources."""
    # Check Ollama connectivity independently of model count
    ollama_reachable = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_reachable = resp.status_code == 200
    except Exception:
        pass

    providers = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai":    bool(settings.openai_api_key),
        "google":    bool(settings.gemini_api_key or settings.google_api_key),
        "ollama":    ollama_reachable,
        "vllm":      bool(settings.vllm_base_url),
    }
    ollama_models = await get_ollama_models()

    return {
        "providers": providers,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_models": [m["name"] for m in ollama_models],
        "search_sources": {
            "arxiv":            True,
            "semantic_scholar": True,
            "openalex":         True,
            "web":              True,
            "semantic_scholar_key": bool(settings.semantic_scholar_api_key),
            "openalex_email":       bool(settings.openalex_email),
        },
        "email_configured": bool(settings.smtp_host),
        "ingest_email_enabled": settings.ingest_email_enabled,
        "default_librarian_model": settings.default_librarian_model,
        "default_ingestion_model": settings.default_ingestion_model,
    }


@router.get("/ollama/models")
async def ollama_models_endpoint(current_user: CurrentUser, refresh: bool = False):
    """Return installed Ollama models with capability info."""
    # First check raw connectivity (independent of model count)
    api_reachable = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            api_reachable = resp.status_code == 200
    except Exception:
        pass

    if not api_reachable:
        return {
            "connected": False,
            "base_url": settings.ollama_base_url,
            "models": [],
            "error": (
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                "The service must be bound to 0.0.0.0 for Docker to reach it. "
                "Fix: sudo systemctl edit ollama → add Environment=OLLAMA_HOST=0.0.0.0 → sudo systemctl restart ollama"
            ),
        }

    models = await get_ollama_models(force=refresh)
    return {
        "connected": True,
        "base_url": settings.ollama_base_url,
        "models": models,
        "model_count": len(models),
    }


@router.get("/models")
async def all_models(current_user: CurrentUser):
    """
    Return all available models grouped by provider.
    Ollama models are fetched live from the Ollama API.
    """
    result = {k: list(v) for k, v in PROVIDER_MODELS.items()}

    ollama_models = await get_ollama_models()
    if ollama_models:
        result["ollama"] = [
            {"value": m["value"], "label": m["label"]}
            for m in ollama_models
        ]
    else:
        result["ollama"] = [
            {"value": "ollama/llama3.1:8b",  "label": "llama3.1:8b (not connected — start Ollama)"},
            {"value": "ollama/gemma4:latest", "label": "gemma4:latest (not connected — start Ollama)"},
        ]

    return result
