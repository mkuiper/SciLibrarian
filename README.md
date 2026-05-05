# SciLibrarian — powered by Alexandria

An AI-powered knowledge management platform for research teams. **Alexandria** is your intelligent research librarian — she ingests references, answers questions, monitors for new material, writes monthly digests, and can even process submissions sent by email.

Built as a reference implementation for the **Australian AI Safety Institute**, but designed for any research domain.

---

## Features

| Feature | Description |
|---|---|
| **Alexandria chat** | Ask anything — she searches the library, uses web search, looks up papers on arXiv, and synthesises answers with citations |
| **Multi-provider AI** | Claude, GPT-4o, Gemini, Ollama (local), vLLM — all configurable per task |
| **PDF & URL ingestion** | Drop a PDF or paste a URL; Alexandria extracts text, generates a summary, metadata, and tags |
| **Email ingestion** | Email a PDF or URL to a dedicated inbox — Alexandria processes and files it automatically |
| **Hierarchical collections** | Folder tree for organising references; Alexandria designs the initial structure from your project description |
| **Full-text search** | Search across titles, abstracts, summaries, and full extracted text |
| **Proactive monitors** | Alexandria searches arXiv, Semantic Scholar, OpenAlex, and the web on a schedule; discoveries go to a review queue |
| **Human review queue** | Approve or reject monitored discoveries before they enter the library |
| **Monthly digest** | State-of-the-art synthesis across all library topics, or focused on a single collection |
| **Watch requests** | Describe what you're looking for in plain English; Alexandria prioritises it in searches |
| **Restructure suggestions** | Alexandria analyses collection usage and recommends reorganisation |
| **Multi-project** | Multiple projects, each with their own library, collections, and settings |
| **CLI** | Batch ingestion, search, and digest generation from the terminal |

---

## Quick start

### Prerequisites
- Docker + Docker Compose
- At least one AI provider API key (see below)

### 1. Clone and configure

```bash
git clone git@github.com:mkuiper/SciLibrarian.git
cd SciLibrarian
cp .env.example .env
```

Edit `.env`. The minimum required setting:

```bash
ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY or GEMINI_API_KEY
SECRET_KEY=any-random-string-here
```

### 2. Start (without local AI models)

```bash
docker-compose up --build
```

- **Frontend:** http://localhost:5173
- **API docs:** http://localhost:8000/docs

### 3. Start with Ollama (local models — no API costs)

```bash
docker-compose --profile ollama up --build

# In a second terminal, pull models:
docker-compose exec ollama ollama pull llama3.2
docker-compose exec ollama ollama pull mistral
docker-compose exec ollama ollama pull qwen2.5:7b
```

Then in the app go to **Configuration** → assign an Ollama model to each agent.

### 4. First run

1. Register an account (username + password, no email required)
2. Create a project — describe your research domain and goals
3. Alexandria designs your initial collection structure
4. Add references via PDF upload, URL, or email
5. Ask Alexandria questions in the chat panel

---

## AI Provider Setup

### About API keys vs "Pro" subscriptions

> **Important:** Claude.ai Pro, ChatGPT Plus, and Gemini Advanced are *consumer subscriptions* — they do not include API access. The developer APIs (Anthropic API, OpenAI API, Google AI Studio) are separate products with separate billing. You cannot use a Claude.ai Pro subscription to make API calls.

To use a provider, you need a **developer API key**:

| Provider | Get key at | Set in .env |
|---|---|---|
| Anthropic (Claude) | console.anthropic.com | `ANTHROPIC_API_KEY` |
| OpenAI (GPT-4o) | platform.openai.com | `OPENAI_API_KEY` |
| Google (Gemini) | aistudio.google.com | `GEMINI_API_KEY` |
| Ollama (local) | ollama.com (free) | runs inside Docker |

Per-project API key overrides are also supported in **Configuration** — useful if different team members have their own developer accounts.

### Supported models

| Provider | Models |
|---|---|
| Anthropic | claude-sonnet-4-6, claude-opus-4-7, claude-haiku-4-5 |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| Google | gemini/gemini-1.5-pro, gemini/gemini-1.5-flash, gemini/gemini-2.0-flash |
| Ollama | llama3.2, mistral, qwen2.5:7b, deepseek-r1:7b, mistral-nemo, and any model you pull |
| vLLM | Any model via OpenAI-compatible endpoint (set `VLLM_BASE_URL`) |

---

## Email Ingestion

Team members can submit references by emailing a dedicated inbox. Alexandria checks it periodically and files everything automatically.

**Setup:**
1. Create a dedicated inbox (Gmail alias, Outlook, Fastmail, etc.)
2. In `.env`, set:
   ```
   INGEST_EMAIL_ENABLED=true
   INGEST_IMAP_HOST=imap.gmail.com
   INGEST_IMAP_USERNAME=ingest@yourdomain.com
   INGEST_IMAP_PASSWORD=your-app-password
   ```
3. Restart. Alexandria checks every 10 minutes.

**What she processes:**
- PDF attachments → full ingestion pipeline (text extraction, metadata, summary, tags)
- URLs in subject or body → URL ingestion
- Subject line used to guess which collection to file into
- Sender receives a confirmation reply with what was filed

**Gmail tip:** Use an App Password (not your regular password). Enable 2FA → generate one at myaccount.google.com/apppasswords.

---

## Search Sources

All proactive search sources are free — API keys only improve rate limits.

| Source | Coverage | Key needed? |
|---|---|---|
| arXiv | CS/ML/Physics preprints | No |
| Semantic Scholar | 200M+ academic papers | No (1 req/s) · Yes for 100 req/s |
| OpenAlex | 250M+ scholarly works | No (10 req/s) · Email for polite pool |
| DuckDuckGo | General web, govt docs, news | No |

Set `OPENALEX_EMAIL` and `SEMANTIC_SCHOLAR_API_KEY` in `.env` for higher rate limits.

---

## Architecture

```
frontend/          React 18 + Vite + Tailwind CSS (port 5173)
backend/
  app/
    models/        SQLAlchemy ORM (User, Project, Collection, Reference, ...)
    routers/       FastAPI routes (auth, references, collections, librarian, ...)
    services/      Business logic:
      llm.py         Unified LiteLLM interface for all AI providers
      librarian.py   Alexandria agent (tool use: search, web, arXiv, full text)
      ingestion.py   PDF + URL ingestion pipeline
      digest.py      Monthly digest generation (project or collection scope)
      proactive_search.py  arXiv / Semantic Scholar / OpenAlex / DuckDuckGo
      email_ingest.py      IMAP inbox polling for email submissions
      scheduler.py   APScheduler: monitors (6h), digests (monthly), email (10m)
      embeddings.py  pgvector semantic search (infrastructure ready)
  cli/             Typer CLI for batch operations
nginx/             Production reverse proxy config
```

**Database:** PostgreSQL  
**Search:** PostgreSQL full-text search (vector search infrastructure in place, migration pending)  
**Background jobs:** APScheduler (in-process, no Redis needed)

---

## CLI

```bash
cd backend
source .venv/bin/activate  # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

python -m cli.main login
python -m cli.main ingest paper.pdf --project 1
python -m cli.main ingest-dir ./papers/ --project 1 --collection 3
python -m cli.main search "AI alignment" --project 1
python -m cli.main digest --project 1
```

---

## Development

```bash
# Run just the database (develop backend locally)
docker-compose up db -d

# Backend
cd backend && source .venv/bin/activate
DATABASE_URL="postgresql+asyncpg://scilibrarian:changeme@localhost:5432/scilibrarian" \
ANTHROPIC_API_KEY="sk-ant-..." uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

API docs: http://localhost:8000/docs

---

## Development cycles

See [docs/development-log.md](docs/development-log.md) for detailed per-cycle notes and [docs/design-decisions.md](docs/design-decisions.md) for architectural rationale.

| Cycle | Focus |
|---|---|
| 1 | Scaffold, auth, collections, ingestion, search, librarian chat, monitors, digest, CLI |
| 2 | LiteLLM multi-provider, Settings page, PDF viewer, OpenAlex, Watch Requests, real stats |
| 3 | Bulk review, inline editing, restructure UI, Ollama auto-detection |
| 4 | APScheduler (monitors 6h, digest monthly), production Docker, project switching |
| 5 | pgvector foundation, review deduplication, inline tag editing |
| 6 | PDF auth fix, Config page, collection digests, DuckDuckGo web search, multi-domain |
| 7 | Ollama-in-Docker, Alexandria tools (web/arXiv/full-text), email ingestion, broad domains |

**Planned — Cycle 8:**
- MCP server endpoint (Claude Desktop can connect to the library)
- pgvector migration (activate semantic/embedding search)
- Social login (Google/GitHub OAuth)
- Rate limiting middleware
- Audit log
