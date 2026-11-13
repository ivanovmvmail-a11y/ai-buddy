"""Как агент чата обращается к корпоративным сервисам: напрямую или по протоколу MCP.

Проверка 12–13.11: «веб-агент вызывает сервисы в одном процессе, а не по MCP» — главный недочёт по критерию
«Внедряемость и интеграции». Теперь у агента один шлюз к сервисам с двумя транспортами:

- `AGENT_SERVICES=direct` — вызов функций `app.mcp_server` в том же процессе (тесты, запуск без MCP SDK);
- `AGENT_SERVICES=mcp` — MCP-клиент (официальный SDK): на каждый вызов — сессия к MCP-серверу
  `app.mcp_server.server` от имени вошедшего пользователя, `initialize` → `tools/call` → разбор `structuredContent`.
  Права проверяет сам MCP-сервер, ошибки приходят ошибками протокола и превращаются в те же доменные ошибки.

Транспорт сессии: при `MCP_URL` — по сети, Streamable HTTP к отдельному MCP-серверу (в Docker — служба `mcp`,
`app/mcp_server/http_server.py`; ключ службы + пользователь заголовком от backend). Без `MCP_URL` — в памяти процесса
(`create_connected_server_and_client_session`, тесты и облачная версия). При внедрении меняется только `MCP_URL`
(MCP Hub Авито) и источник пользователя (SSO).

Через MCP не идут два действия, и это намеренно: подтверждение отгула и напоминание по просьбе. Их выполняет
доверенный обратный вызов после кнопки «Подтвердить» человека (`onboarding_tools.py`), а в MCP-сервере инструмента
«подтвердить» нет — модель не может подтвердить действие сама (спека 001).
"""
import logging
from contextlib import asynccontextmanager
from typing import Any

from pydantic import TypeAdapter

from app.config import settings
from app.mcp_server import absence, access, checklist, hiring
from app.mcp_server.absence_models import AbsenceRequest
from app.mcp_server.errors import Conflict, Forbidden, NotFound
from app.mcp_server.models import AccessRequest, AccessResource, Plan, PlanItem, SkillProfile

from .users import User

log = logging.getLogger("ai_buddy.services")

# Тексты отказов сервисов (app/mcp_server, `raise Forbidden(...)`): по протоколу отказ и конфликт приходят одинаково —
# ошибкой инструмента с текстом. Отказ модели показываем как «нет доступа», конфликт — его текстом.
FORBIDDEN_TEXTS = {"Действие запрещено", "Операция доступна только системе", "Общий пункт нельзя убрать",
                   "Пункт с сервисом или этап-контур нельзя менять вручную"}
UNAVAILABLE = "Сервис временно недоступен"


class InvalidArguments(Exception):
    """MCP-сервер отклонил аргументы (схема инструмента) — как ValidationError при прямом вызове."""


def mode() -> str:
    return "mcp" if settings.agent_services.strip().lower() == "mcp" else "direct"


@asynccontextmanager
async def _session(user: User):
    if settings.mcp_url.strip():
        # По сети: Streamable HTTP к отдельному MCP-серверу (в Docker — сервис `mcp`). Сервер доверяет только
        # backend с MCP_SERVICE_TOKEN; пользователя передаём заголовком из сессии входа, модель его не задаёт.
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        headers = {"Authorization": f"Bearer {settings.mcp_service_token}", "X-AI-Buddy-User": user.id}
        async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(15, read=60)) as http:
            async with streamable_http_client(settings.mcp_url.strip(), http_client=http) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    yield client
        return
    from mcp.shared.memory import create_connected_server_and_client_session as connected

    from app.mcp_server.server import create_server
    async with connected(create_server(user.id)) as client:
        yield client


def transport() -> str:
    """Для /health и логов: как агент сейчас ходит к сервисам."""
    if mode() != "mcp":
        return "direct"
    return "mcp-http" if settings.mcp_url.strip() else "mcp-memory"


def _error(text: str) -> Exception:
    message = text.split(": ", 1)[1] if text.startswith("Error executing tool") and ": " in text else text
    if message == "Не найдено":
        return NotFound()
    if message in FORBIDDEN_TEXTS:
        return Forbidden(message)
    if message == UNAVAILABLE:
        return RuntimeError(UNAVAILABLE)
    if "validation error" in message or message == "Некорректные параметры":
        return InvalidArguments(message)
    return Conflict(message)


async def call_tool(user: User, tool: str, arguments: dict[str, Any], result_type: Any) -> Any:
    """Один вызов инструмента MCP-сервера от имени пользователя; результат — модель сервиса."""
    async with _session(user) as client:
        result = await client.call_tool(tool, {k: v for k, v in arguments.items() if v is not None})
    if result.isError:
        text = "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")
        raise _error(text)
    data = result.structuredContent or {}
    # FastMCP заворачивает список в {"result": [...]}, модель отдаёт полями как есть.
    payload = data["result"] if set(data) == {"result"} else data
    log.info("mcp call user=%s tool=%s via=%s", user.id, tool, transport())
    return TypeAdapter(result_type).validate_python(payload)


# --- Операции, которые нужны агенту. Имена инструментов — как в app/mcp_server/server.py. ---------------------------

async def get_plan(user: User, intern_id: str) -> Plan:
    if mode() == "mcp":
        return await call_tool(user, "get_plan", {"intern_id": intern_id}, Plan)
    return await checklist.get_plan(user, intern_id)


async def set_item_status(user: User, item_id: str, status: str, reason: str | None) -> PlanItem:
    if mode() == "mcp":
        return await call_tool(user, "set_item_status", {"item_id": item_id, "status": status, "reason": reason},
                               PlanItem)
    return await checklist.set_item_status(user, item_id, status, reason)


async def list_resources(user: User) -> list[AccessResource]:
    if mode() == "mcp":
        return await call_tool(user, "list_resources", {}, list[AccessResource])
    return await access.list_resources(user)


async def create_request(user: User, resource_id: str, level: str, justification: str) -> AccessRequest:
    if mode() == "mcp":
        return await call_tool(user, "create_request",
                               {"resource_id": resource_id, "level": level, "justification": justification},
                               AccessRequest)
    return await access.create_request(user, resource_id, level, justification)


async def list_requests(user: User, intern_id: str | None) -> list[AccessRequest]:
    if mode() == "mcp":
        return await call_tool(user, "list_requests", {"intern_id": intern_id}, list[AccessRequest])
    return await access.list_requests(user, intern_id)


async def decide_request(user: User, request_id: str, approve: bool, reason: str | None) -> AccessRequest:
    if mode() == "mcp":
        return await call_tool(user, "decide_request", {"request_id": request_id, "approve": approve, "reason": reason},
                               AccessRequest)
    return await access.decide_request(user, request_id, approve, reason)


async def get_skill_profile(user: User, intern_id: str) -> SkillProfile:
    if mode() == "mcp":
        return await call_tool(user, "get_skill_profile", {"intern_id": intern_id}, SkillProfile)
    return await hiring.get_skill_profile(user, intern_id)


async def list_absence_requests(user: User) -> list[AbsenceRequest]:
    if mode() == "mcp":
        return await call_tool(user, "absence_list_requests", {}, list[AbsenceRequest])
    return await absence.list_requests(user.id)
