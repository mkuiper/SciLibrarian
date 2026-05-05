from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
from app.models.project import Project
from app.services.librarian import chat
from app.services.llm import get_ollama_models, PROVIDER_MODELS

router = APIRouter(prefix="/librarian", tags=["librarian"])


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "claude-sonnet-4-6"
    project_id: int | None = None


@router.post("/chat")
async def chat_endpoint(request: ChatRequest, db: DB, current_user: CurrentUser):
    system_prompt = None
    project_settings = None

    if request.project_id:
        result = await db.execute(select(Project).where(Project.id == request.project_id))
        project = result.scalar_one_or_none()
        if project and project.settings:
            system_prompt = project.settings.get("librarian_system_prompt")
            project_settings = project.settings

    async def generate():
        async for chunk in chat(db, request.messages, request.model, system_prompt, project_settings):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


@router.get("/models")
async def list_models(current_user: CurrentUser):
    """Return all available models grouped by provider, with live Ollama detection."""
    result = {k: list(v) for k, v in PROVIDER_MODELS.items()}

    ollama = await get_ollama_models()
    if ollama:
        result["ollama"] = [{"value": m["value"], "label": m["label"]} for m in ollama]
    else:
        result["ollama"] = [
            {"value": "ollama/llama3.1:8b",  "label": "llama3.1:8b (Ollama not connected)"},
            {"value": "ollama/gemma4:latest", "label": "gemma4:latest (Ollama not connected)"},
        ]

    return result
