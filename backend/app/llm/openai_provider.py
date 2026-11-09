import json

from openai import AsyncOpenAI

from app.config import settings

from .base import LLMReply, Message, ToolCall, ToolSpec


def to_openai_messages(messages: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)},
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def to_openai_tools(tools: list[ToolSpec]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in tools
    ]


def parse_arguments(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


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

    async def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMReply:
        kwargs: dict = {"model": settings.openai_model, "messages": to_openai_messages(messages)}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        calls = [
            ToolCall(id=c.id, name=c.function.name, arguments=parse_arguments(c.function.arguments))
            for c in (msg.tool_calls or [])
        ]
        return LLMReply(content=msg.content or "", tool_calls=calls)
