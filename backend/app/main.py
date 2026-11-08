from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent.service import answer
from app.config import settings
from app.llm import Message

app = FastAPI(title="AI-buddy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    messages: list[Message]


class Source(BaseModel):
    title: str
    url: str | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = []


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": settings.llm_provider}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    history = [m for m in req.messages if m.role in ("user", "assistant")]
    try:
        reply, sources = await answer(history)
    except Exception as exc:  # для прототипа отдаём фронту понятную ошибку
        raise HTTPException(status_code=502, detail=f"Ошибка LLM: {exc}") from exc
    return ChatResponse(reply=reply, sources=[Source(**s) for s in sources])
