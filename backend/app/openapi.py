"""Описание API в формате OpenAPI 3.1 и страница Swagger UI (внедряемость, чекпоинт 2).

Эксперт: «как нам забрать ваш проект, не переписывая код?» Другая система Авито должна видеть, какие адреса есть и что
им отправлять. Описание собирается из самого приложения при запросе: список адресов — из маршрутов Flask, описание —
из докстринга обработчика, тело запроса — из pydantic-модели, которую обработчик читает (`_body(Model)` или
`Model.model_validate`), параметры строки запроса — из `request.args.get(...)`. Поэтому оно не расходится с кодом:
новый адрес появляется в описании сам (тест проверяет, что описаны все).
"""
import inspect
import re
from typing import Any

from flask import Flask
from pydantic import BaseModel

from .config import settings

TITLE = "AI-buddy API"
TAGS = {  # первый сегмент пути → раздел документации
    "chat": "Чат с агентом", "actions": "Действия: черновик → подтверждение", "plan": "План адаптации",
    "profile": "Карта навыков", "skills": "Карта навыков", "access": "Заявки на доступ", "absence": "Отгулы",
    "reminders": "Напоминания", "mentor": "Вопросы наставнику («память»)", "metrics": "Метрики",
    "feedback": "Метрики", "documents": "Документы", "interns": "Стажёры", "me": "Пользователь",
    "health": "Служебное", "demo": "Демо-панель", "integrations": "Интеграции", "openapi.json": "Служебное",
    "docs": "Служебное",
}
PUBLIC = {"health", "openapi_json", "swagger_ui"}  # без заголовка пользователя
SERVICE = {"integration_hired", "integration_mattermost"}  # вызывают системы, а не люди: ключ службы


def _models(app: Flask) -> dict[str, type[BaseModel]]:
    """Все pydantic-модели модулей, где живут обработчики, — по имени."""
    found: dict[str, type[BaseModel]] = {}
    for view in app.view_functions.values():
        module = inspect.getmodule(view)
        for name, obj in vars(module).items() if module else ():
            if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
                found[name] = obj
    return found


def _source(view) -> str:
    try:
        return inspect.getsource(view)
    except (OSError, TypeError):
        return ""


# Подписи для обработчиков без докстринга (остальные берутся из докстринга).
SUMMARIES = {
    "health": "Проверка живости и режима модели",
    "me": "Кто вошёл (имитация входа)",
    "chat": "Вопрос агенту: ответ, источники, черновики, пункт плана и вкладка чата",
    "list_actions": "Мои действия и черновики",
    "confirm_action": "Подтвердить черновик — только после этого действие выполняется",
    "cancel_action": "Отменить черновик — ничего не отправляется",
    "plan": "План адаптации стажёра: пункты, этапы, следующий шаг",
    "item_status": "Отметить пункт плана (свой или «вернуть» наставником)",
    "summary": "Итоги недели: только факты из плана",
    "resources": "Каталог ресурсов для заявки на доступ",
    "requests_list": "Заявки на доступ: свои или своих стажёров",
    "decide": "Одобрить или отклонить заявку на доступ (наставник)",
    "skills": "Карта навыков стажёра",
    "reminders": "Напоминания и уведомления (колокольчик)",
    "snooze": "Отложить напоминание",
    "reminder_done": "Закрыть напоминание",
    "feedback": "Оценка ответа: полезно / не полезно",
    "metrics_view": "Метрики пользы: вопросы, темы, «нет в документах»",
    "next_day": "Демо: сдвинуть календарь на день",
    "reset": "Демо: вернуть данные к началу",
}


def _summary(view) -> tuple[str, str]:
    doc = inspect.getdoc(view) or SUMMARIES.get(view.__name__, "")
    first, _, rest = doc.partition("\n")
    return first.strip() or view.__name__.replace("_", " "), rest.strip()


def build_spec(app: Flask) -> dict[str, Any]:
    models = _models(app)
    schemas: dict[str, Any] = {}
    paths: dict[str, Any] = {}

    def ref(model: type[BaseModel]) -> dict:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, sub in schema.pop("$defs", {}).items():
            schemas.setdefault(name, sub)
        schemas.setdefault(model.__name__, schema)
        return {"$ref": f"#/components/schemas/{model.__name__}"}

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.endpoint == "static":
            continue
        view = app.view_functions[rule.endpoint]
        source = _source(view)
        path = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule.rule)
        first = path.strip("/").split("/")[0] or "health"
        summary, description = _summary(view)
        endpoint_name = rule.endpoint.split(".")[-1]
        params = [{"name": p, "in": "path", "required": True, "schema": {"type": "string"}} for p in rule.arguments]
        params += [{"name": q, "in": "query", "required": False, "schema": {"type": "string"}}
                   for q in dict.fromkeys(re.findall(r"request\.args\.get\(\s*[\"'](\w+)[\"']", source))]
        if "_intern_id()" in source and not any(p["name"] == "intern_id" for p in params):
            params.append({"name": "intern_id", "in": "query", "required": False, "schema": {"type": "string"},
                           "description": "Чей план/профиль (наставнику, руководителю); по умолчанию — свой"})
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            op: dict[str, Any] = {"tags": [TAGS.get(first, "Прочее")], "summary": summary, "operationId": f"{method.lower()}_{endpoint_name}"}
            if description:
                op["description"] = description
            if params:
                op["parameters"] = params
            body = re.search(r"_body\(\s*(\w+)", source) or re.search(r"(\w+)\.model_validate\(", source)
            name = body.group(1) if body else None
            if method in ("POST", "PUT", "PATCH", "DELETE") and name in models:
                op["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(models[name])}}}
            response: dict[str, Any] = {"description": "Успех"}
            if endpoint_name == "chat" and "ChatResponse" in models:
                response["content"] = {"application/json": {"schema": ref(models["ChatResponse"])}}
            op["responses"] = {"200": response, "4XX": {"description": "Ошибка: {\"detail\": \"…\"}"}}
            if endpoint_name in SERVICE:
                op["security"] = [{"serviceToken": []}]
            elif endpoint_name in PUBLIC or rule.endpoint in PUBLIC:
                op["security"] = []
            paths.setdefault(path, {})[method.lower()] = op

    return {
        "openapi": "3.1.0",
        "info": {
            "title": TITLE,
            "version": "1.0",
            "description": (
                "ИИ-помощник стажёра. Пользователь в прототипе передаётся заголовком `X-User-Id` (имитация входа; при "
                "внедрении — корпоративный SSO, одна функция `app/agent/users.get_user`). Системы Авито (найм, "
                "Mattermost) вызывают `/integrations/*` с ключом службы. Карта интеграции — docs/INTEGRATION.md."),
        },
        "servers": [{"url": "/"}],
        "security": [{"userHeader": []}],
        "components": {
            "securitySchemes": {
                "userHeader": {"type": "apiKey", "in": "header", "name": "X-User-Id",
                               "description": "Имитация входа: id демо-пользователя, например intern-anya"},
                "serviceToken": {"type": "http", "scheme": "bearer",
                                 "description": "Ключ службы INTEGRATION_TOKEN из .env (для систем, не людей)"},
            },
            "schemas": schemas,
        },
        "paths": paths,
    }


# Swagger UI — статикой с CDN jsdelivr (точная версия). Без интернета страница не загрузится, но /openapi.json работает
# и открывается в любом клиенте (Postman, Insomnia, импорт в API-шлюз).
SWAGGER_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI-buddy API</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
<style>html, body { background: #fff; color: #3b4151; margin: 0; } .offline { font: 16px/1.5 sans-serif; padding: 24px; }</style>
</head><body>
<div id="ui"></div>
<noscript>Описание API в формате OpenAPI: <a href="openapi.json">openapi.json</a></noscript>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>
// Финальная проверка 13.11: без интернета страница была пустой, в тёмной теме браузера — тёмный текст на тёмном.
if (window.SwaggerUIBundle) {
  window.ui = SwaggerUIBundle({ url: "openapi.json", dom_id: "#ui", persistAuthorization: true });
} else {
  document.getElementById("ui").innerHTML = '<div class="offline">Страница Swagger UI грузится с cdn.jsdelivr.net — '
    + 'сейчас он недоступен. Описание API целиком: <a href="openapi.json">openapi.json</a> (откроется в Postman, '
    + 'Insomnia или любом клиенте OpenAPI).</div>';
}
</script>
</body></html>"""


def register(app: Flask) -> None:
    @app.get("/openapi.json")
    def openapi_json():
        """Описание API в формате OpenAPI 3.1 — собирается из кода приложения."""
        spec = build_spec(app)
        spec["info"]["x-llm-provider"] = settings.llm_provider
        return spec

    @app.get("/docs")
    def swagger_ui():
        """Страница Swagger UI: все адреса API, можно вызвать прямо из браузера."""
        return SWAGGER_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}
