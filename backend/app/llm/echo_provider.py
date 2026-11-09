from .base import LLMReply, Message, ToolSpec


class EchoProvider:
    """Заглушка: работает без ключей (демо-режим и разработка). Инструменты не вызывает."""

    name = "echo"

    async def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMReply:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMReply(
            content=f"[echo] Вы написали: {last}\n\n(Чтобы подключить нейросеть: LLM_PROVIDER=gigachat в backend/.env)"
        )
