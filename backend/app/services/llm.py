"""
Unified LLM service using LiteLLM.

Supports: Anthropic (Claude), OpenAI, Google (Gemini), Ollama (local),
vLLM (OpenAI-compatible local serving), and any other LiteLLM-supported provider.

Model string format:
  - Claude:  "claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"
  - OpenAI:  "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"
  - Gemini:  "gemini/gemini-1.5-pro", "gemini/gemini-1.5-flash"
  - Ollama:  "ollama/llama3.2", "ollama/mistral", "ollama/qwen2.5"
  - vLLM:    "openai/your-model-name" (set vllm_base_url in config)
"""
import os
from typing import AsyncIterator, Optional

import litellm
from litellm import acompletion

from app.config import settings

litellm.drop_params = True
litellm.set_verbose = False

PROVIDER_MODELS = {
    "anthropic": [
        {"value": "claude-sonnet-4-6",        "label": "Claude Sonnet 4.6 (recommended)"},
        {"value": "claude-opus-4-7",           "label": "Claude Opus 4.7 (most capable)"},
        {"value": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 (fastest)"},
    ],
    "openai": [
        {"value": "gpt-4o",       "label": "GPT-4o"},
        {"value": "gpt-4o-mini",  "label": "GPT-4o mini (faster)"},
        {"value": "gpt-4-turbo",  "label": "GPT-4 Turbo"},
    ],
    "google": [
        {"value": "gemini/gemini-1.5-pro",   "label": "Gemini 1.5 Pro"},
        {"value": "gemini/gemini-1.5-flash", "label": "Gemini 1.5 Flash (faster)"},
        {"value": "gemini/gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
    ],
    "ollama": [
        {"value": "ollama/llama3.2",          "label": "Llama 3.2 (local)"},
        {"value": "ollama/llama3.1:8b",       "label": "Llama 3.1 8B (local)"},
        {"value": "ollama/mistral",            "label": "Mistral (local)"},
        {"value": "ollama/qwen2.5:7b",        "label": "Qwen 2.5 7B (local)"},
        {"value": "ollama/deepseek-r1:7b",    "label": "DeepSeek-R1 7B (local, reasoning)"},
        {"value": "ollama/mistral-nemo",      "label": "Mistral Nemo (local)"},
    ],
    "vllm": [
        {"value": "openai/your-model-name", "label": "vLLM custom model"},
    ],
}

TOOL_USE_CAPABLE = {
    "claude-", "gpt-4o", "gpt-4-turbo", "gemini/gemini-1.5",
    "gemini/gemini-2",
}


def model_supports_tools(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in TOOL_USE_CAPABLE)


def _build_kwargs(model: str, extra: dict | None = None, project_settings: dict | None = None) -> dict:
    """
    Build LiteLLM keyword arguments for a model call.
    project_settings can override system API keys with per-project keys.
    """
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
    elif model.startswith("ollama/"):
        kwargs["api_base"] = ps.get("ollama_base_url") or settings.ollama_base_url

    if extra:
        kwargs.update(extra)
    return kwargs


async def complete(
    model: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 2000,
    tools: list | None = None,
    tool_choice: str | None = None,
) -> dict:
    """Single completion call. Returns the response message dict."""
    api_messages = []
    if system:
        api_messages.append({"role": "system", "content": system})
    api_messages.extend(messages)

    kwargs = _build_kwargs(model)
    kwargs["model"] = model
    kwargs["messages"] = api_messages
    kwargs["max_tokens"] = max_tokens
    if tools and model_supports_tools(model):
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    response = await acompletion(**kwargs)
    return response


async def complete_text(
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 2000,
) -> str:
    """Convenience wrapper: single user prompt → text response."""
    resp = await complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        system=system,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def stream_text(
    model: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    """Streaming text completion."""
    api_messages = []
    if system:
        api_messages.append({"role": "system", "content": system})
    api_messages.extend(messages)

    kwargs = _build_kwargs(model)
    kwargs["model"] = model
    kwargs["messages"] = api_messages
    kwargs["max_tokens"] = max_tokens
    kwargs["stream"] = True

    response = await acompletion(**kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
