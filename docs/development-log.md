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

---

## Cycle 3 — 2026-05-05 — Polish, Bulk Actions, Restructure UI, Inline Editing

**Goal:** Workflow polish, collection restructure UI, bulk review actions, Ollama auto-detection, inline reference editing.

**Built:**

### Restructure analysis page (`/restructure`)
- Alexandria analyses current collections vs actual reference distribution
- Shows prioritised recommendations (split/merge/create/move) with rationale
- Colour-coded by priority (high/medium/low)
- Alexandria's summary quote displayed prominently

### Review queue improvements
- Bulk approve / bulk reject all pending items
- Collection assignment picker per item (choose where approved refs go)
- Item count badge on tab headers
- Improved layout with source badge and search query attribution

### Inline reference editing
- Every field on the reference detail page is now editable in-place
- Hover to reveal pencil icon; click to edit; Enter/Escape to confirm/cancel
- Title, authors, year, source type, summary, abstract all editable
- Collection assignment dropdown inline
- Changes save immediately via PATCH API

### Ollama model auto-detection
- `/librarian/models` now pings the Ollama API to list actually-installed models
- Falls back to static defaults if Ollama is unreachable
- Shows "(local, installed)" label for confirmed models

### Sidebar additions
- Restructure page link added to main navigation

---

## Cycle 4 — 2026-05-05 — Scheduler, Production Deployment, Project Switching

**Built:**

### Automated background scheduler (`services/scheduler.py`)
- APScheduler AsyncIOScheduler running in-process
- Search monitors run every 6 hours (self-gate on daily/weekly frequency per monitor)
- Monthly digests auto-generated on 1st of each month at 08:00 UTC, for all projects
- Scheduler starts on app startup (skipped in test mode)

### Production deployment configuration
- `docker-compose.prod.yml`: production services (no --reload, 2 workers, restart always)
- `nginx/nginx.conf`: nginx reverse proxy with SSL, streaming support for chat, SPA routing
- `frontend/Dockerfile.prod`: multi-stage build — Node builder → nginx serving static files
- CORS tightened to specific origin in production (set `allow_origins` in main.py)

### Project switching
- Multiple projects supported simultaneously
- Sidebar shows project dropdown when >1 project exists
- Active project stored in localStorage for persistence across refreshes

---

## Cycle 5 — 2026-05-05 — Semantic Search Foundation, Deduplication, Tag Editing

**Built:**

### Semantic search foundation (`services/embeddings.py`)
- pgvector dependency added
- `get_embedding()` via LiteLLM — works with OpenAI (text-embedding-3-small), Ollama (nomic-embed-text), Google
- `similarity_search()` using pgvector cosine distance (`<=>` operator)
- Graceful fallback if embedding column not yet added or pgvector not installed
- **Activation:** requires `CREATE EXTENSION IF NOT EXISTS vector;` in PostgreSQL and adding an `embedding` column to the references table (migration pending — will be a separate Alembic migration)

### Review queue deduplication
- Before adding any item to the review queue, check for duplicates by URL (exact) and title (normalised, case-insensitive)
- Also checks the library itself — won't re-queue things already approved
- Reduces noise significantly for monitors that run frequently

### Inline tag editing
- Tags on reference detail page are now editable in-place
- Click pencil → edit comma-separated string → save updates tag list via PATCH API
- Consistent with the inline edit pattern established in Cycle 3

## Planned: Cycle 6 (future)

- Alembic migration to add embedding column + pgvector extension enable
- Background embedding generation for existing references
- Semantic search endpoint wired to frontend search
- Email delivery for monthly digests (SMTP config)
- Batch upload (zip file of PDFs)
- Rate limiting middleware
- Audit log (who added/modified what)

- pgvector semantic/embedding search upgrade (significant quality improvement for retrieval)
- Reference tag editing inline
- Batch upload (zip of PDFs)
- Email delivery for monthly digests (SMTP config)
- Search result deduplication in monitor queue
- OpenAlex abstract inverted index reconstruction (already coded, needs testing)
- Rate limiting and API key validation on startup

- Scheduled digest automation (APScheduler monthly trigger)
- pgvector semantic search upgrade
- Project switching UI (support multiple active projects)
- Email/notification for digest delivery
- Cloud deployment config (production docker-compose, nginx, S3 uploads)
- Reference tag editing inline
- Batch upload (zip file of PDFs)

- Restructure suggestions UI (Alexandria recommends collection reorganisation)
- Bulk actions in review queue (approve all / reject all)
- Reference editing in-place
- Project switching (support multiple active projects)
- Scheduled digest (auto-generate monthly, deliver via email)
- pgvector semantic search upgrade
- Better Ollama model detection (ping `/api/tags` to list installed models)
