# Development Log

A chronological record of what was built each cycle and key decisions made along the way.

---

## Cycle 1 — 2026-05-04 — Initial Build

**Goal:** Complete working Cycle 1: auth, projects, collections, ingestion, search, librarian chat, review queue, monitors, digests.

**Built:**
- Full FastAPI backend with PostgreSQL (SQLAlchemy async)
- Alexandria librarian agent using Claude tool-use for library search
- PDF and URL ingestion with Claude-generated metadata, summaries, tags
- Project onboarding: Alexandria generates initial collection taxonomy on project creation
- Hierarchical collection tree (adjacency list)
- PostgreSQL full-text search across all reference fields
- Proactive search monitors (arXiv + Semantic Scholar)
- Human review queue (approve/reject before library commit)
- Monthly digest generation (state-of-the-art synthesis)
- React 18 + Vite + Tailwind frontend
- Typer CLI for batch operations
- Docker Compose for local dev

**Librarian named:** Alexandria (after the Library of Alexandria)

---

## Cycle 2 — 2026-05-05 — Multi-provider LLM + UX Foundations

**Goal:** Multi-provider AI support, configurable agent instructions, PDF viewer, real stats, watch requests UI, OpenAlex search.

**Built:**

### Multi-provider LLM (LiteLLM)
- Replaced all direct Anthropic calls with `litellm` unified interface
- New `services/llm.py`: `complete_text()`, `stream_text()`, `complete()` — works with any provider
- Supports: Anthropic Claude, OpenAI GPT-4o, Google Gemini, Ollama (local), vLLM (self-hosted)
- Tool-use fallback: models without function calling (most Ollama models) get search results injected into context automatically
- Model picker in chat panel groups models by provider

### Hermes Agent Assessment
- Investigated NousResearch Hermes agent (user request)
- **Verdict: not suitable as librarian backend** — Hermes is an autonomous agent *platform* (VPS/Docker + messaging), not a model API. It targets different use cases (autonomous infrastructure tasks via Telegram/Discord).
- Our LiteLLM abstraction covers the same model range and more.

### User-configurable agent instructions
- `PATCH /projects/{id}/settings` endpoint stores: `librarian_model`, `ingestion_model`, `librarian_system_prompt`, `ollama_base_url`
- Settings page in UI: model dropdowns + editable system prompt textarea + reset to default
- Alexandria's system prompt is now fully customisable per project
- Librarian chat sends `project_id` so the correct prompt is used

### Search sources
- Added **OpenAlex** (250M+ scholarly works, free, no API key needed)
- Set `OPENALEX_EMAIL` in `.env` for polite pool (much higher rate limits)
- Monitors now default to arXiv + Semantic Scholar + OpenAlex
- `SEMANTIC_SCHOLAR_API_KEY` optional (increases S2 rate limit from 1 → 100 req/s)
- Documented all search source options in `.env.example`

**Search source summary (no keys required for any of these):**
| Source | Coverage | Rate limit (no key) |
|---|---|---|
| arXiv | CS/ML/Physics preprints | ~3 req/s |
| Semantic Scholar | 200M+ papers | 1 req/s (100 with key) |
| OpenAlex | 250M+ works | 10 req/s (unlimited with email) |

### Frontend fixes
- API client now routes through Vite proxy (`/api`) instead of hardcoded `http://localhost:8000` — more robust in Docker
- Dashboard shows real reference counts + source type breakdown
- Active monitor count in stats
- Settings route + sidebar link

### PDF handling
- `GET /references/{id}/file` serves uploaded PDFs for in-browser viewing
- PDF viewer (iframe with browser PDF renderer) on reference detail page — click "View PDF" to expand
- Extracted text collapsible section on reference page

### Reference actions
- Copy citation (plain text format)
- BibTeX export (download or clipboard)
- Copy title button

### Watch Requests page
- Users describe what Alexandria should look out for in natural language
- Stored per-project with optional keywords and source type filter
- Informs monitor priority in future cycles

### Ollama support
- Ollama models now selectable in all model dropdowns
- `host.docker.internal` configured in docker-compose so backend can reach host Ollama
- Ollama base URL configurable in Settings page
- Default Ollama models listed: llama3.2, llama3.1:8b, mistral, qwen2.5, deepseek-r1, mistral-nemo

---

## Planned: Cycle 3

- Restructure suggestions UI (Alexandria recommends collection reorganisation)
- Bulk actions in review queue (approve all / reject all)
- Reference editing in-place
- Project switching (support multiple active projects)
- Scheduled digest (auto-generate monthly, deliver via email)
- pgvector semantic search upgrade
- Better Ollama model detection (ping `/api/tags` to list installed models)
