"""Пункты плана прямо из чата (чекпоинт 2, 13.11: «в плане есть кнопка "Объяснить", а в чате нету»; «сдать задание
можно только в плане — логичнее, чтобы всё проходило через чат»).

Стажёр пишет «объясни пункт про песочницу» или «хочу сдать задание по гиту» — сервер узнаёт пункт его плана и
отвечает так же, как кнопка: объяснение по документу пункта под уровень стажёра или задание практикума, ответ на
которое придёт следующим сообщением. Без модели: одинаково с ключом и без.

«Сделать за меня» в один клик (решение эксперта): явное нажатие кнопки — уже согласие стажёра, поэтому простой доступ
(учебный сервис на чтение, выдаётся автоматически) оформляется сразу. Доступ к коду команды, права выше чтения и всё,
что проходит через согласующего, по-прежнему — черновик с «Подтвердить». Решает сервер, а не интерфейс.
"""
import re
from dataclasses import dataclass

from app.llm.scenario_provider import _overlap, _query_words
from app.mcp_server.models import PlanItem

from . import services
from .explain import explain_item
from .practice import has_check
from .users import User, by_gender

EXPLAIN_WORDS = ("объясни", "поясни", "расскажи про пункт", "расскажи о пункте", "что за пункт", "что значит пункт",
                 "что делать в пункте", "что нужно сделать в пункте", "что делать с пунктом", "как сделать пункт",
                 "explain")
PRACTICE_WORDS = ("сдать задани", "сдам задани", "сдаю задани", "проверь задани", "проверь мое задани",
                  "проверь моё задани", "сдать практикум", "сдам практикум", "проверь практикум", "сдать практику",
                  "сдать домашк", "проверь домашк", "задание выполнил", "задание сделал", "выполнил задание",
                  "сделал задание", "выполнила задание", "сделала задание", "задание выполнила", "задание сделала")
WORKING = ("week1", "week2")


@dataclass
class ItemReply:
    reply: str
    item_id: str
    mode: str | None = None  # "practice" — следующее сообщение стажёра идёт на проверку задания
    sources: list[dict] | None = None


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def _named_item(question: str, items: list[PlanItem], wide: bool = False) -> PlanItem | None:
    """Пункт по «кавычкам» или по словам названия: «объясни пункт про песочницу» → «Запустить песочницу объявлений»."""
    quoted = re.findall(r"[«\"]([^»\"]+)[»\"]", question)
    for title in quoted:
        found = next((i for i in items if _norm(i.title) == _norm(title.strip())), None)
        if found:
            return found
    wanted = _query_words(question) - {"объясни", "поясни", "пункт", "пункта", "пункте", "пунктом", "расскажи", "задание",
                                 "задания", "сдать", "проверь", "практикум"}
    if not wanted:
        return None
    def text(i: PlanItem) -> str:  # задание узнаём и по его тексту: «по CI» → «…упавший шаг пайплайна»
        return f"{i.title} {i.topic or ''} {i.practice or ''}" if wide else i.title
    ranked = sorted(((_overlap(wanted, text(i)), -n, i) for n, i in enumerate(items)), key=lambda r: r[:2], reverse=True)
    best = ranked[0] if ranked else None
    if best is None or best[0] == 0:
        return None
    if len(ranked) > 1 and ranked[1][0] == best[0]:
        return None  # ничья — не угадываем
    return best[2]


async def item_reply(question: str, user: User) -> ItemReply | None:
    """Ответ про пункт плана, если стажёр просит объяснить пункт или сдать задание. Иначе None — обычный чат."""
    q = _norm(question)
    practice = any(w in q for w in PRACTICE_WORDS)
    explain = any(w in q for w in EXPLAIN_WORDS)
    if user.role.value != "intern" or not (practice or explain):
        return None
    plan = await services.get_plan(user, user.id)
    items = [i for i in plan.items if i.stage in WORKING]
    if practice:
        open_tasks = [i for i in items if has_check(i.practice) and i.status != "done"]
        if not open_tasks:
            return None if not items else ItemReply(
                "Сейчас в твоём плане нет открытых заданий с проверкой. Задания появляются у практикумов — "
                "их подбирает наставник по карте навыков.", item_id="")
        item = _named_item(question, open_tasks, wide=True) or (open_tasks[0] if len(open_tasks) == 1 else None)
        if item is None:
            names = ", ".join(f"«{i.title}»" for i in open_tasks)
            return ItemReply(f"Какое задание сдаёшь? Открытые: {names}. Напиши, например, «сдать задание по "
                             f"{open_tasks[0].topic or open_tasks[0].title}».", item_id="")
        return ItemReply(
            f"Задание по пункту «{item.title}»: {item.practice}\n\nНапиши ответ следующим сообщением — своими словами, "
            f"что и как ты {by_gender(user, 'сделал', 'сделала')}. Я сверю его с учебным документом пункта и подскажу, чего не хватает. "
            "Это проверка задания, а не оценка: уровень по-прежнему решает наставник.",
            item_id=item.id, mode="practice")
    item = _named_item(question, items)
    if item is None:
        return None  # «объясни, что такое OKR» — вопрос к документам, а не к пункту
    body = await explain_item(user, user.id, item.id, "explain")
    return ItemReply(body["text"], item_id=item.id, sources=[body["source"]] if body["source"] else [])


async def one_click_allowed(user: User, params: dict) -> bool:
    """Можно ли оформить заявку сразу по кнопке: только чтение учебного сервиса, который выдаётся автоматически."""
    if params.get("level", "read") != "read":
        return False
    resources = await services.list_resources(user)
    resource = next((r for r in resources if r.id == params.get("resource_id")), None)
    return resource is not None and resource.kind == "base" and resource.approver == "auto"
