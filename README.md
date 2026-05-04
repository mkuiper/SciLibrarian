# SciLibrarian — powered by Alexandria

An AI-powered knowledge management platform for research teams. Alexandria (your librarian agent) helps you ingest, organise, search, and stay on top of the literature — with proactive monitoring, monthly digests, and a natural-language chat interface.

Built as a reference implementation for the **Australian AI Safety Institute**.

---

## Features

| Feature | Description |
|---|---|
| **Alexandria Chat** | Ask your librarian anything — she searches the library, synthesises answers, and cites sources |
| **PDF & URL ingestion** | Drop a PDF or paste a URL; Alexandria extracts text, generates a summary, metadata, and tags |
| **Hierarchical collections** | Organise references in a folder tree; Alexandria designs the initial structure from your project description |
| **Full-text search** | Search across titles, abstracts, summaries, and full text |
| **Proactive monitors** | Configure search queries; Alexandria searches arXiv and Semantic Scholar and queues discoveries for review |
| **Human review queue** | Approve or reject discoveries before they enter the library |
| **Monthly digest** | Alexandria writes a state-of-the-art synthesis across all library topics |
| **Multi-project** | Multiple projects, each with their own library and collections |
| **CLI** | Batch ingestion, search, and digest generation from the terminal |

---

## Quick start

### Prerequisites
- Docker & Docker Compose
- An Anthropic API key

### Setup

```bash
git clone git@github.com:mkuiper/SciLibrarian.git
cd SciLibrarian
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
docker compose up
```

- **Web UI**: http://localhost:5173
- **API docs**: http://localhost:8000/docs

Register an account, create your first project, and Alexandria will design your library structure.

### CLI

```bash
cd backend
pip install -r requirements.txt

# Authenticate
python -m cli.main login

# Ingest a PDF
python -m cli.main ingest paper.pdf --project 1

# Batch ingest a directory
python -m cli.main ingest-dir ./papers/ --project 1

# Search
python -m cli.main search "AI alignment" --project 1

# Generate a monthly digest
python -m cli.main digest --project 1
```

---

## Architecture

```
frontend/          React 18 + Vite + Tailwind CSS
backend/
  app/
    models/        SQLAlchemy ORM models
    routers/       FastAPI route handlers
    services/      Business logic (ingestion, librarian, search, digest)
    schemas/       Pydantic request/response schemas
  cli/             Typer-based CLI
```

**Persistence**: PostgreSQL  
**AI**: Anthropic Claude (configurable model — Sonnet, Opus, or Haiku)  
**Document processing**: PyMuPDF for PDFs, httpx + BeautifulSoup for URLs  
**Search**: PostgreSQL full-text search (vector search planned for Cycle 3)  
**Background monitors**: APScheduler (in-process)

---

## Development cycles

See [docs/design-decisions.md](docs/design-decisions.md) for the reasoning behind architectural choices.

| Cycle | Status | Focus |
|---|---|---|
| 1 | ✅ Complete | Auth, collections, ingestion, search, librarian chat, projects, digests |
| 2 | Planned | Watch requests UI, restructure suggestions, scheduled digest |
| 3 | Planned | Vector/semantic search, cloud deployment, pgvector |

---

## Environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SECRET_KEY` | JWT signing secret (change in production) |
| `DATABASE_URL` | PostgreSQL connection string |
| `MAX_UPLOAD_MB` | Maximum PDF upload size (default 50) |
