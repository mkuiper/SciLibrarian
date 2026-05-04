from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import auth, collections, references, search, librarian, review, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="SciLibrarian API",
    description="AI-powered knowledge management for the Australian AI Safety Institute",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(collections.router)
app.include_router(references.router)
app.include_router(search.router)
app.include_router(librarian.router)
app.include_router(review.router)
app.include_router(projects.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
