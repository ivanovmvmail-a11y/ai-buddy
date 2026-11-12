"""Практическое задание с проверкой результата (спека 107, проверка 12.11 п. 6).

Стажёр пишет ответ на «задание на практике» пункта плана — сервер сверяет его с ключевыми фактами из учебного
документа пункта. Без модели: одинаково с ключом и без. Это проверка задания, а не оценка человека: уровень по-прежнему
меняет только наставник; засчитанное задание лишь подсказывает стажёру закрыть пункт («Готово»), а закрытые пункты темы
уже ведут к предложению наставнику (спека 202).

Задания привязаны к тексту `practice` из seed (зона Codex): тест проверяет, что каждый ключ ниже в seed есть.
"""
import re
from dataclasses import dataclass

from app.agent.users import Role, User
from app.mcp_server import checklist
from app.mcp_server.errors import NotFound

from .explain import load_doc


@dataclass(frozen=True)
class Fact:
    label: str  # что засчитано — показываем стажёру
    hint: str  # чего не хватает — подсказка без готового ответа
    variants: tuple[str, ...]  # начала слов или фразы, любое из них засчитывает факт


CHECKS: dict[str, tuple[Fact, ...]] = {
    "Создай учебную ветку, коммит и pull request.": (
        Fact("своя ветка под задачу", "с чего начинается работа над задачей — где делаются изменения?",
             ("checkout -b", "switch -c", "ветк", "branch")),
        Fact("коммит с понятным сообщением", "как сохранить изменения в истории?", ("коммит", "commit")),
        Fact("отправка ветки (push)", "как изменения попадают на сервер?", ("push", "запуш", "отправ")),
        Fact("PR в основную ветку", "как изменения попадают в основную ветку?",
             ("pull request", "пул реквест", "пулл реквест", "pr ", " pr", "мерж", "merge")),
    ),
    "Найди упавший шаг учебного пайплайна и опиши проверку исправления.": (
        Fact("разбирать первый красный шаг", "какой из упавших шагов разбирать?", ("перв",)),
        Fact("читать лог шага", "где искать текст ошибки?", ("лог", "log")),
        Fact("повторить проверку локально", "как убедиться, что ошибка воспроизводится?",
             ("локальн", "у себя", "локально")),
        Fact("новый коммит и зелёный пайплайн", "как проверить, что исправление помогло?",
             ("коммит", "commit", "зелен", "зелён", "перезапус", "прош")),
    ),
    "Опиши, почему нельзя сразу выдать зарегистрированную посылку.": (
        Fact("сначала — «принято»", "какой статус идёт сразу после регистрации?", ("принят", "прием", "приём")),
        Fact("потом «в пути» и «готово к выдаче»", "какие статусы стоят между приёмом и выдачей?",
             ("в пути", "готов")),
        Fact("статусы идут по порядку, прыжок — ошибка перехода", "что будет, если пропустить статусы?",
             ("ошибк", "по порядку", "последовательн", "нельзя пропус", "пропуст")),
    ),
}

MIN_LENGTH = 15


def has_check(practice: str | None) -> bool:
    return bool(practice) and practice in CHECKS


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower().replace("ё", "е")) + " "


def check_answer(practice: str, answer: str) -> dict:
    facts = CHECKS[practice]
    text = _norm(answer)
    found = [f for f in facts if any(v.replace("ё", "е") in text for v in f.variants)]
    missing = [f for f in facts if f not in found]
    return {"passed": not missing and len(answer.strip()) >= MIN_LENGTH,
            "found": [f.label for f in found], "missing": [f.hint for f in missing]}


async def submit(actor: User, item_id: str, answer: str) -> dict:
    """Только стажёр и только свой пункт с проверяемым заданием; чужой или без проверки — 404 (неотличимо)."""
    if actor.role != Role.INTERN:
        raise NotFound()
    plan = await checklist.get_plan(actor, actor.id)
    item = next((i for i in plan.items if i.id == item_id), None)
    if item is None or not has_check(item.practice):
        raise NotFound()
    result = check_answer(item.practice, answer)
    if len(answer.strip()) < MIN_LENGTH:
        result["missing"] = ["опиши подробнее — пара предложений своими словами."]
    doc = load_doc(item.doc_source_id)
    result["source"] = {"title": doc.title, "url": doc.url} if doc else None
    result["item_id"], result["topic"] = item.id, item.topic
    if result["passed"]:
        result["text"] = ("Задание выполнено: " + ", ".join(result["found"]) + ". "
                          + ("Можно отметить пункт «Готово»." if item.status != "done" else ""))
    else:
        hints = " ".join(h[:1].upper() + h[1:] for h in result["missing"])
        result["text"] = f"Почти. Подумай: {hints} Подсказка — в документе пункта."
    return result
