"""
Unified LLM service.

Cloud providers (Claude, GPT, Gemini, vLLM): use LiteLLM.
Ollama (local): call Ollama's native /api/chat directly.
  - Reason: LiteLLM's ollama provider cannot forward the `think` parameter,
    causing streaming failures on thinking models (qwen3.x, deepseek-r1).
    Direct API calls work reliably for all model families.

Tested model capabilities (2026-05-05):
  gemma4       — text ✓  streaming ✓  tool-calling ✓
  qwen3.5/3.6  — text ✓  streaming ✓  tool-calling ✓  [thinking model, think=False]
  llama3.1:8b  — text ✓  streaming ✓  tool-calling ✗  [use context injection]
  deepseek-r1  — text ✓  streaming ✓  tool-calling ✗  [thinking model, think=False]
  medgemma     — not tested for tools
"""
import json
import logging
import time
from typing import AsyncIterator

import httpx
import litellm
from litellm import acompletion

from app.config import settings

litellm.drop_params = True
litellm.set_verbose = False
logger = logging.getLogger(__name__)

# ── Model capability knowledge ────────────────────────────────────────────────

# Ollama model families that produce thinking tokens by default.
# These need `think: false` in every request to get clean output.
OLLAMA_THINKING_FAMILIES = {"qwen3", "deepseek-r1", "qwen35moe", "qwen3moe"}

# Ollama model families confirmed to support function/tool calling via Ollama API.
# Based on live testing. Does NOT match LiteLLM's internal database (which is outdated).
OLLAMA_TOOL_FAMILIES = {"gemma", "gemma4", "gemma3", "qwen3", "qwen35", "qwen35moe"}

# Cloud model prefixes that support tool use (LiteLLM handles these)
CLOUD_TOOL_PREFIXES = {"claude-", "gpt-4o", "gpt-4-turbo", "gemini/gemini-1.5", "gemini/gemini-2"}

# ── Model metadata cache ───────────────────────────────────────────────────────

_ollama_cache: dict = {"ts": 0, "models": [], "info": {}}


def _parse_ollama_family(model_name: str) -> str:
    """Extract normalised family name from a model name like 'qwen3.5:9b'."""
    base = model_name.split(":")[0].lower()
    # Normalise: qwen3.5 → qwen3, deepseek-r1 → deepseek-r1
    for fam in ["qwen35moe", "qwen3moe", "qwen35", "qwen3", "deepseek-r1",
                "gemma4", "gemma3", "gemma", "llama3", "llama",
                "mistral", "phi3", "phi", "medgemma", "nemotron"]:
        if base.startswith(fam):
            return fam
    return base


def _ollama_model_is_thinking(model_name: str) -> bool:
    return _parse_ollama_family(model_name) in OLLAMA_THINKING_FAMILIES


def _ollama_model_supports_tools(model_name: str) -> bool:
    return _parse_ollama_family(model_name) in OLLAMA_TOOL_FAMILIES


async def get_ollama_models(force: bool = False, ttl: int = 30) -> list[dict]:
    """
    Fetch installed Ollama models with model capability info.
    Returns list of dicts: {value, label, supports_tools, is_thinking}
    Cached for `ttl` seconds.
    """
    global _ollama_cache
    if not force and time.time() - _ollama_cache["ts"] < ttl:
        return _ollama_cache["models"]

    base_url = settings.ollama_base_url
    if not base_url:
        return []

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            raw = resp.json().get("models", [])

        models = []
        for m in raw:
            name = m["name"]
            family = _parse_ollama_family(name)
            supports_tools = _ollama_model_supports_tools(name)
            is_thinking = _ollama_model_is_thinking(name)
            size_gb = round(m.get("size", 0) / 1e9, 1)

            label_parts = [name, f"{size_gb}GB"]
            if is_thinking:
                label_parts.append("thinking")
            if supports_tools:
                label_parts.append("tools✓")

            models.append({
                "value": f"ollama/{name}",
                "label": f"{name} ({', '.join(label_parts[1:])})",
                "name": name,
                "family": family,
                "supports_tools": supports_tools,
                "is_thinking": is_thinking,
                "size_gb": size_gb,
            })

        _ollama_cache = {"ts": time.time(), "models": models, "info": {m["name"]: m for m in raw}}
        logger.info(f"Ollama: found {len(models)} models at {base_url}")
        return models

    except Exception as e:
        logger.warning(f"Ollama not reachable at {base_url}: {e}")
        return _ollama_cache["models"]  # return stale cache rather than empty


# ── Provider model lists ──────────────────────────────────────────────────────

PROVIDER_MODELS = {
    "anthropic": [
        {"value": "claude-sonnet-4-6",        "label": "Claude Sonnet 4.6 (recommended)"},
        {"value": "claude-opus-4-7",           "label": "Claude Opus 4.7 (most capable)"},
        {"value": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 (fastest)"},
    ],
    "openai": [
        {"value": "gpt-4o",      "label": "GPT-4o"},
        {"value": "gpt-4o-mini", "label": "GPT-4o mini"},
        {"value": "gpt-4-turbo", "label": "GPT-4 Turbo"},
    ],
    "google": [
        {"value": "gemini/gemini-1.5-pro",   "label": "Gemini 1.5 Pro"},
        {"value": "gemini/gemini-1.5-flash", "label": "Gemini 1.5 Flash"},
        {"value": "gemini/gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
    ],
    "vllm": [
        {"value": "openai/your-model-name", "label": "vLLM custom model"},
    ],
    # Ollama is populated dynamically at runtime from get_ollama_models()
    "ollama": [],
}


# ── Tool-use capability ───────────────────────────────────────────────────────

def model_supports_tools(model: str) -> bool:
    if model.startswith("ollama/"):
        name = model.replace("ollama/", "")
        return _ollama_model_supports_tools(name)
    return any(model.startswith(p) for p in CLOUD_TOOL_PREFIXES)


# ── LiteLLM kwargs builder (cloud providers only) ────────────────────────────

def _build_kwargs(model: str, extra: dict | None = None, project_settings: dict | None = None) -> dict:
    ps = project_settings or {}
    kwargs: dict = {}

    if model.startswith("claude-"):
        key = ps.get("anthropic_api_key") or settings.anthropic_api_key
        if key:
            kwargs["api_key"] = key
    elif model.startswith("gpt-") or (model.startswith("openai/") and settings.vllm_base_url):
        key = ps.get("openai_api_key") or settings.openai_api_key
        if key:
            kwargs["api_key"] = key
        if model.startswith("openai/") and settings.vllm_base_url:
            kwargs["api_base"] = settings.vllm_base_url
    elif model.startswith("gemini/"):
        key = ps.get("gemini_api_key") or settings.gemini_api_key or settings.google_api_key
        if key:
            kwargs["api_key"] = key

    if extra:
        kwargs.update(extra)
    return kwargs


# ── Direct Ollama caller ──────────────────────────────────────────────────────

def _ollama_base_url(project_settings: dict | None = None) -> str:
    ps = project_settings or {}
    return ps.get("ollama_base_url") or settings.ollama_base_url or "http://localhost:11434"


async def _ollama_complete(
    model_name: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 2000,
    tools: list | None = None,
    project_settings: dict | None = None,
) -> dict:
    """Non-streaming Ollama completion via native /api/chat API."""
    base_url = _ollama_base_url(project_settings)
    thinking = _ollama_model_is_thinking(model_name)
    supports_tools = _ollama_model_supports_tools(model_name)

    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    payload: dict = {
        "model": model_name,
        "messages": all_messages,
        "stream": False,
        "think": False,  # always off — thinking adds latency without benefit here
        "options": {"num_predict": max_tokens},
    }

    if tools and supports_tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()


async def _ollama_stream(
    model_name: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 2048,
    tools: list | None = None,
    project_settings: dict | None = None,
) -> AsyncIterator[tuple[str, list]]:
    """
    Streaming Ollama completion via native /api/chat API.
    Yields (text_chunk, tool_calls) tuples.
    text_chunk is a string fragment; tool_calls is a list (usually populated only on the last message).
    """
    base_url = _ollama_base_url(project_settings)
    supports_tools = _ollama_model_supports_tools(model_name)

    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    payload: dict = {
        "model": model_name,
        "messages": all_messages,
        "stream": True,
        "think": False,
        "options": {"num_predict": max_tokens},
    }

    if tools and supports_tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for raw_line in resp.aiter_lines():
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                msg = chunk.get("message", {})
                text = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])

                if text or tool_calls:
                    yield text, tool_calls

                if chunk.get("done"):
                    break


# ── Public interface ──────────────────────────────────────────────────────────

async def complete_text(
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 2000,
    project_settings: dict | None = None,
) -> str:
    """Single prompt → text response. Works for all providers."""
    messages = [{"role": "user", "content": prompt}]

    if model.startswith("ollama/"):
        model_name = model.replace("ollama/", "")
        result = await _ollama_complete(model_name, messages, system, max_tokens,
                                        project_settings=project_settings)
        return result.get("message", {}).get("content", "")

    # Cloud providers via LiteLLM
    api_messages = []
    if system:
        api_messages.append({"role": "system", "content": system})
    api_messages.extend(messages)

    kwargs = _build_kwargs(model, project_settings=project_settings)
    resp = await acompletion(model=model, messages=api_messages, max_tokens=max_tokens, **kwargs)
    return resp.choices[0].message.content or ""


async def stream_text(
    model: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 2048,
    project_settings: dict | None = None,
) -> AsyncIterator[str]:
    """Streaming text completion. Works for all providers."""
    if model.startswith("ollama/"):
        model_name = model.replace("ollama/", "")
        async for text, _ in _ollama_stream(model_name, messages, system, max_tokens,
                                             project_settings=project_settings):
            if text:
                yield text
        return

    # Cloud providers via LiteLLM streaming
    api_messages = []
    if system:
        api_messages.append({"role": "system", "content": system})
    api_messages.extend(messages)

    kwargs = _build_kwargs(model, project_settings=project_settings)
    kwargs["stream"] = True
    resp = await acompletion(model=model, messages=api_messages, max_tokens=max_tokens, **kwargs)
    async for chunk in resp:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


async def complete(
    model: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 2000,
    tools: list | None = None,
    tool_choice: str | None = None,
    project_settings: dict | None = None,
) -> dict:
    """Single completion call (non-streaming). Returns raw response dict."""
    if model.startswith("ollama/"):
        model_name = model.replace("ollama/", "")
        return await _ollama_complete(model_name, messages, system, max_tokens,
                                      tools=tools, project_settings=project_settings)

    api_messages = []
    if system:
        api_messages.append({"role": "system", "content": system})
    api_messages.extend(messages)

    kwargs = _build_kwargs(model, project_settings=project_settings)
    if tools and model_supports_tools(model):
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    return await acompletion(model=model, messages=api_messages, max_tokens=max_tokens, **kwargs)
