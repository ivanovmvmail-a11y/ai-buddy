"""Уровень стажёра в ответах чата (SPEC 3.4, 4; проверка 13.11).

С ключом модели Аня (Git — новичок) и Кирилл (Git — уверенно) на «как создать ветку и отправить на ревью?» получали
один и тот же ответ слово в слово: уровень лежал в системном промпте, но GigaChat его не учитывал. Теперь сервер сам
определяет тему вопроса, даёт модели явное указание по глубине и открывает ответ строкой, по которой стажёр видит,
что объяснение подстроено под него. Только факт из карты навыков — без оценок и слова «слабость».
"""
import re

from app.llm.scenario_provider import _normalize

TOPIC_TITLES = {"git": "Git", "sql": "SQL", "ci": "CI"}
# Слова вопроса (после замены разговорных: «гит» → git, «CI» → пайплайн, «пул реквест» → pull request).
TOPIC_WORDS = {
    "git": ("git", "ветк", "коммит", "commit", "pull request", "мерж", "merge", "rebase", "ребейз", "конфликт", "push",
            "пуш", "клонир", "репозитор"),
    "sql": ("sql", "select", "запрос к баз", "базе данных", "база данных", "базы данных", "таблиц", "redash", "редаш"),
    "ci": ("пайплайн", "pipeline", "сборк", "линтер", "автотест", "тесты", "тест упал", "тесты упали"),
}
LEVEL_RU = {"новичок": "novice", "знаком": "familiar", "уверенно": "confident"}

HINT = {
    # Проверка 14.11: «дай пример» модель понимала как «придумай» («зайди в Mattermost и посмотри статус PR»,
    # «git pull request --create»). Пример — только из документа; своих не сочинять.
    "novice": ("Стажёр в теме «{t}» — новичок. Ответь по шагам (3–6 коротких шагов), простыми словами, без лишней "
               "теории. Команду или пример приводи, только если они есть в документе — дословно; своих примеров, "
               "названий ошибок и сервисов не придумывай."),
    "familiar": "Стажёр с темой «{t}» уже знаком. Ответь коротко по шагам, без азов и без определений.",
    "confident": ("Стажёр в теме «{t}» уверен. Ответь коротко: 2–3 предложения, только то, что принято в команде, "
                  "без пошаговой инструкции, азов и примеров команд."),
}
OPENING = {
    "novice": "{t} в твоей карте навыков пока новая тема — разберу по шагам.",
    "familiar": "{t} ты уже знаешь — по шагам, без азов.",
    "confident": "{t} ты знаешь уверенно — коротко, только как принято в команде.",
}


def topic_of(question: str) -> str | None:
    """Одна тема карты навыков, о которой вопрос; если тем несколько или ни одной — None."""
    q = f" {_normalize(question)} "
    found = [t for t, words in TOPIC_WORDS.items() if any(w in q for w in words)]
    return found[0] if len(found) == 1 else None


def skills_from(system: str) -> dict[str, str]:
    """Уровни стажёра из сводки плана в системном промпте («Уровень по темам: git — новичок, sql — уверенно.»)."""
    found = re.search(r"Уровень по темам: ([^.]+)\.", system)
    if not found:
        return {}
    pairs = (part.split(" — ") for part in found.group(1).split(", "))
    return {p[0].strip(): LEVEL_RU[p[1].strip()] for p in pairs if len(p) == 2 and p[1].strip() in LEVEL_RU}


def level_for(question: str, system: str) -> tuple[str, str] | None:
    """(тема, уровень) для этого вопроса или None — тогда ответ не подстраиваем."""
    if any(w in question.lower() for w in ("уровен", "навык")):
        return None  # вопрос о самом уровне («какой у меня уровень по Git?») — отвечать надо данными, не глубиной
    topic = topic_of(question)
    level =skills_from(system).get(topic or "")
    return (topic, level) if topic and level else None


def hint(topic: str, level: str) -> str:
    return "\n\nГлубина ответа: " + HINT[level].format(t=TOPIC_TITLES.get(topic, topic))


def opening(topic: str, level: str) -> str:
    return OPENING[level].format(t=TOPIC_TITLES.get(topic, topic))
