"""LLM-слой (зона Claude). Провайдер выбирается переменной LLM_PROVIDER: gigachat | openai | scenario | echo.

scenario — сценарный режим без ключа (спека 003); echo — заглушка для разработки (повторяет сообщение)."""
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
    if provider == "scenario":
        from .scenario_provider import ScenarioProvider

        return ScenarioProvider()
    from .echo_provider import EchoProvider

    return EchoProvider()
