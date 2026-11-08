"""Собирает промпт, подтягивает контекст из RAG, вызывает LLM."""
from app.llm import Message, get_llm
from app.rag import retrieve

from .prompts import SYSTEM_PROMPT


async def answer(history: list[Message]) -> tuple[str, list[dict]]:
    question = next((m.content for m in reversed(history) if m.role == "user"), "")
    docs = await retrieve(question)

    system = SYSTEM_PROMPT
    if docs:
        context = "\n\n".join(f"### {d['title']}\n{d['content']}" for d in docs)
        system += f"\n\nКонтекст из документов команды:\n{context}"

    messages = [Message(role="system", content=system), *history]
    reply = await get_llm().chat(messages)
    sources = [{"title": d["title"], "url": d.get("url")} for d in docs]
    return reply, sources
