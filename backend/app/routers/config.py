"""
System configuration endpoint — returns provider status, live Ollama model list,
model capability info, API key health checks, and system status.
"""
import os
import time
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.dependencies import DB, CurrentUser
from app.services.llm import PROVIDER_MODELS, get_ollama_models

logger = logging.getLogger(__name__)
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


@router.get("/ollama/diagnostics")
async def ollama_diagnostics(current_user: CurrentUser):
    """Comprehensive Ollama reachability + state probe.

    Tries the configured URL plus a fixed list of common alternatives, measures
    latency, fetches currently-loaded models (/api/ps) and installed models
    (/api/tags). Returns categorised remediation when nothing responds.

    Probes run in parallel so worst-case latency is ~3s (one timeout) not 15s.
    """
    import asyncio

    candidates = [settings.ollama_base_url]
    for alt in (
        "http://host.docker.internal:11434",
        "http://172.17.0.1:11434",
        "http://localhost:11434",
        "http://ollama:11434",
    ):
        if alt not in candidates:
            candidates.append(alt)

    async def _probe(url: str) -> dict:
        t0 = time.perf_counter()
        result = {"url": url, "reachable": False, "latency_ms": None, "error": None, "version": None}
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{url}/api/version")
                result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                if resp.status_code == 200:
                    result["reachable"] = True
                    try:
                        result["version"] = resp.json().get("version")
                    except Exception:
                        pass
                else:
                    result["error"] = f"HTTP {resp.status_code}"
        except httpx.ConnectError:
            result["error"] = "connection refused / no route"
        except httpx.ReadTimeout:
            result["error"] = "timeout after 3s"
        except Exception as e:
            result["error"] = f"{e.__class__.__name__}: {str(e)[:80]}"
        return result

    probes = await asyncio.gather(*[_probe(u) for u in candidates])
    # Pick the first reachable URL deterministically (preserving candidates order — configured URL first)
    any_reachable = next((p["url"] for p in probes if p["reachable"]), None)

    # Fetch live state from whichever URL works. Critically: use any_reachable,
    # not settings.ollama_base_url — when configured is dead but a fallback works,
    # the user needs to see what's actually installed, not an empty list.
    loaded_models = []
    installed_models = []
    if any_reachable:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                resp = await client.get(f"{any_reachable}/api/ps")
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        raw_size = m.get("size_vram") or m.get("size") or 0
                        loaded_models.append({
                            "name": m.get("name"),
                            "size_mb": round(raw_size / (1024 * 1024)) if raw_size else None,
                            "expires_at": m.get("expires_at"),
                        })
            except Exception as e:
                logger.debug(f"/api/ps probe failed: {e}")
            try:
                resp = await client.get(f"{any_reachable}/api/tags")
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        installed_models.append({"name": m.get("name"), "supports_tools": None})
            except Exception as e:
                logger.debug(f"/api/tags fetch from {any_reachable} failed: {e}")

    # Build categorised remediation guidance based on what we saw
    remediation = []
    configured_url = settings.ollama_base_url
    configured_reachable = any(p["reachable"] and p["url"] == configured_url for p in probes)
    if not any_reachable:
        remediation.append({
            "title": "No Ollama instance is reachable",
            "steps": [
                "Check that Ollama is running: `systemctl status ollama` on the host",
                "If installed via systemd, ensure it's bound to 0.0.0.0 so containers can reach it:",
                "  sudo mkdir -p /etc/systemd/system/ollama.service.d",
                "  echo -e '[Service]\\nEnvironment=\"OLLAMA_HOST=0.0.0.0:11434\"' | sudo tee /etc/systemd/system/ollama.service.d/override.conf",
                "  sudo systemctl daemon-reload && sudo systemctl restart ollama",
                "If running inside Docker, start with: docker-compose --profile ollama up",
            ],
        })
    elif not configured_reachable:
        remediation.append({
            "title": f"Configured OLLAMA_BASE_URL ({configured_url}) is not responding, but Ollama IS reachable at {any_reachable}",
            "steps": [
                f"Update .env: OLLAMA_BASE_URL={any_reachable}",
                "Restart the backend container: docker-compose restart backend",
            ],
        })
    elif loaded_models == []:
        remediation.append({
            "title": "Ollama is reachable but no model is currently loaded",
            "steps": [
                "Models load on first chat request — this isn't necessarily a problem",
                "If responses are slow, pre-load with: `ollama run <model> ''` from the host",
            ],
        })

    return {
        "configured_url": configured_url,
        "any_reachable": any_reachable,
        "probes": probes,
        "loaded_models": loaded_models,
        "installed_count": len(installed_models),
        "installed_models": installed_models,
        "remediation": remediation,
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


# ── Global model override ─────────────────────────────────────────────────────

class ModelOverrideRequest(BaseModel):
    model: str | None  # null/empty clears the override


@router.get("/overrides")
async def get_overrides(current_user: CurrentUser):
    """Return any active app-wide overrides (currently just model_override)."""
    from app.services import app_settings
    return {"model_override": await app_settings.get("model_override")}


@router.put("/overrides/model")
async def set_model_override(body: ModelOverrideRequest, current_user: CurrentUser):
    """Set or clear the global model override.

    When set, every agent call (librarian chat, ingestion, digests, monitor
    suggestions) uses this model regardless of per-project settings.
    """
    from app.services import app_settings
    m = (body.model or "").strip() or None
    if m:
        await app_settings.set_value("model_override", m)
    else:
        await app_settings.delete("model_override")
    return {"model_override": m}


# ── API key health check ──────────────────────────────────────────────────────

class KeyTestRequest(BaseModel):
    provider: str          # "anthropic" | "openai" | "google"
    key: str = ""          # if empty, uses .env key


_PROVIDER_TEST_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai":    "gpt-4o-mini",
    "google":    "gemini/gemini-1.5-flash",
}

_PROVIDER_ENV_KEY = {
    "anthropic": "anthropic_api_key",
    "openai":    "openai_api_key",
    "google":    "gemini_api_key",
}


@router.post("/test-key")
async def test_api_key(body: KeyTestRequest, current_user: CurrentUser):
    """Make a minimal 1-token API call to verify a key. Returns model name + latency."""
    import litellm

    model = _PROVIDER_TEST_MODEL.get(body.provider)
    if not model:
        raise HTTPException(400, f"Unknown provider: {body.provider}")

    env_attr = _PROVIDER_ENV_KEY.get(body.provider, "")
    effective_key = body.key.strip() or getattr(settings, env_attr, "")
    if not effective_key:
        return {"ok": False, "error": "No API key configured — enter one above or set it in .env"}

    t0 = time.perf_counter()
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
            api_key=effective_key,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": True, "model": response.model or model, "latency_ms": latency_ms}
    except Exception as e:
        err = str(e)
        if "AuthenticationError" in err or "invalid_api_key" in err.lower() or "401" in err:
            msg = "Invalid API key"
        elif "RateLimitError" in err or "429" in err:
            msg = "Rate limited — but key appears valid"
        elif "insufficient_quota" in err.lower():
            msg = "Quota exceeded — key is valid but has no credits"
        elif "model_not_found" in err.lower() or "404" in err:
            msg = "Model not found — key may be valid but lacks access"
        else:
            msg = err[:120]
        return {"ok": False, "error": msg}


# ── System status ─────────────────────────────────────────────────────────────

def _dir_stats(path: str) -> dict:
    """Count files and total size under a directory."""
    total_bytes = 0
    count = 0
    try:
        for dirpath, _, files in os.walk(path):
            for fname in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(dirpath, fname))
                    count += 1
                except OSError:
                    pass
    except OSError:
        pass
    return {"count": count, "total_mb": round(total_bytes / (1024 * 1024), 1)}


@router.get("/system")
async def system_status_detail(db: DB, current_user: CurrentUser):
    """
    Return detailed system health: DB stats, upload storage, scheduler state.
    """
    from sqlalchemy import select, func, text
    from app.models.reference import Reference
    from app.models.review_queue import ReviewQueueItem
    from app.services.scheduler import get_scheduler

    # DB stats
    try:
        ref_count = (await db.execute(select(func.count(Reference.id)))).scalar_one()
        pending_queue = (await db.execute(
            select(func.count(ReviewQueueItem.id))
            .where(ReviewQueueItem.status == "pending")
        )).scalar_one()
        db_ok = True
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        ref_count = pending_queue = 0
        db_ok = False

    # Storage
    storage = _dir_stats(settings.upload_dir)

    # Scheduler
    scheduler_info = {"running": False, "paused": False, "jobs": []}
    try:
        sched = get_scheduler()
        if sched is not None:
            scheduler_info["running"] = sched.running
            scheduler_info["paused"] = sched.state == 2  # STATE_PAUSED = 2
            for job in sched.get_jobs():
                nrt = job.next_run_time
                scheduler_info["jobs"].append({
                    "id": job.id,
                    "next_run": nrt.isoformat() if nrt else None,
                })
    except Exception as e:
        logger.debug(f"Scheduler status error: {e}")

    return {
        "database": {
            "ok": db_ok,
            "reference_count": ref_count,
            "pending_queue": pending_queue,
        },
        "storage": {
            "upload_dir": settings.upload_dir,
            **storage,
        },
        "scheduler": scheduler_info,
    }


# ── Scheduler control ─────────────────────────────────────────────────────────

@router.post("/scheduler/{action}")
async def scheduler_control(action: str, current_user: CurrentUser):
    """Pause or resume the background job scheduler without restarting."""
    from app.services.scheduler import get_scheduler

    if action not in ("pause", "resume"):
        raise HTTPException(400, "action must be 'pause' or 'resume'")

    sched = get_scheduler()
    if sched is None or not sched.running:
        raise HTTPException(503, "Scheduler is not running")

    if action == "pause":
        sched.pause()
        return {"ok": True, "state": "paused"}
    else:
        sched.resume()
        return {"ok": True, "state": "running"}
