"""Эксперимент 14.11: намерение стажёра определяет модель, а не слова в коде (INTENT_ROUTER=model).

Почему. Правила по ключевым словам надёжны там, где ошибка дорога (права, чужие данные, действия), но перехватывают
чужие вопросы: «что мне делать по git» ловилось правилом «что мне делать» и получало сводку плана. Каждая новая
формулировка требовала нового правила.

Как. Один короткий запрос к модели: «к какому намерению из списка относится сообщение, и какие у него параметры» —
ответ строго JSON. Сервер переводит намерение в команду для уже готовых обработчиков (разбор даты отгула, черновик
заявки, объяснение пункта, сдача задания, сводка плана) — права, черновики и подтверждение остаются на сервере.
Вопрос «по документам» не перехватывается правилами действий и плана — его отвечает модель по документам.

Что не меняется. Разговорные реплики, защита от «взлома», чужие данные и правила продукта (policy_reply) работают
как раньше — это «правила для опасного». Без ключа (scenario) и при любом сбое распределителя — прежний путь.
"""
import json
import logging
import re
from dataclasses import dataclass

from app.llm import Message

log = logging.getLogger("ai_buddy.intent")

INTENTS = {
    "next_step": "что делать дальше / следующий шаг / сколько осталось / что у меня по плану в целом",
    "explain_item": "объяснить конкретный пункт плана или что делать по теме Git/SQL/CI, если это пункт плана",
    "submit_practice": "сдать или проверить выполненное задание практикума",
    "absence": "отпроситься, взять отгул на день, не смогу прийти (в том числе к врачу, по учёбе, семье)",
    "access": "просьба оформить/выдать/открыть доступ к ресурсу (Jira, Confluence, Redash, Grafana, Bitbucket)",
    "reminder": "просьба поставить напоминание",
    "my_requests": "статус своих заявок на доступ или отгул",
    "hr": "больничный, отпуск, зарплата, кадровые документы",
    "docs": "вопрос о работе, процессах, инструментах, правилах, людях — ответ ищется в документах команды",
}

PROMPT = """Ты — классификатор сообщений стажёра для помощника AI-buddy. Определи ОДНО намерение из списка и параметры.
Намерения:
{intents}

Параметры (null, если не названо):
- topic: "git" | "sql" | "ci" | null — тема карты навыков;
- resource: "jira" | "confluence" | "redash" | "grafana" | "bitbucket" | null;
- item: короткое название пункта плана своими словами (например «песочница»), или null.

Правила:
- «Как получить доступ к X?» — это тоже access. «Кому писать про отгул?», «как устроен отгул?» без просьбы — docs.
- «Что мне делать по git?» — explain_item с topic "git". «Что делать, если пайплайн красный?» — docs.
- Если сомневаешься — docs.
Ответь ТОЛЬКО JSON без пояснений: {{"intent": "...", "topic": null, "resource": null, "item": null}}"""

RESOURCES = {"jira": "Jira", "confluence": "Confluence", "redash": "Redash", "grafana": "Grafana", "bitbucket": "Bitbucket"}
TOPICS = {"git": "git", "sql": "SQL", "ci": "CI"}


@dataclass
class Routed:
    intent: str
    command: str  # формулировка для готовых обработчиков сервера
    rules: bool  # применять ли правила действий и плана (False — вопрос по документам: сразу модели)


def _parse(text: str) -> dict | None:
    found = re.search(r"\{.*\}", text or "", re.S)
    if not found:
        return None
    try:
        data = json.loads(found.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and data.get("intent") in INTENTS else None


def command_for(data: dict, question: str) -> Routed:
    """Намерение → команда, которую готовые обработчики понимают однозначно. Исходные слова сохраняем там, где в них
    данные (дата отгула, текст напоминания)."""
    intent = data["intent"]
    topic = TOPICS.get(str(data.get("topic") or "").lower())
    resource = RESOURCES.get(str(data.get("resource") or "").lower())
    item = (data.get("item") or "").strip()
    if intent == "next_step":
        return Routed(intent, "что мне делать дальше?", True)
    if intent == "explain_item" and (item or topic):
        return Routed(intent, f"объясни пункт про {item or topic}", True)
    if intent == "submit_practice":
        return Routed(intent, f"хочу сдать задание{f' по {topic}' if topic else ''}", True)
    if intent == "absence":
        return Routed(intent, question if re.search(r"отгул|отпрос", question, re.I) else f"отгул: {question}", True)
    if intent == "access" and resource:
        return Routed(intent, f"оформи доступ к {resource}", True)
    if intent == "access":
        return Routed(intent, f"оформи доступ: {question}", True)
    if intent == "reminder":
        return Routed(intent, question if re.match(r"\s*напомни", question, re.I) else f"напомни {question}", True)
    if intent == "my_requests":
        return Routed(intent, "мои заявки", True)
    if intent == "hr":
        return Routed(intent, question, True)
    return Routed("docs", question, False)


async def route(llm, question: str) -> Routed | None:
    """Намерение по модели или None (сбой, непонятный ответ) — тогда прежний путь по словам."""
    intents = "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())
    try:
        reply = await llm.chat([Message(role="system", content=PROMPT.format(intents=intents)),
                                Message(role="user", content=question)])
    except Exception:  # noqa: BLE001 — распределитель не должен ронять ответ
        log.warning("intent router failed", exc_info=True)
        return None
    data = _parse(reply.content)
    if data is None:
        log.info("intent router: unparsed reply")
        return None
    routed = command_for(data, question)
    log.info("intent router intent=%s rules=%s", routed.intent, routed.rules)
    return routed
