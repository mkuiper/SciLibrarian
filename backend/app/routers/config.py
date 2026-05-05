"""
System configuration endpoint — returns provider status, Ollama models,
and allows updating global agent model assignments.
"""
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.dependencies import CurrentUser
from app.services.llm import PROVIDER_MODELS

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/status")
async def system_status(current_user: CurrentUser):
    """Return status of all configured AI providers and search sources."""
    providers = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "google": bool(settings.gemini_api_key or settings.google_api_key),
        "ollama": False,
        "vllm": bool(settings.vllm_base_url),
    }
    ollama_models = []
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                providers["ollama"] = True
                ollama_models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass

    search_sources = {
        "arxiv": True,
        "semantic_scholar": True,
        "openalex": True,
        "web": True,
        "semantic_scholar_key": bool(settings.semantic_scholar_api_key),
        "openalex_email": bool(settings.openalex_email),
    }

    email_configured = bool(settings.smtp_host)

    return {
        "providers": providers,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_models": ollama_models,
        "search_sources": search_sources,
        "email_configured": email_configured,
        "default_librarian_model": settings.default_librarian_model,
        "default_ingestion_model": settings.default_ingestion_model,
    }


@router.get("/ollama/models")
async def ollama_models(current_user: CurrentUser):
    """Ping Ollama and return installed models."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return {
                    "connected": True,
                    "base_url": settings.ollama_base_url,
                    "models": [
                        {
                            "name": m["name"],
                            "value": f"ollama/{m['name']}",
                            "size": m.get("size", 0),
                            "modified": m.get("modified_at", ""),
                        }
                        for m in models
                    ],
                }
    except Exception as e:
        pass

    return {
        "connected": False,
        "base_url": settings.ollama_base_url,
        "models": [],
        "error": "Cannot reach Ollama. Make sure it is running and the URL is correct.",
    }
