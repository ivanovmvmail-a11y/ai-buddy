from .base import Message


class EchoProvider:
    """Заглушка: работает без ключей, чтобы фронт можно было разрабатывать сразу."""

    name = "echo"

    async def chat(self, messages: list[Message]) -> str:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"[echo] Вы написали: {last}\n\n(Чтобы подключить нейросеть: LLM_PROVIDER=gigachat в backend/.env)"
