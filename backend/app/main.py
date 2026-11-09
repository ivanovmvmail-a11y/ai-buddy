"""HTTP API AI-buddy (Flask). Контракт — docs/API.md."""
from flask import Flask, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, ValidationError

from app import async_runner
from app.agent.service import answer
from app.config import settings
from app.llm import Message


class ChatRequest(BaseModel):
    messages: list[Message]


class Source(BaseModel):
    title: str
    url: str | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = []


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False  # кириллица в ответах как есть, без \uXXXX

    origins = [o.strip() for o in settings.frontend_origins.split(",") if o.strip()]
    CORS(app, origins=origins)

    @app.get("/health")
    def health():
        return {"status": "ok", "llm_provider": settings.llm_provider}

    @app.post("/chat")
    def chat():
        try:
            req = ChatRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as exc:
            return jsonify(detail=exc.errors(include_url=False, include_context=False)), 422

        history = [m for m in req.messages if m.role in ("user", "assistant")]
        try:
            reply, sources = async_runner.run(answer(history))
        except Exception as exc:  # для прототипа отдаём фронту понятную ошибку
            return jsonify(detail=f"Ошибка LLM: {exc}"), 502
        return ChatResponse(reply=reply, sources=[Source(**s) for s in sources]).model_dump()

    return app


app = create_app()
