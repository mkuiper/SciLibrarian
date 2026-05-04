# SciLibrarian — Claude Code Context

## What this is
A knowledge management platform for the Australian AI Safety Institute. An AI librarian agent (Claude-powered) helps users ingest, organise, search, and retrieve reference materials (papers, policies, model cards, evaluations).

## Architecture
- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL (port 8000)
- **Frontend**: React 18 + Vite + Tailwind CSS (port 5173)
- **AI**: Anthropic Claude API (configurable model, default claude-sonnet-4-6)
- **Infra**: Docker Compose for local dev

## Running locally
```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
docker compose up
```
Backend API docs: http://localhost:8000/docs  
Frontend: http://localhost:5173

## Key directories
- `backend/app/models/` — SQLAlchemy models
- `backend/app/routers/` — FastAPI route handlers
- `backend/app/services/` — Business logic (ingestion, librarian, search)
- `frontend/src/pages/` — Top-level pages
- `frontend/src/components/` — Shared UI components

## Development cycles
- **Cycle 1** (current): Auth, collections, reference ingestion (PDF+URL), FTS search, librarian chat
- **Cycle 2**: Review queue UI, proactive search monitors with scheduler
- **Cycle 3**: Cloud deployment config, vector search upgrade

## DB migrations
```bash
# Inside backend container or venv
alembic upgrade head        # apply migrations
alembic revision --autogenerate -m "description"  # create new migration
```

## Code conventions
- Python: async/await throughout, Pydantic v2 models, no comments unless non-obvious
- TypeScript/JSX: functional components, TanStack Query for server state
- Never commit .env or uploads/
