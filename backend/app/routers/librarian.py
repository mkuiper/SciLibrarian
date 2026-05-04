from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies import DB, CurrentUser
from app.services.librarian import chat_with_librarian

router = APIRouter(prefix="/librarian", tags=["librarian"])


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "claude-sonnet-4-6"


@router.post("/chat")
async def chat(request: ChatRequest, db: DB, current_user: CurrentUser):
    async def generate():
        async for chunk in chat_with_librarian(db, request.messages, request.model):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")
