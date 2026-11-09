"""Инструменты агента и их безопасный вызов.

Два правила, заложенные в основу (см. docs/DECISIONS.md):
1. Права проверяются на сервере ПЕРЕД КАЖДЫМ вызовом инструмента — не только при поиске документов
   и не только тем, что недоступный инструмент не показан модели.
2. Инструмент, который что-то меняет (kind="write"), не выполняется сразу: создаётся черновик,
   выполнить его может только сам пользователь кнопкой «Подтвердить» (ИИ готовит — решает человек;
   ст. 16 152-ФЗ о решениях на основе автоматизированной обработки).
"""
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.llm import ToolCall, ToolSpec

from .actions import ActionStore
from .users import User, has_permission

log = logging.getLogger("ai_buddy.tools")

Handler = Callable[[User, BaseModel], Awaitable[dict[str, Any]]]
Authorize = Callable[[User, BaseModel], bool]
Describe = Callable[[BaseModel], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    permission: str
    handler: Handler
    kind: Literal["read", "write"] = "read"
    # доп. проверка на уровне конкретных данных (например, «только свой стажёр»)
    authorize: Authorize | None = None
    # человеко-понятный заголовок черновика для write-инструментов
    describe: Describe | None = None

    def spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return ToolSpec(name=self.name, description=self.description, parameters=schema)


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def available_for(self, user: User) -> list[Tool]:
        """Модели показываем только то, на что у пользователя есть право."""
        return [t for t in self.tools.values() if has_permission(user, t.permission)]


FORBIDDEN_MESSAGE = "Нет прав на это действие или на эти данные. Сведения не раскрываются."


def check_access(user: User, tool: Tool, args: BaseModel) -> bool:
    if not has_permission(user, tool.permission):
        return False
    return tool.authorize is None or tool.authorize(user, args)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, store: ActionStore) -> None:
        self.registry = registry
        self.store = store

    async def call(self, user: User, call: ToolCall) -> dict[str, Any]:
        """Выполнить вызов от модели. Возвращает результат для модели (всегда dict, без исключений)."""
        tool = self.registry.get(call.name)
        if tool is None:
            log.warning("unknown tool user=%s tool=%s", user.id, call.name)
            return {"error": "unknown_tool", "message": f"Инструмента {call.name} нет."}
        try:
            args = tool.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            return {"error": "invalid_arguments", "details": exc.errors(include_url=False, include_context=False)}

        if not check_access(user, tool, args):
            log.info("forbidden user=%s role=%s tool=%s", user.id, user.role, tool.name)
            return {"error": "forbidden", "message": FORBIDDEN_MESSAGE}

        if tool.kind == "write":
            title = tool.describe(args) if tool.describe else tool.description
            action = self.store.create(user_id=user.id, tool=tool.name, title=title, params=args.model_dump())
            log.info("draft user=%s tool=%s action=%s", user.id, tool.name, action.id)
            return {
                "status": "awaiting_confirmation",
                "action_id": action.id,
                "summary": title,
                "executed": False,
                "message": (
                    "Действие НЕ выполнено — подготовлен только черновик. Скажи пользователю: "
                    "«Подготовил черновик: <суть>. Проверь и нажми «Подтвердить»». "
                    "Не пиши, что действие создано или выполнено."
                ),
            }

        try:
            result = await tool.handler(user, args)
        except Exception as exc:  # сбой сервиса не должен ронять весь ответ
            log.exception("tool failed user=%s tool=%s", user.id, tool.name)
            return {"error": "service_unavailable", "message": f"Сервис временно недоступен: {exc}"}
        log.info("read user=%s tool=%s", user.id, tool.name)
        return result


def to_tool_content(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
