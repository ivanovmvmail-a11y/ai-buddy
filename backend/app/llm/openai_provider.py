from openai import AsyncOpenAI

from app.config import settings

from .base import Message


class OpenAICompatibleProvider:
    """Любой OpenAI-совместимый API: задайте OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL."""

    name = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY не задан в backend/.env")
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
        )

    async def chat(self, messages: list[Message]) -> str:
        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[m.model_dump() for m in messages],
        )
        return response.choices[0].message.content or ""
