"""MCP/stdio: тонкий транспорт над авторизованными сервисами онбординга."""
from contextlib import asynccontextmanager
import logging

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import StrictBool, ValidationError

from app.agent.users import DEMO_USERS, User
from app.async_runner import run

from . import access, checklist, clock, hiring, storage
from .errors import Conflict, Forbidden, NotFound
from .models import AccessLevel, AccessRequest, AccessResource, ItemStatus, Plan, PlanItem, Reminder, SkillProfile

log = logging.getLogger("ai_buddy.mcp")


@asynccontextmanager
async def _lifespan(server: FastMCP):
    try:
        yield
    finally:
        # In-memory MCP-транспорт отменяет серверную задачу при закрытии клиента.
        with anyio.CancelScope(shield=True):
            await storage.get_store().close()


mcp = FastMCP("AI-buddy onboarding", lifespan=_lifespan)
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def _actor(user_id: str) -> User:
    actor = DEMO_USERS.get(user_id)
    if actor is None:
        raise ToolError("Неизвестный пользователь")
    return actor


async def _call(operation, user_id, *args, **kwargs):
    actor = _actor(user_id)
    try:
        return await operation(actor, *args, **kwargs)
    except NotFound:
        # Чужой и отсутствующий объект дают один и тот же ответ MCP.
        raise ToolError("Не найдено") from None
    except (Forbidden, Conflict) as error:
        raise ToolError(str(error)) from None
    except ValidationError:
        raise ToolError("Некорректные параметры") from None
    except Exception as error:
        log.warning("MCP service %s failed (%s)", operation.__name__, type(error).__name__)
        raise ToolError("Сервис временно недоступен") from None


@mcp.tool(annotations=READ)
async def get_plan(user_id: str, intern_id: str) -> Plan:
    """План доступного стажёра: пункты, текущий день и следующий шаг."""
    return await _call(checklist.get_plan, user_id, intern_id)


@mcp.tool(annotations=WRITE)
async def set_item_status(user_id: str, item_id: str, status: ItemStatus, reason: str | None = None) -> PlanItem:
    """Изменить свой ручной пункт; наставнику вернуть закрытый пункт с причиной."""
    return await _call(checklist.set_item_status, user_id, item_id, status, reason)


@mcp.tool(annotations=READ)
async def list_resources(user_id: str) -> list[AccessResource]:
    """Ресурсы, доступные для заявки стажёра его команды."""
    return await _call(access.list_resources, user_id)


@mcp.tool(annotations=WRITE)
async def create_request(user_id: str, resource_id: str, level: AccessLevel, justification: str) -> AccessRequest:
    """Создать заявку на ресурс: базовый доступ выдаётся автоматически."""
    return await _call(access.create_request, user_id, resource_id, level, justification)


@mcp.tool(annotations=READ)
async def list_requests(user_id: str, intern_id: str | None = None) -> list[AccessRequest]:
    """Свои заявки стажёра либо заявки стажёров своего наставника."""
    return await _call(access.list_requests, user_id, intern_id)


@mcp.tool(annotations=WRITE)
async def decide_request(user_id: str, request_id: str, approve: StrictBool, reason: str | None = None) -> AccessRequest:
    """Наставник одобряет свою pending-заявку или отклоняет с причиной."""
    return await _call(access.decide_request, user_id, request_id, approve, reason)


@mcp.tool(annotations=READ)
async def get_skill_profile(user_id: str, intern_id: str) -> SkillProfile:
    """Карта навыков: доступна стажёру и его наставнику."""
    return await _call(hiring.get_skill_profile, user_id, intern_id)


@mcp.tool(annotations=READ)
async def list_reminders(user_id: str) -> list[Reminder]:
    """Личные напоминания пользователя, включая историю статусов."""
    return await _call(clock.list_reminders, user_id)


def main():
    # Не создаём отдельный event loop SDK: PostgreSQL и сервисы живут на async_runner.
    run(mcp.run_stdio_async(), timeout=None)


if __name__ == "__main__":
    main()
