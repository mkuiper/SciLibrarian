# Ollama Integration Investigation — 2026-05-05

## Approach and methodology

Worked through this systematically overnight using live testing rather than assumptions.
Also consulted two external agents: Google Gemini CLI (`gemini`) and OpenAI Codex CLI (`codex`).

### Agent collaboration notes

**Gemini (gemini-2.5-pro):** Provided detailed architectural advice. Key suggestions:
- Use in-memory cached model discovery via `/api/tags`
- Maintain own tool-use capability list rather than relying on LiteLLM's database
- Suggested `host.docker.internal` for Docker networking (good general advice)
- Could read and analyse the actual codebase — gave specific, contextual recommendations

**Codex:** Had an expired authentication token and could not respond. Would need `codex login` to use.

**Takeaway:** Using Gemini as a second opinion was genuinely useful — it caught the dynamic model
discovery pattern and confirmed the tool-use family approach. The key diagnostic work (actual LiteLLM
vs Ollama API testing) still needed to be done hands-on; no agent could substitute for live testing.

---

## Findings

### Ollama setup on Mike's machine

- Ollama installed at `/usr/local/bin/ollama`, version 0.21.2
- Running on `localhost:11434`
- **13 models installed** — all large frontier-class models:

| Model | Size | Tool calling | Thinking |
|---|---|---|---|
| gemma4:latest | 9.6 GB | ✓ | No |
| gemma4:26b | 18.0 GB | ✓ | No |
| gemma4:31b | 19.9 GB | ✓ | No |
| qwen3.5:9b / qwen3.5:latest | 6.6 GB | ✓ | Yes |
| qwen3.6:27b | 17.4 GB | ✓ | Yes |
| qwen3.6:35b | 23.9 GB | ✓ | Yes |
| llama3.1:8b | 4.9 GB | ✗ | No |
| deepseek-r1:8b | 5.2 GB | ✗ | Yes |
| medgemma:27b | 17.4 GB | ✗ (not tested) | No |
| medgemma1.5 | 3.3 GB | ✗ (not tested) | No |
| gpt-oss:20b | 13.8 GB | ✗ | No |
| nemotron-cascade-2:30b | 24.3 GB | ✗ | No |

### Problems found

**Problem 1: Wrong Docker IP**
Our code defaulted `OLLAMA_BASE_URL=http://ollama:11434` (the internal Docker Compose Ollama
service URL). Since Mike runs Ollama on the host, the backend couldn't reach it.
- Fix: set `OLLAMA_BASE_URL=http://172.17.0.1:11434` (Docker bridge gateway on Linux)
- `172.17.0.1` confirmed as the Docker bridge IP on this machine

**Problem 2: LiteLLM can't handle thinking models**
qwen3.x and deepseek-r1 are "thinking" models — they output internal reasoning tokens
by default. LiteLLM's ollama provider:
- Cannot forward the `think: false` parameter
- Streaming fails with `Unable to parse ollama chunk` when thinking tokens are present
- Non-streaming returns empty string

**Problem 3: LiteLLM tool-use detection is wrong**
`litellm.supports_function_calling("ollama/gemma4:latest")` returns `False` — but gemma4
actually does support tool calling via Ollama's native API. LiteLLM's model database is
behind Ollama's actual capabilities.

**Problem 4: Hardcoded model list was outdated**
Our `PROVIDER_MODELS["ollama"]` had llama3.2, mistral, qwen2.5:7b — none of which are
installed. Users saw a model list that didn't match reality.

### Solution

**Bypass LiteLLM for all Ollama calls.** Call Ollama's native `/api/chat` API directly:
- Always pass `think: false` to suppress thinking tokens on all models
- For streaming: use `httpx.AsyncClient` + `aiter_lines()` on `/api/chat` with `stream: true`
- For tool calling: pass tools in the native Ollama format
- Result: all 4 tested models work correctly (gemma4, qwen3.5, deepseek-r1, llama3.1)

LiteLLM is still used for cloud providers (Claude, GPT-4o, Gemini) where it works well.

**Dynamic model discovery with caching:**
- `get_ollama_models()` calls `/api/tags` every 30 seconds (cached)
- Returns rich metadata: family, supports_tools, is_thinking, size_gb
- Falls back to stale cache if Ollama is temporarily unreachable
- Frontend model picker shows "(thinking)" and "tools✓" badges

**Correct tool-use family detection:**
Based on live testing, these Ollama model families support tool calling:
`gemma`, `gemma3`, `gemma4`, `qwen3`, `qwen35`, `qwen35moe`

These do NOT (or unreliably): `llama3`, `deepseek-r1`, `medgemma`, `nemotron`, `gpt-oss`

For models without tool calling, Alexandria uses context injection (pre-fetch library
search results and inject into system prompt).

---

## Files changed

| File | Change |
|---|---|
| `backend/app/services/llm.py` | Major rewrite: direct Ollama API, dynamic discovery, thinking model detection |
| `backend/app/services/librarian.py` | Updated tool loop to use native Ollama format |
| `backend/app/routers/librarian.py` | Use `get_ollama_models()` for model list |
| `backend/app/routers/config.py` | Use `get_ollama_models()` with capability info |
| `.env` | OLLAMA_BASE_URL=http://172.17.0.1:11434 |
| `.env.example` | Same fix + better comments |

---

## Recommendations

1. **Use gemma4:latest or qwen3.5:9b as the default Ollama model for Alexandria.**
   Both support tool calling (enabling full library search, web search, arXiv lookup)
   and are available in sizes that run on most hardware.

2. **Run Ollama with GPU support** if available — `ollama serve` will auto-detect NVIDIA/AMD.
   The qwen3.6:27b and gemma4:31b models need a GPU to be responsive.

3. **For the Docker Ollama profile**, when users run `docker-compose --profile ollama up`,
   pull gemma4 and qwen3.5 as the defaults:
   ```bash
   docker-compose exec ollama ollama pull gemma4
   docker-compose exec ollama ollama pull qwen3.5:9b
   ```
