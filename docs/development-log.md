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

---

## Cycle 7 — 2026-05-05 — Ollama-in-Docker, Alexandria Tools, Email Ingestion, Broad Domains

**Built:**

### Ollama as Docker Compose service
- Add `ollama` service using Docker Compose profiles
- `docker-compose --profile ollama up` → self-contained AI stack
- Backend defaults `OLLAMA_BASE_URL=http://ollama:11434` (internal Docker network)
- No more host.docker.internal fragility on Linux
- GPU support: uncomment `deploy.resources.reservations` block
- Models pulled with: `docker-compose exec ollama ollama pull llama3.2`

### Alexandria's expanded toolkit (4 tools)
- `search_library`: full-text search (existing)
- `get_full_text`: retrieve complete extracted text of a specific reference
- `web_search`: DuckDuckGo for policy docs, news, government reports
- `lookup_paper`: fetch arXiv paper metadata by ID or title search
- Up to 6 tool-call rounds per message (supports complex multi-step retrieval)
- Parallel tool results accumulated before generating response

### Email ingestion (IMAP polling)
- `services/email_ingest.py`: polls IMAP inbox on a schedule
- Processes PDF attachments → full ingestion pipeline
- Extracts and processes URLs from subject and body (up to 5 per email)
- Subject line used to guess target collection
- Confirmation reply sent to sender (if SMTP configured)
- Scheduler runs every INGEST_CHECK_INTERVAL_MINUTES (default 10)
- Works with Gmail (App Password), Outlook, Fastmail, any IMAP provider

### API key / Pro account clarification
- Added explicit note in Config page: consumer Pro subscriptions ≠ developer API access
- Per-project API key overrides added (Anthropic/OpenAI/Gemini per project)
- _build_kwargs() in llm.py: project key takes priority over system .env key

### Broad research domains
- Expanded from 14 AI-specific domains to 50+ suggestions across all fields
- Biology, Chemistry, Physics, Engineering, Social Sciences, Humanities, etc.
- Free-form tag input with autocomplete — not restricted to suggestions

### Documentation
- README.md: comprehensive rewrite covering all features, Ollama setup,
  email ingestion, API key clarification, CLI usage, architecture overview
- .env.example: full email ingestion config with Gmail setup notes

---

## Cycle 8 — 2026-05-08 — Search Quality, Research Intelligence, Evidence Trails

**Goal:** Eight targeted improvement rounds covering search quality, research workflow, AI output trust, and admin tooling.

### Round 1 — PostgreSQL full-text search (`services/search.py`, `database.py`)
- Replaced ILIKE substring scan with `to_tsvector` / `plainto_tsquery`
- GIN index on `concat(title, abstract, summary)` added via migration
- Weighted ranking: `ts_rank_cd` with title weighted higher
- `ts_headline` snippets returned with every search result
- Search service returns `(refs, snippets, total)` tuple

### Round 2 — Search filter UI (`Library.jsx`, `ReferenceCard.jsx`)
- Year-range inputs (`year_from` / `year_to`) added
- `important` quick-filter added alongside starred/unread
- All filters now sent server-side (were client-side)
- FTS snippets displayed in italic below the title in search results

### Round 3 — Ingestion deduplication (`routers/references.py`)
- `_find_duplicate()` checks URL (exact) and normalised title before creating any Reference
- Returns HTTP 409 with `existing_id` so the caller can redirect rather than lose work
- URL check runs before the ingestion LLM call (saves API cost); title check runs after

### Round 4 — Research Radar (`routers/projects.py`, `Dashboard.jsx`, `client.js`)
- New `GET /projects/{id}/radar` endpoint: new refs in 7 days, recent additions, trending tags from 30 days, pending queue depth, active monitor count
- Dashboard Radar panel sits above the library breakdown with two columns: recent additions and trending topic tags

### Round 5 — Enhanced reading states (`ReferenceCard.jsx`, `ReferencePage.jsx`)
- `important` added to the read_status cycle after `read` (unread → reading → read → important → unread)
- Distinct bookmark icon and alexandria-brand colour
- Status cycle accessible from both the card and the reference detail page

### Round 6 — Evidence trails (`services/librarian.py`, `LibrarianPanel.jsx`)
- `DEFAULT_SYSTEM_PROMPT` updated: Alexandria instructed to append a `### Sources` section with `[ID] Title` lines after library-grounded answers
- Frontend `parseSourcesFromResponse()` strips the Sources block from the display text and shows it as a "Library sources" panel with clickable reference links
- `project_id` threaded through the full chat call chain so library search is now project-scoped
- `_search_library` upgraded to use FTS with `ts_rank_cd` ranking

### Round 7 — Claim/finding extraction (`services/ingestion.py`, `ReferencePage.jsx`)
- `generate_metadata` prompt now extracts `main_finding`, `method`, `limitations` alongside existing fields
- These are moved into `extra_metadata.findings` to keep the Reference schema stable
- Reference detail page shows a **Key Findings** card when findings are present
- Findings key hidden from the raw Metadata section to avoid duplication

### Round 8 — Monitor quality metrics (`models/search_monitor.py`, `routers/review.py`, `Monitors.jsx`)
- `approve_count` and `reject_count` integer columns added to `search_monitors` (migration)
- `decide()` endpoint increments the appropriate counter when a queue item has a `monitor_id`
- MonitorCard shows approval/rejection counts and a precision percentage (approvals ÷ total decisions)

---

## Cycle 9 — 2026-05-08 — Admin Config Panel

**Goal:** Give operators visibility into system health and confidence in API key configuration without needing terminal access.

### API key health checks (`routers/config.py`, `ConfigPage.jsx`)
- New `POST /config/test-key` endpoint accepts `provider` + optional `key`
- Makes a real 1-token call to the provider (Haiku for Anthropic, GPT-4o-mini for OpenAI, Gemini Flash for Google)
- Returns `{ok, model, latency_ms}` on success; categorised error message on failure (auth error, rate limit, quota exhausted, model not found)
- Falls back to the `.env` key if the input field is empty
- "Test" button renders inline with each API key field; shows ✓ model·ms or ✗ reason without refreshing the page

### System Status panel (`routers/config.py`, `ConfigPage.jsx`)
- New `GET /config/system` endpoint (requires DB dependency): database connection + reference count + pending queue depth, upload storage stats (file count, total MB, directory path), scheduler state (running/paused, next run times for monitor and digest jobs)
- `SystemStatusPanel` React component with three status rows, placed at the top of the Config page
- Refresh button; auto-refreshes on scheduler toggle

### Scheduler pause/resume (`routers/config.py`, `ConfigPage.jsx`)
- New `POST /config/scheduler/{pause|resume}` endpoint calls APScheduler's `.pause()` / `.resume()` in-process
- Pause/Resume button on the Scheduler row; useful when bulk-importing references to suppress monitor competition

---

## Cycle 12 — 2026-05-16 — Monitor Learning (and an Ollama binding note)

### Ollama systemd binding fix (host config, not code)

Operational issue surfaced during testing: the Config page reported "Ollama: not connected" even though the host service was running. Diagnosis: Ollama 0.21.2 defaults to listening on `127.0.0.1:11434`, which the backend container cannot reach.

Remedy (host-side, one-time):

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
echo -e '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"' \
  | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

After this, the backend reaches Ollama via `host.docker.internal:11434` (the existing `extra_hosts: host-gateway` mapping in docker-compose.yml). Non-Docker tools that hit `localhost:11434` still work because binding to `0.0.0.0` includes loopback.

Captured here (not just as a future "I'll remember it" — Mike's already hit this twice across cycles) so future sessions can paste the override and move on.

### Monitor learning

**Goal:** Close the feedback loop so monitors get less noisy over time. Before this, the only thing approve / reject counts did was display a precision percentage — useful for spotting bad monitors but the user still had to fix them by hand.

#### Schema (`models/search_monitor.py`, `database.py`)
- New `negative_keywords TEXT` column on `search_monitors` (nullable, comma-separated).

#### Filtering (`services/proactive_search.py`)
- `run_monitor` adds a "step 3.5" between the Alexandria relevance filter and the dedup loop. If the monitor has negative keywords, any result whose title or abstract contains one of them (case-insensitive substring) is dropped before being added to the review queue. Drops are logged.

#### Suggestion service (`services/proactive_search.py`)
- New `suggest_monitor_improvements(db, monitor)` function:
  - Fetches the last 10 approved + last 10 rejected `ReviewQueueItem`s for the monitor.
  - Returns early with a hint if there are <3 decisions total.
  - Otherwise prompts Alexandria with the monitor name + query + sample lists and asks for `{refined_query, negative_keywords[], reasoning}` as JSON.
  - The model is instructed to keep the refined query close to the original, prefer specific terms over generic ones, and admit when there isn't enough signal.
- New `POST /review/monitors/{id}/suggest-improvements` endpoint wires it up.

#### UI (`pages/Monitors.jsx`, `api/client.js`)
- The "Improve" affordance only shows when precision < 50% with ≥5 decisions — avoids cluttering monitors that are already working well.
- Click → inline panel with reasoning, suggested refined query, and suggested negative keywords as red pills.
- Three apply choices: query only, keywords only, or both. Keywords are *merged* with any existing negatives so applying twice doesn't lose previous tuning.
- Existing negative_keywords are shown on the card ("Excluding: ...") so the state is visible without opening the panel.

#### Why advisory rather than automatic

The system never silently adjusts a monitor — the user reviews the suggestion before it takes effect. Reason: query and exclusion rules carry research-judgment risk (a negative keyword that looks reasonable might exclude an important paper). Cheap to review, expensive to discover after the fact that good results were silently filtered out.

---

## Cycle 11 — 2026-05-16 — Quote Search, Pagination, Compare View

**Goal:** Make the library answer three more researcher questions reliably:
1. "Where in any of these papers did I read the 65% figure?"  → quote search over full text.
2. "What does this library actually contain?"  → server-side pagination so the answer isn't "the most recent 200".
3. "How do these three papers differ on method / findings / limitations?"  → side-by-side comparison.

### Quote search via weighted FTS (`models/reference.py`, `database.py`, `services/search.py`)
- New generated `tsv tsvector` column on `references`, computed from `setweight(...title 'A') || ...abstract 'B' || ...summary 'C' || ...full_text 'D'`. PostgreSQL auto-maintains it on insert/update.
- GIN index `ix_references_tsv` on the column; old `ix_references_fts` dropped.
- `services/search.py` queries the column directly (no `concat` expression any more) and uses `ts_rank_cd(Reference.tsv, tsq)` for ranking.
- `ts_headline` now scans `full_text` when present so search snippets surface the matching passage from the body, not just the abstract. Falls back to abstract+summary for refs with no extracted text.
- Title matches still outrank body matches because of the `setweight` levels — quote search doesn't crowd out short relevant titles.

### Server-side pagination (`routers/references.py`, `main.py`, `pages/Library.jsx`)
- `GET /references` now runs a `COUNT(*)` with the same filters and returns the total in an `X-Total-Count` response header.
- CORS middleware exposes `X-Total-Count` so the frontend can read it.
- `limit` cap raised from 200 to 500; default still 50.
- `Library.jsx` paginates both list and search modes at 50 per page with prev/next controls. Page resets to 0 when filters or query change. `keepPreviousData: true` so navigation feels instant.

### Side-by-side comparison (`routers/references.py`, `pages/ComparePage.jsx`, `pages/Library.jsx`, `components/ReferenceCard.jsx`)
- New `GET /references/batch?ids=1,2,3` returns up to 8 refs in one round-trip with tags eager-loaded.
- New `/compare` route renders a wide table: authors, year, source type, **main finding / method / limitations** (from `extra_metadata.findings`), tags, summary, DOI, arXiv ID.
- Each column header is the ref title (links to detail page) with an `X` to drop it from the comparison.
- `Library.jsx` has a Compare toggle that turns reference cards into selectable checkboxes; floating action bar shows selection count and "Compare N". Max 8 refs to keep the table readable.
- `ReferenceCard.jsx` gains `selectable / selected / onToggleSelect` props — click-through routes to either ref-detail or selection-toggle depending on mode.

---

## Cycle 10 — 2026-05-16 — DOI / arXiv ID Deduplication

**Goal:** Stop the same paper from arriving multiple times through different monitor sources (arXiv + Semantic Scholar + OpenAlex). The previous URL+title checks were too brittle — OpenAlex returns DOI URLs, arXiv returns abstract page URLs, and Semantic Scholar sometimes returns the PDF URL, so URL-equality misses them and small title variations slip past the title check.

### Schema (`models/reference.py`, `models/review_queue.py`, `database.py`)
- New nullable columns `doi VARCHAR(200)` and `arxiv_id VARCHAR(50)` on both `references` and `review_queue`
- Composite indexes `(project_id, doi)` and `(project_id, arxiv_id)` on `references` for fast project-scoped lookup
- Migrations are guarded with `IF NOT EXISTS` and run on backend startup

### ID extraction at ingestion (`services/ingestion.py`)
- New helpers `normalise_doi`, `normalise_arxiv_id`, `extract_ids_from_url`
- DOI normalised to lowercase `10.x/yyy` form (strips `https://doi.org/`, `doi:`, etc.); rejects non-DOI strings
- arXiv ID normalised to `YYMM.NNNNN` or `YYMM.NNNNNvN` form
- `generate_metadata` lifts `doi` / `arxiv_id` from LLM-generated `extra_metadata` into top-level meta fields
- `ingest_url` applies URL-derived IDs as a fallback when LLM extraction missed them

### ID surfacing in source adapters (`services/proactive_search.py`)
- arXiv: parses ID from the entry's `<id>` URL via `extract_ids_from_url`
- Semantic Scholar: reads `externalIds.DOI` and `externalIds.ArXiv`, normalises both
- OpenAlex: normalises the `doi` field (was previously kept only inside `extra_metadata`)

### Dedup wiring (`routers/references.py`, `routers/review.py`, `services/proactive_search.py`)
- `_find_duplicate(...)` now takes `doi` and `arxiv_id` and checks them before URL / title
- Upload, from-URL, bulk PDF, bulk URL, and review-queue approval all read `doi` / `arxiv_id` from the ingestion meta and persist them
- `_is_duplicate` in `proactive_search` checks `Reference.doi` / `arxiv_id` and `ReviewQueueItem.doi` / `arxiv_id` so the same paper from multiple monitor sources is rejected at queue intake
- BibTeX export now uses the column directly (with `eprint` + `archivePrefix` for arXiv entries) and falls back to `extra_metadata` for legacy rows

### Schemas (`schemas/reference.py`, `schemas/review_queue.py`)
- `ReferenceOut` and `ReviewQueueItemOut` expose `doi` and `arxiv_id` so the frontend can render them on detail pages later

---

## Planned: Future Cycles

See `docs/feature-requests.md` for the authoritative roadmap with phase completion status. The most pressing remaining items, in priority order:

1. Enforce project access on direct reference endpoints (`GET/PATCH/DELETE /references/{id}`, file serving, BibTeX export) — open security gap flagged by Codex review
2. DOI / arXiv ID as indexed columns for stronger deduplication
3. Server-side pagination on the Library list view (currently capped at 200)
4. Monitor learning from review history (query refinement suggestions, negative keywords)
5. Project membership / roles — prerequisite for Phase 4 collaboration features
6. pgvector hybrid semantic + lexical search
7. Cloud deployment config (production docker-compose, nginx, S3 uploads)
8. Email delivery for monthly digests (SMTP config)
9. Rate limiting middleware + audit log
10. Better Ollama model detection (ping `/api/tags` to list installed models)
