"""LLM-слой (зона Claude). Провайдер выбирается переменной LLM_PROVIDER: gigachat | openai | echo."""
from functools import lru_cache

from app.config import settings

from .base import LLMProvider, LLMReply, Message, ToolCall, ToolSpec

__all__ = ["LLMProvider", "LLMReply", "Message", "ToolCall", "ToolSpec", "get_llm"]


@lru_cache
def get_llm() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "gigachat":
        from .gigachat_provider import GigaChatProvider

        return GigaChatProvider()
    if provider == "openai":
        from .openai_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider()
    from .echo_provider import EchoProvider

    return EchoProvider()
