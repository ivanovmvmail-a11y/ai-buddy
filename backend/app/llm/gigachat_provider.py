import json
import uuid
from pathlib import Path

from gigachat import GigaChat

from app.config import settings

from .base import LLMReply, Message, ToolCall, ToolSpec

# Публичный корневой сертификат Минцифры (https://www.gosuslugi.ru/crt), лежит в репозитории.
DEFAULT_CA_FILE = Path(__file__).resolve().parents[2] / "certs" / "russian_trusted_root_ca.cer"


def to_gigachat_messages(messages: list[Message]) -> list[dict]:
    """GigaChat: вызов инструмента — assistant с function_call, результат — role=function."""
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "function", "name": m.name, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            # GigaChat вызывает не больше одной функции за ответ
            call = m.tool_calls[0]
            out.append(
                {
                    "role": "assistant",
                    "content": m.content,
                    "function_call": {"name": call.name, "arguments": call.arguments},
                    "functions_state_id": call.id,
                }
            )
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def to_gigachat_functions(tools: list[ToolSpec]) -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]


def make_client() -> GigaChat:
    """Клиент GigaChat из настроек: для чата и эмбеддингов (одни ключ и сертификат)."""
    if not settings.gigachat_credentials:
        raise RuntimeError("GIGACHAT_CREDENTIALS не задан в backend/.env")
    kwargs: dict = {
        "credentials": settings.gigachat_credentials,
        "scope": settings.gigachat_scope,
        "model": settings.gigachat_model,
        "timeout": 60,
    }
    ca_file = settings.gigachat_ca_bundle_file or (str(DEFAULT_CA_FILE) if DEFAULT_CA_FILE.exists() else "")
    if ca_file:
        # с сертификатом проверка SSL всегда включена, GIGACHAT_VERIFY_SSL игнорируется
        kwargs["ca_bundle_file"] = ca_file
    else:
        kwargs["verify_ssl_certs"] = settings.gigachat_verify_ssl
    return GigaChat(**kwargs)


class GigaChatProvider:
    name = "gigachat"

    def __init__(self) -> None:
        self._client = make_client()

    async def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMReply:
        payload: dict = {"messages": to_gigachat_messages(messages), "temperature": settings.llm_temperature}
        if tools:
            payload["functions"] = to_gigachat_functions(tools)
            payload["function_call"] = "auto"
        response = await self._client.achat(payload)
        msg = response.choices[0].message
        calls: list[ToolCall] = []
        if msg.function_call:
            args = msg.function_call.arguments
            if isinstance(args, str):  # на всякий случай: некоторые версии API отдают строку
                args = json.loads(args or "{}")
            calls.append(
                ToolCall(
                    id=msg.functions_state_id or f"call_{uuid.uuid4().hex[:12]}",
                    name=msg.function_call.name,
                    arguments=args or {},
                )
            )
        return LLMReply(content=msg.content or "", tool_calls=calls)
