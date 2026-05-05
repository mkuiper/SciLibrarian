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
    providers = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai":    bool(settings.openai_api_key),
        "google":    bool(settings.gemini_api_key or settings.google_api_key),
        "ollama":    False,
        "vllm":      bool(settings.vllm_base_url),
    }
    ollama_models = await get_ollama_models()
    if ollama_models:
        providers["ollama"] = True

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
    models = await get_ollama_models(force=refresh)
    connected = bool(models)

    if not connected:
        return {
            "connected": False,
            "base_url": settings.ollama_base_url,
            "models": [],
            "error": (
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                "Check that Ollama is running and OLLAMA_BASE_URL is correct in .env. "
                f"For host Ollama on Linux, set OLLAMA_BASE_URL=http://172.17.0.1:11434"
            ),
        }

    return {
        "connected": True,
        "base_url": settings.ollama_base_url,
        "models": models,
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
