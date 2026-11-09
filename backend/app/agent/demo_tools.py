"""Демонстрационные инструменты — проверка механики (права, черновики), а не продуктовые сценарии.

Продуктовые инструменты (отгул, доступы и т.п.) появятся после интервью и придут из MCP-сервера
(зона Codex) через тот же ToolRegistry.
"""
from datetime import date

from pydantic import BaseModel, Field

from .tools import Tool, ToolRegistry
from .users import DEMO_USERS, User, can_view_intern

_reminders: list[dict] = []  # имитация «сервиса напоминаний»


def _public_profile(u: User) -> dict:
    mentor = DEMO_USERS.get(u.mentor_id or "")
    return {
        "id": u.id,
        "name": u.name,
        "role": u.role.value,
        "team": u.team,
        "mentor": mentor.name if mentor else None,
    }


class NoArgs(BaseModel):
    pass


async def get_my_profile(user: User, args: NoArgs) -> dict:
    return _public_profile(user)


class InternArgs(BaseModel):
    intern_id: str = Field(description="id стажёра, например intern-anya")


def _can_view(user: User, args: InternArgs) -> bool:
    intern = DEMO_USERS.get(args.intern_id)
    return intern is not None and can_view_intern(user, intern)


async def get_intern_profile(user: User, args: InternArgs) -> dict:
    return _public_profile(DEMO_USERS[args.intern_id])


class ReminderArgs(BaseModel):
    text: str = Field(min_length=1, max_length=300, description="О чём напомнить")
    remind_on: date = Field(description="Дата напоминания, ГГГГ-ММ-ДД")


async def create_reminder(user: User, args: ReminderArgs) -> dict:
    reminder = {"id": f"rem_{len(_reminders) + 1}", "user_id": user.id, **args.model_dump(mode="json")}
    _reminders.append(reminder)
    return {"status": "created", "reminder": reminder}


def register_demo_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="get_my_profile",
        description="Профиль текущего пользователя: имя, роль, команда, наставник.",
        args_model=NoArgs, permission="profile:read", handler=get_my_profile,
    ))
    registry.register(Tool(
        name="get_intern_profile",
        description="Профиль стажёра по id. Доступно его наставнику, руководителю, HR BP и куратору.",
        args_model=InternArgs, permission="interns:read", handler=get_intern_profile, authorize=_can_view,
    ))
    registry.register(Tool(
        name="create_reminder",
        description="Создать напоминание пользователю на дату. Выполняется только после подтверждения.",
        args_model=ReminderArgs, permission="reminders:write", handler=create_reminder, kind="write",
        describe=lambda a: f"Напоминание на {a.remind_on:%d.%m.%Y}: {a.text}",
    ))
