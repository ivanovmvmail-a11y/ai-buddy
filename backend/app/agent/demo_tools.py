"""Демонстрационные инструменты — профили пользователей. Напоминание по просьбе (`create_reminder`) с 13.11 —
настоящий сервис, см. `onboarding_tools.py`.

Продуктовые инструменты (отгул, доступы и т.п.) появятся после интервью и придут из MCP-сервера
(зона Codex) через тот же ToolRegistry.
"""
from pydantic import BaseModel, Field

from .tools import Tool, ToolRegistry
from .users import DEMO_USERS, User, can_view_intern

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
