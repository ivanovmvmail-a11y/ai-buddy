from typing import Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(Protocol):
    name: str

    async def chat(self, messages: list[Message]) -> str: ...
