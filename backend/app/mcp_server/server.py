"""MCP/stdio: один пользователь на процесс, права проверяют сервисы онбординга."""
import argparse
import logging
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import StrictBool, ValidationError

from app.agent.users import DEMO_USERS
from app.async_runner import run

from . import access, checklist, clock, hiring, storage
from .errors import Conflict, Forbidden, NotFound
from .models import AccessLevel, AccessRequest, AccessResource, ItemStatus, Plan, PlanItem, Reminder, SkillProfile

log = logging.getLogger("ai_buddy.mcp")
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
CHANGE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)
CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def create_server(user_id: str) -> FastMCP:
    """Пользователь разрешается один раз из конфигурации доверенного запускающего."""
    if not user_id:
        raise ValueError("Укажите пользователя: --user <id> или переменная MCP_USER_ID")
    actor = DEMO_USERS.get(user_id)
    if actor is None:
        raise ValueError("Неизвестный пользователь MCP; используйте id из DEMO_USERS")
    server = FastMCP("AI-buddy onboarding")

    async def call(operation, *args, **kwargs):
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

    @server.tool(annotations=READ)
    async def get_plan(intern_id: str) -> Plan:
        """План доступного стажёра: пункты, текущий день и следующий шаг."""
        return await call(checklist.get_plan, intern_id)

    @server.tool(annotations=CHANGE)
    async def set_item_status(item_id: str, status: ItemStatus, reason: str | None = None) -> PlanItem:
        """Изменить свой ручной пункт; наставнику вернуть закрытый пункт с причиной."""
        return await call(checklist.set_item_status, item_id, status, reason)

    @server.tool(annotations=READ)
    async def list_resources() -> list[AccessResource]:
        """Ресурсы, доступные для заявки стажёра его команды."""
        return await call(access.list_resources)

    @server.tool(annotations=CREATE)
    async def create_request(resource_id: str, level: AccessLevel, justification: str) -> AccessRequest:
        """Создать заявку на ресурс: базовый доступ выдаётся автоматически."""
        return await call(access.create_request, resource_id, level, justification)

    @server.tool(annotations=READ)
    async def list_requests(intern_id: str | None = None) -> list[AccessRequest]:
        """Свои заявки стажёра либо заявки стажёров своего наставника."""
        return await call(access.list_requests, intern_id)

    @server.tool(annotations=CHANGE)
    async def decide_request(request_id: str, approve: StrictBool, reason: str | None = None) -> AccessRequest:
        """Наставник одобряет свою pending-заявку или отклоняет с причиной."""
        return await call(access.decide_request, request_id, approve, reason)

    @server.tool(annotations=READ)
    async def get_skill_profile(intern_id: str) -> SkillProfile:
        """Карта навыков: доступна стажёру и его наставнику."""
        return await call(hiring.get_skill_profile, intern_id)

    @server.tool(annotations=READ)
    async def list_reminders() -> list[Reminder]:
        """Только активные личные напоминания пользователя, как HTTP /reminders."""
        return [reminder for reminder in await call(clock.list_reminders) if reminder.status == "active"]

    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="MCP/stdio онбординга: один пользователь на процесс")
    parser.add_argument("--user", default=os.environ.get("MCP_USER_ID"), help="ID пользователя из DEMO_USERS (или MCP_USER_ID)")
    args = parser.parse_args(argv)
    try:
        server = create_server(args.user)
    except ValueError as error:
        parser.error(str(error))
    # Несколько сессий используют одно хранилище; закрывает его владелец процесса.
    try:
        run(server.run_stdio_async(), timeout=None)
    finally:
        run(storage.get_store().close())


if __name__ == "__main__":
    main()
