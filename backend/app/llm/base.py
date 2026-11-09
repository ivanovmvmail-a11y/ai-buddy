"""Общие типы LLM-слоя. Провайдеры (gigachat, openai, echo) переводят их в формат своего API."""
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Просьба модели вызвать инструмент."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    # assistant: какие инструменты модель попросила вызвать
    tool_calls: list[ToolCall] | None = None
    # tool: результат какого вызова и какого инструмента
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    """Описание инструмента для модели: имя, назначение, JSON Schema аргументов."""

    name: str
    description: str
    parameters: dict[str, Any]


class LLMReply(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    async def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMReply: ...
