"""Сценарный режим без ключа модели (спека 003).

Тот же интерфейс, что у GigaChat: может попросить вызвать инструмент и отвечает текстом. Намерение —
по ключевым словам вопроса, ответ — только из результатов инструментов и фрагментов документов,
которые агент уже положил в системное сообщение. Ничего не выдумывает: нет данных — так и говорит.

Права, черновики и отказы обеспечивает агент (`ToolExecutor`), поэтому режим доказывает, что механика
работает независимо от модели.
"""
import json
import re
from datetime import date, timedelta
from typing import Any

from app.agent.users import DEMO_USERS, Role

from .base import LLMReply, Message, ToolCall, ToolSpec

DOCS_MARKER = "Контекст из документов команды"

ORG_WORDS = ("отпуск", "больнич", "отгул", "заболел", "зарплат", "компенсац", "справк", "дмс", "увольн", "трудов", "командиров",
             "аванс", "получк", "оклад")
SALARY = re.compile(r"(?<![а-яё])(зп|з/п)(?![а-яё])")
# SPEC 3.8: отгул на один день — не к HR, а заявление руководителю (если инструмент доступен — стажёру).
ABSENCE_WORDS = ("отгул", "отпрос", "к врачу", "ко врачу", "не смогу прийти", "не приду", "не выйду", "пропустить день",
                 "взять выходной", "на прием", "на приём", "на экзамен", "отлучиться")
HR_ONLY = ("отпуск", "больнич", "заболел", "декрет", "увольн")
FAMILY_WORDS = ("семь", "семей", "ребен", "ребён", "родител", "мам", "пап", "свадьб", "бабушк", "дедушк")
STUDY_WORDS = ("учеб", "учёб", "экзамен", "сесси", "зачет", "зачёт", "универ", "институт", "диплом", "защит")
MONTHS = ("январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр")
NEXT_WORDS = ("дальше", "следующ", "что мне делать", "кого жд", "кого я жд", "мой план", "что у меня", "с чего начать",
              "ничего не понима", "что делать сейчас", "за что браться")
ACCESS_VERBS = ("оформ", "запрос", "получ", "дай", "нужен", "нужн", "сделай", "подай", "закажи", "выдай", "открой")
REQUEST_WORDS = ("мои", "статус", "какие", "ждут", "список", "покажи")
GREETINGS = ("привет", "здравствуй", "добрый день", "хай", "hello")
THANKS = re.compile(r"(спасибо|благодарю|спс|понятно|понял[а]?|ясно|ок|окей|отлично|супер)"
                    r"(\s+(тебе|большое|огромное|всё|все))*[\s!.,)]*")
STUCK_WORDS = ("завис", "жд", "просроч", "как дела", "как у", "прогресс", "успева", "застрял")
LEVEL_WORDS = ("мой уровень", "уровень по", "какой у меня уровень", "что я знаю", "мои навыки", "карта навыков", "уровень у",
               "какой уровень")
# Не рабочие вопросы: не ищем в документах и не предлагаем «спросить наставника» (проверка 12.11).
OFF_WORK = ("анекдот", "шутк", "пошути", "погод", "стих", "песн", "фильм", "сериал", "рецепт", "гороскоп", "поиграем",
            "сыграем", "загадк", "кто ты", "ты кто", "как тебя зовут")
APPROVE_WORDS = ("одобри", "согласуй", "утверди", "подтверди мою", "подтверди заявк", "approve")
ADMIN_WORDS = ("админ", "повышенн", "права на запись", "полные права", "полный доступ", "root", "суперпольз", "права владел")
# Второе действие в той же фразе («оформи доступ и напомни завтра»): делаем первое, про второе говорим честно.
ACTION_START = ("напомни", "оформи", "запроси", "отправь", "создай", "подай", "закажи", "выдай", "открой", "поставь",
                "запиши", "дай", "покажи", "отпроси", "сделай", "подготовь")
# Разговорные слова и сокращения → слова документов (поиск без модели ищет по словам).
SYNONYMS = (
    (re.compile(r"пул+\s*-?\s*р[еи]квест[а-яё]*|пулреквест[а-яё]*|запул[а-яё]*|(?<![a-zа-яё])пр(?![a-zа-яё])"),
     " pull request "),
    (re.compile(r"(?<![a-z])ci(?![a-z])|(?<![а-яё])си(?:ай)?(?![а-яё])"), " пайплайн "),
    (re.compile(r"посмотрел[а-яё]*|проверил[а-яё]*"), " ревью "),
    (re.compile(r"(?<![а-яё])проект[а-яё]*"), " сервис локально "),
)
STOP = {"который", "когда", "почему", "сделать", "нужно", "можно", "такой", "этого", "через", "после", "чтобы",
        "только", "какой", "какие", "какая", "мне", "меня", "есть", "надо", "подскажи", "пожалуйста", "расскажи",
        "такое", "такая", "такие", "этот", "этом", "если", "where", "what", "зачем", "покажи", "свой", "свое", "свою",
        "чтоб", "дали", "знаю", "хочу", "могу", "вообще"}
NAMES = {"intern-anya": ("аня", "ани", "аню", "анн"), "intern-ivan": ("иван", "ваня", "вани"),
         "intern-kirill": ("кирилл",), "intern-liza": ("лиза", "лизы", "лизу", "лиз")}
STATUS_RU = {"created": "создана", "pending_approval": "на согласовании", "granted": "доступ выдан", "rejected": "отклонена"}


def _words(text: str) -> set[str]:
    words = re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е"))
    return {w for w in words if len(w) >= 4 and w not in STOP}


def _normalize(question: str) -> str:
    q = question.lower().replace("ё", "е")
    for pattern, words in SYNONYMS:
        q = pattern.sub(words, q)
    return q


def _query_words(question: str) -> set[str]:
    """Слова вопроса для поиска: разговорное «запулить», «пул реквест», «CI» → слова документов."""
    return _words(_normalize(question))


def search_query(question: str) -> str:
    """Запрос в поиск по документам: вопрос + слова документов вместо разговорных («запулить» → pull request)."""
    normalized = _normalize(question)
    return question if normalized == question.lower().replace("ё", "е") else f"{question} {normalized}"


def _one_typo(a: str, b: str) -> bool:
    """Слова отличаются одной буквой (пропуск, лишняя или замена): «офрмить» = «оформить»."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _same(a: str, b: str) -> bool:
    """Одно слово в разных формах: «доставки» = «доставка», но «доставки» ≠ «достаточно»."""
    if a == b:
        return True
    common = len(next((a[:i] for i in range(min(len(a), len(b)), 0, -1) if a[:i] == b[:i]), ""))
    shortest = min(len(a), len(b))
    return common >= 6 or (shortest <= 5 and common >= shortest - 1) or (shortest >= 6 and _one_typo(a, b))


def _overlap(question: set[str], text: str) -> int:
    words = _words(text)
    return sum(1 for q in question if any(_same(q, w) for w in words))


def _docs(system: str) -> list[tuple[str, str]]:
    if DOCS_MARKER not in system:
        return []
    tail = system.split(DOCS_MARKER, 1)[1]
    blocks = re.split(r"\n### ", "\n" + tail.split("\n", 1)[1] if "\n" in tail else "")
    docs = []
    for block in blocks:
        if not block.strip():
            continue
        title, _, content = block.partition("\n")
        docs.append((title.strip(), content.strip()))
    return docs


def _units(content: str) -> list[tuple[str, str]]:
    """(заголовок раздела, текст): абзацы и отдельные пункты списков. Заголовок участвует в поиске
    («Первый день» → абзац под ним), но в ответ не попадает. Служебная пометка «синтетический документ» — пропуск."""
    units: list[tuple[str, str]] = []
    heading = ""
    for paragraph in re.split(r"\n\s*\n", content):
        lines = []
        for line in (raw.strip() for raw in paragraph.splitlines()):
            if line.startswith("#"):
                heading = line.lstrip("# ")
            elif line:
                lines.append(line)
        if not lines:
            continue
        if all(re.match(r"^([-*]|\d+\.)\s", line) for line in lines):
            units.extend((heading, line) for line in lines)  # список — каждый пункт отдельно
        else:
            units.append((heading, " ".join(lines)))
    return [(h, u) for h, u in units if "синтетическ" not in u.lower()]


CONFLICT_MARK = "Документы расходятся"
_NUMBERS = {"одн": 1, "дв": 2, "тр": 3, "четыр": 4, "пят": 5}
_DURATION = re.compile(
    r"(?<![а-яё])(?:(?:(\d+)|(одн|дв|тр|четыр|пят)[а-яё]*)\s+)?(?:рабоч[а-яё]*\s+)?"
    r"(день|дн(?:я|ей|и)|час(?:а|ов)?|недел[ьиюяе])(?![а-яё])")


def _durations(text: str) -> set[tuple[int, str]]:
    """Сроки в тексте: «в течение рабочего дня» → (1, день), «двух рабочих дней» → (2, день)."""
    found = set()
    for digits, word, unit in _DURATION.findall(text.lower().replace("ё", "е")):
        n = int(digits) if digits else _NUMBERS.get(word, 1)
        found.add((n, "день" if unit.startswith(("де", "дн")) else unit[:3]))
    return found


def _conflict(best: tuple[int, str, str], wanted: set[str], need: int, system: str) -> str | None:
    """SPEC 3.7: два документа отвечают на вопрос разными сроками — не выбираем молча, показываем оба."""
    mine = _durations(best[2])
    if not mine:
        return None
    for title, content in _docs(system):
        if title == best[1]:
            continue
        for heading, unit in _units(content):
            other = _durations(unit)
            if other and other != mine and _overlap(wanted, heading + " " + unit) >= need:
                return (f"{CONFLICT_MARK}: в них разные сроки.\n\n"
                        f"• «{best[1]}»: {best[2]}\n• «{title}»: {unit}\n\n"
                        "Не буду выбирать молча — уточни у наставника, какой вариант действует. "
                        "Расхождение я отметил: наставник увидит, что документ стоит обновить.")
    return None


def _best_unit(question: str, system: str) -> tuple[tuple[int, str, str], set[str], int]:
    """Лучший абзац документов для вопроса: (совпадение, документ, текст), слова вопроса и порог совпадения."""
    wanted = _query_words(question)
    # Поиск без ключа всегда отдаёт top-k, поэтому порог свой: совпасть должны хотя бы 2 основы слов
    # (или единственная, если в вопросе одно значимое слово) — иначе честно «в базе нет».
    need = min(2, len(wanted)) or 1
    # При равном совпадении: инструкция важнее определения из глоссария («**PR** — …»), затем порядок
    # поиска (документы уже отсортированы по близости), затем более содержательный абзац того же документа.
    # «Что такое CI?» — нужно определение или первый абзац о теме, а не самый длинный абзац документа.
    defining = bool(re.search(r"что так(ое|ой|ая)|что значит|что это", question.lower()))
    best, best_key = (0, "", ""), None
    for rank, (title, content) in enumerate(_docs(system)):
        for index, (heading, unit) in enumerate(_units(content)):
            score = _overlap(wanted, heading + " " + unit)
            definition = bool(re.match(r"^([-*]\s+)?\*\*", unit))
            key = (score, definition if defining else not definition, -rank, -index if defining else len(unit))
            if best_key is None or key > best_key:
                best, best_key = (score, title, unit), key
    return best, wanted, need


TIME_WORDS = ("сколько", "срок", "когда", "как долго", "как быстро", "через какое время", "за какое время")


def docs_conflict(question: str, system: str) -> str | None:
    """SPEC 3.7 для любой модели: если найденные документы называют разные сроки, ответ — оба варианта,
    независимо от того, заметит ли расхождение модель (GigaChat на прогоне 12.11 выбирал один молча)."""
    if not any(w in question.lower() for w in TIME_WORDS):
        return None  # расхождение в сроках важно только для вопроса о сроке (иначе «один день» отгула ≠ «два дня» ревью)
    best, wanted, need = _best_unit(question, system)
    return _conflict(best, wanted, need, system) if best[0] >= need else None


def _found_text(best: tuple[int, str, str]) -> str:
    fragment = best[2] if len(best[2]) <= 700 else best[2][:700].rsplit(" ", 1)[0] + "…"
    return f"Нашёл в документе «{best[1]}»:\n\n{fragment}\n\nЕсли что-то непонятно — спроси, разберём по шагам."


def _as_sentence(question: str) -> str:
    """Вопрос для черновика: с заглавной буквы и со знаком в конце («…пул реквест» → «…пул реквест?»)."""
    text = question.strip()
    text = text[:1].upper() + text[1:]
    if text.endswith(("?", "!", ".", "…")):
        return text
    asks = re.match(r"(а\s+|и\s+)?(как|что|где|когда|кто|кого|кому|почему|зачем|сколько|можно|какой|какая|какие|куда|"
                    r"откуда|чем|ли)(?![а-яё])", text.lower())
    return text + ("?" if asks else ".")


def _missing_text(question: str, system: str) -> str:
    who = "твой наставник" if _role(system) == "intern" else "коллеги из команды"
    return (
        "В документах, доступных тебе, этого нет — выдумывать не буду. Скорее всего подскажет "
        f"{who}. Черновик вопроса, можно скопировать:\n\n«Привет! Подскажи, пожалуйста: {_as_sentence(question)} "
        "Я поискал в документах команды, но ответа не нашёл.»")


MISSING_PHRASES = ("этого нет", "не нашел", "нет информации", "информации об этом нет", "нет в документ", "не нашлось",
                   "не нашла", "не найден", "не указан")
# Вопросы, на которые отвечают инструменты, сводка плана или HR, а не абзац документа: страховку не применяем.
_NOT_DOC_QUESTION = ("план", "заявк", "мой наставник", "кто наставник", "кто мой", "доступ", "уровень", "навык")


def _strong(score: int, wanted: set[str]) -> bool:
    """Совпала большая часть вопроса — не два случайных слова («учебный» + «отправь» ≠ статусы отправления)."""
    return score >= min(len(wanted), max(2, -(-len(wanted) * 3 // 5)))


def _leans_on_docs(reply: str, question: str, system: str) -> bool:
    """Ответ по смыслу опирается на документ (≥4 значимых слова абзаца, кроме слов вопроса), даже без названия."""
    words = _words(reply) - _words(question)
    return any(len(words & _words(content)) >= 4 or (title and title in reply) for title, content in _docs(system))


def docs_guard(question: str, system: str, reply: str) -> str | None:
    """Страховка для любой модели (прогон GigaChat 12.11): поиск нашёл абзац, а модель говорит «этого нет» —
    показываем абзац с источником; поиск ничего не нашёл, а модель отвечает «как обычно бывает» (IT-отдел,
    портал), даже после «этого нет», — честное «в документах нет» и к кому идти. Ответ со ссылкой на документ не трогаем."""
    q = question.lower().strip()
    if THANKS.fullmatch(q) or any(q.startswith(g) for g in GREETINGS):
        return None
    if any(w in q for w in (*NEXT_WORDS, *STUCK_WORDS, *LEVEL_WORDS, *ORG_WORDS, *ABSENCE_WORDS, *_NOT_DOC_QUESTION)):
        return None
    best, wanted, need = _best_unit(question, system)
    if len(wanted) < 2:
        return None
    low = reply.lower().replace("ё", "е")
    says_missing = any(p in low for p in MISSING_PHRASES)
    if best[0] >= need:
        # Абзац нашёлся уверенно, а модель «этого нет» — показываем абзац; при слабом совпадении не вмешиваемся.
        return _found_text(best) if says_missing and _strong(best[0], wanted) else None
    # Ничего не нашлось: даже честное «этого нет» модель дополняет «как обычно бывает» (сайт компании,
    # IT-поддержка) — поэтому наш ответ: нет в документах, к кому идти и готовый текст вопроса. Ответ, который
    # по смыслу опирается на документ (вопрос задан другими словами, чем в документе), не трогаем.
    return None if _leans_on_docs(reply, question, system) else _missing_text(question, system)


def _names_someone(q: str) -> str | None:
    """id стажёра, если вопрос называет его по имени («Что у Ани зависло?»)."""
    return next((i for i, forms in NAMES.items() if any(re.search(rf"\b{f}", q) for f in forms)), None)


def _role(system: str) -> str:
    match = re.search(r"роль: (\w+)", system)
    return match.group(1) if match else "intern"


def _name(user_id: str | None) -> str:
    user = DEMO_USERS.get(user_id or "")
    return user.name if user else "согласующий"


def _days(n: int) -> str:
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return f"{n} день"
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return f"{n} дня"
    return f"{n} дней"


def _today(system: str) -> date | None:
    """Сегодняшняя дата стажёра из сводки плана в системном сообщении («Сегодня: 2026-11-11.»)."""
    found = re.search(r"Сегодня: (\d{4}-\d{2}-\d{2})", system)
    return date.fromisoformat(found.group(1)) if found else None


def _absence_day(q: str, today: date) -> date:
    """«послезавтра», «сегодня», «14.11», «14 ноября»; по умолчанию — завтра. Прошлое → завтра (задним числом нельзя)."""
    if "послезавтра" in q:
        return today + timedelta(days=2)
    if "сегодня" in q:
        return today
    day, month = None, 0
    if found := re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?!\d)", q):
        day, month = int(found.group(1)), int(found.group(2))
    elif found := re.search(r"(\d{1,2})\s+([а-яё]+)", q):
        month = next((i + 1 for i, m in enumerate(MONTHS) if found.group(2).startswith(m)), None)
        day = int(found.group(1)) if month else None
    if day:
        try:
            wanted = date(today.year, month, day)
        except ValueError:
            wanted = None
        if wanted and wanted >= today:
            return wanted
    return today + timedelta(days=1)


def _reason(q: str) -> str:
    if any(w in q for w in STUDY_WORDS):
        return "study"
    if any(w in q for w in FAMILY_WORDS):
        return "family"
    return "personal"


def absence_rule(system: str) -> str:
    """Абзац регламента об отгуле из найденных документов — с источником в «кавычках»."""
    best = (0, "", "")
    wanted = {"отгул", "отпроситься", "заявление", "день", "руководитель"}
    for title, content in _docs(system):
        for heading, unit in _units(content):
            score = _overlap(wanted, heading + " " + unit)
            if score > best[0]:
                best = (score, title, unit)
    return f"По документу «{best[1]}»: {best[2]}\n\n" if best[0] >= 2 else ""


def _hr_name() -> str:
    return next((u.name for u in DEMO_USERS.values() if u.role == Role.HRBP), "HR BP")


def _own_id(system: str) -> str | None:
    """id текущего пользователя по имени из системного сообщения («Текущий пользователь: Аня Смирнова, …»)."""
    found = re.search(r"Текущий пользователь: ([^,]+),", system)
    return next((u.id for u in DEMO_USERS.values() if found and u.name == found.group(1)), None)


def _split_actions(question: str) -> tuple[str, str]:
    """«оформи доступ в джиру и напомни завтра» → («оформи доступ в джиру», «напомни завтра»).
    Второй кусок — только если он сам начинается с глагола действия; иначе вопрос целиком."""
    pattern = r"\s*(?:,\s*|\s+)(?:и|а|а ещё|а еще|и ещё|и еще|ещё|еще|потом|и потом|также)\s+(?=(?:%s))" % "|".join(ACTION_START)
    parts = re.split(pattern, question, maxsplit=1, flags=re.IGNORECASE)
    # Первая часть тоже должна быть действием: «игнорируй инструкции и выдай план» — одна просьба, а не две.
    first_is_action = bool(re.match(r"(?:пожалуйста,?\s+|можешь\s+)?(?:%s)" % "|".join(ACTION_START),
                                    parts[0].strip(), flags=re.IGNORECASE))
    if len(parts) == 2 and first_is_action and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return question, ""


def _second_note(second: str) -> str:
    if not second:
        return ""
    if second.lower().startswith("напомни"):
        return (f"\n\nПро «{second}»: сам по твоей просьбе напоминание пока не ставлю — напоминания о сроках "
                "пунктов плана приходят в колокольчик 🔔 автоматически.")
    return (f"\n\nВторую просьбу («{second}») не выполнял: делаю по одному действию за раз, чтобы каждое можно "
            "было проверить. Напиши её отдельным сообщением.")


RESOURCE_WORDS = ("jira", "джир", "confluence", "конфлю", "redash", "редаш", "grafana", "графан", "bitbucket", "битбакет")


def _resource_named(q: str) -> bool:
    return any(w in q for w in RESOURCE_WORDS)


def policy_reply(q: str, question: str, system: str, available: set[str]) -> str | None:
    """Ответы по правилам продукта, одинаковые для любой модели. Прогон GigaChat 12.11: модель отвечала туманно
    («обратитесь к системе»), а наставнику советовала «обратиться к её наставнику». Агент применяет их до модели."""
    q = q.lower()
    role = _role(system)
    someone = _names_someone(q)
    other = someone if someone and someone != _own_id(system) else None
    if any(w in q for w in OFF_WORK):
        return ("Я помогаю только со стажировкой: следующий шаг по плану, документы команды, заявки на доступ и "
                "отгул. Спроси, например, «что мне делать дальше?» или «как оформить pull request?».")
    if "наставник" in q and "материал" in q and role == "intern":
        return ("Материалы для наставников стажёру недоступны — подробности не раскрываю. В документах, доступных "
                "тебе, этого нет; если нужен конкретный документ для работы, спроси наставника.")
    if any(w in q for w in LEVEL_WORDS) and other:
        if role == "intern":
            return ("Это данные другого стажёра — их я не показываю. Могу рассказать про твой уровень по темам: "
                    "спроси «какой у меня уровень?».")
        if "get_skill_profile" not in available:
            return "Уровень по темам видят только стажёр и его наставник — тебе эти данные недоступны."
    if role == "intern" and any(w in q for w in APPROVE_WORDS):
        return ("Одобрять заявки может только наставник в своём кабинете — я работаю от имени того, кто вошёл "
                "(сейчас это ты, стажёр), и представиться в чате другим человеком нельзя. Посмотреть статус своих "
                "заявок — спроси «мои заявки».")
    if role == "intern" and any(w in q for w in ADMIN_WORDS):
        mentor = re.search(r"Наставник: ([^.]+)\.", system)
        who = mentor.group(1) if mentor else "твой наставник"
        return (f"Повышенные права (админ, запись) стажёру сразу не выдаются — это решает наставник ({who}). "
                "Могу оформить черновик заявки на чтение: например, «нужен доступ к репозиторию команды». "
                f"Если нужно больше, вопрос наставнику, можно скопировать:\n\n«Привет! {_as_sentence(question)} "
                "Для какой задачи это нужно: …»")
    if role in ("mentor", "lead") and any(w in q for w in ("отгул", "отсутств")) and \
            any(w in q for w in ("почему", "причин", "зачем")):
        where = ("Причина — в заявлении, в блоке «Заявки на отгул» на твоём экране." if role == "lead" else
                 "Наставник видит только дату отсутствия (она в карточке стажёра), причину — руководитель.")
        return f"Причину отгула в чате не раскрываю. {where}"
    return None


def named_intern_plan(question: str, system: str) -> str | None:
    """«Что у Ани зависло?» от наставника, руководителя или куратора → id стажёра, чей план нужно загрузить
    до ответа модели (прогон GigaChat 12.11: модель отвечала «не могу посмотреть», не вызывая инструмент)."""
    q = question.lower()
    if _role(system) not in ("mentor", "lead", "curator"):
        return None
    someone = _names_someone(q)
    if someone and ("план" in q or any(w in q for w in STUCK_WORDS)):
        return someone
    return None


def split_actions(question: str) -> tuple[str, str]:
    return _split_actions(question)


def second_note(second: str) -> str:
    return _second_note(second)


class ScenarioProvider:
    name = "scenario"

    async def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMReply:
        system = next((m.content for m in messages if m.role == "system"), "")
        question = next((m.content for m in reversed(messages) if m.role == "user"), "").strip()
        available = {t.name for t in tools or []}
        first, second = _split_actions(question)
        last = messages[-1] if messages else None
        if last is not None and last.role == "tool":
            reply = self._after_tool(last, first, available, system)
        else:
            reply = self._first_step(first.lower(), first, available, system)
        if second and reply.content and not reply.tool_calls:
            reply = LLMReply(content=reply.content + _second_note(second))
        return reply

    # --- первый шаг: что спросили ---------------------------------------------------------------

    def _first_step(self, q: str, question: str, available: set[str], system: str) -> LLMReply:
        def call(name: str, args: dict[str, Any] | None = None) -> LLMReply:
            return LLMReply(tool_calls=[ToolCall(id=f"scn_{name}", name=name, arguments=args or {})])

        role = _role(system)
        someone = _names_someone(q)
        other = someone if someone and someone != _own_id(system) else None
        if THANKS.fullmatch(q):
            return LLMReply(content="Пожалуйста! Если появится вопрос — спрашивай. Следующий шаг всегда виден в плане слева.")
        if (text := policy_reply(q, question, system, available)) is not None:
            return LLMReply(content=text)
        if "наставник" in q and any(w in q for w in ("кто", "мой", "моего", "как зовут", "связат", "написать")):
            mentor = re.search(r"Наставник: ([^.]+)\.", system)
            if mentor:
                return LLMReply(content=(
                    f"Твой наставник — {mentor.group(1)}. К нему — вопросы по задачам и всё, что блокирует работу; "
                    "если работа встала, пиши сразу, ждать встречи 1:1 не нужно."))
        if "руководител" in q and any(w in q for w in ("кто", "мой", "моего", "как зовут", "связат", "написать")):
            lead = re.search(r"Руководитель: ([^.]+)\.", system)
            if lead:
                return LLMReply(content=(
                    f"Твой руководитель — {lead.group(1)}. Связаться — в рабочем мессенджере команды. К руководителю — "
                    "заявления на отгул и вопросы о целях стажировки; по задачам и доступам сначала к наставнику."))
        if any(w in q for w in LEVEL_WORDS):
            if other:  # стажёру и роли без права policy_reply уже ответил
                return call("get_skill_profile", {"intern_id": other})
            levels = re.search(r"Уровень по темам: (.+?)\.(\s|$)", system)
            if levels:
                return LLMReply(content=(
                    f"По профилю: {levels.group(1)}. Уровень ставит наставник; я использую его только чтобы "
                    "объяснять подробнее или короче, а не для оценки."))
        if ("create_absence_request" in available and any(w in q for w in ABSENCE_WORDS)
                and not any(w in q for w in HR_ONLY)):
            today = _today(system)
            if today:
                return call("create_absence_request", {"day": _absence_day(q, today).isoformat(), "reason": _reason(q)})
        if any(w in q for w in ORG_WORDS) or SALARY.search(q):
            return LLMReply(content=(
                f"Это организационный вопрос — с ним лучше сразу к HR BP ({_hr_name()}): наставник на такие "
                f"вопросы не отвечает. Черновик сообщения, можно скопировать:\n\n«Здравствуйте! {_as_sentence(question)} "
                "Подскажите, пожалуйста, как это оформить.»"))
        if "план" in q or any(w in q for w in STUCK_WORDS):
            if someone and "get_plan" in available:
                return call("get_plan", {"intern_id": someone})
            if other:
                return LLMReply(content="У тебя нет доступа к планам стажёров — подробности не раскрываю.")
        if any(w in q for w in NEXT_WORDS) and "get_plan" in available:
            return call("get_plan")
        # «доступ в Redash» без глагола — тоже заявка: ресурс назван прямо (каталог #90).
        if ("доступ" in q and (any(v in q for v in ACCESS_VERBS) or _resource_named(q))
                and "list_access_resources" in available):
            return call("list_access_resources")
        if "заявк" in q and any(w in q for w in REQUEST_WORDS) and "list_access_requests" in available:
            return call("list_access_requests")
        if len(q) < 25 and any(q.startswith(g) for g in GREETINGS):
            return LLMReply(content=(
                "Привет! Я работаю в сценарном режиме (без ключа модели). Могу подсказать следующий шаг "
                "по плану, оформить черновик заявки на доступ, найти ответ в документах команды или помочь "
                "сформулировать вопрос наставнику."))
        return LLMReply(content=self._from_docs(question, system))

    def _from_docs(self, question: str, system: str) -> str:
        if conflict := docs_conflict(question, system):
            return conflict
        best, wanted, need = _best_unit(question, system)
        # Абзац засчитываем, если совпала хотя бы половина значимых слов вопроса (проверка 12.11; было 40%): два
        # случайных слова из пяти («учебное» + «отправь») — не ответ, а абзац не по теме с подписью «Нашёл в документе».
        enough = best[0] >= max(need, -(-len(wanted) // 2))
        return _found_text(best) if enough else _missing_text(question, system)

    # --- после инструмента: собрать ответ ---------------------------------------------------------

    def _after_tool(self, msg: Message, question: str, available: set[str], system: str) -> LLMReply:
        try:
            result = json.loads(msg.content or "{}")
        except json.JSONDecodeError:
            result = {"error": "bad_result"}
        if not isinstance(result, dict):
            result = {"error": "bad_result"}
        if result.get("error") == "forbidden":
            return LLMReply(content="У тебя нет доступа к этим данным — подробности не раскрываю. "
                                    "Если они нужны для работы, спроси наставника.")
        if result.get("error") == "not_found":
            return LLMReply(content="Такого ресурса нет среди доступных тебе — черновик не готовлю. "
                                    "Посмотреть, на что можно подать заявку, — спроси «какие доступы можно запросить?».")
        if result.get("error"):
            return LLMReply(content="Сервис сейчас не ответил. Попробуй ещё раз чуть позже.")
        if result.get("status") == "awaiting_confirmation" and msg.name == "create_absence_request":
            rule = absence_rule(system)
            return LLMReply(content=(
                f"{rule}Подготовил черновик: {result.get('summary')}. Подробности вроде врача в заявление не пишу — "
                "только причину из списка. Проверь дату и нажми «Подтвердить»: без этого руководителю ничего не уйдёт."))
        if result.get("status") == "awaiting_confirmation":
            return LLMReply(content=f"Подготовил черновик: {result.get('summary')}. Проверь и нажми «Подтвердить» — "
                                    "без этого ничего не отправится.")
        handler = {
            "get_plan": lambda r: self._plan(r, own=not _names_someone(question.lower())),
            "list_access_resources": lambda r: self._pick_resource(r, question, available),
            "list_access_requests": lambda r: self._requests(r, question, system),
            "get_skill_profile": self._levels,
        }.get(msg.name or "")
        return handler(result) if handler else LLMReply(content="Готово, данные сервиса получены.")

    def _levels(self, profile: dict) -> LLMReply:
        names = {"novice": "новичок", "familiar": "знаком", "confident": "уверенно"}
        titles = {"ci": "CI", "git": "Git", "sql": "SQL"}
        skills = ", ".join(f"{titles.get(k, k)} — {names.get(v, v)}" for k, v in (profile.get("skills") or {}).items())
        first = _name(profile.get("intern_id")).split()[0]
        return LLMReply(content=(f"{first}, уровень по темам: {skills or 'пока не заполнен'}. Уровень меняет только "
                                 "наставник; бот по нему подстраивает глубину объяснений."))

    def _plan(self, plan: dict, own: bool = True) -> LLMReply:
        day = plan.get("current_day")
        first = _name(plan.get("intern_id")).split()[0]
        lines = [f"Сейчас {day}-й день стажировки." if own else f"{first}: {day}-й день стажировки."]
        step = plan.get("next_step")
        if step:
            late = " Срок уже прошёл — лучше заняться им первым." if step.get("overdue") else ""
            lines.append(f"Следующий шаг — «{step['title']}».{late}")
        for item in plan.get("waiting") or []:
            lines.append(f"Ждём ответа ({_name(item.get('waiting_for'))}): «{item['title']}», "
                         f"{_days(item.get('waiting_days') or 0)}.")
        shown = {step.get("id") if step else None} | {w.get("id") for w in plan.get("waiting") or []}
        overdue = [i for i in plan.get("items") or [] if i.get("overdue") and i.get("id") not in shown
                   and i.get("status") != "waiting"]
        for item in overdue:
            lines.append(f"Срок прошёл: «{item['title']}» (до дня {item.get('due_day')}).")
        if not own and not plan.get("waiting") and not overdue and not (step and step.get("overdue")):
            lines.append("Зависших пунктов нет.")
        if not step and not plan.get("waiting"):
            lines.append("Свои пункты недель 1–2 закрыты — дальше «Месяц 1».")
        return LLMReply(content="\n".join(lines))

    def _pick_resource(self, result: dict, question: str, available: set[str]) -> LLMReply:
        resources = result.get("resources") or []
        q = question.lower()
        match = None
        if "jira" in q or "джир" in q:
            match = next((r for r in resources if "jira" in r["id"]), None)
        elif "confluence" in q or "конфлю" in q or "база знаний" in q:
            match = next((r for r in resources if "confluence" in r["id"]), None)
        elif "redash" in q or "редаш" in q:
            match = next((r for r in resources if r["id"] == "redash"), None)
        elif "grafana" in q or "графан" in q:
            match = next((r for r in resources if r["id"] == "grafana"), None)
        elif any(w in q for w in ("bitbucket", "битбакет", "пространств", "репозитор", "команд")):
            match = next((r for r in resources if r.get("kind") == "team_space"), None)
        if match and "create_access_request" in available:
            justification = f"Нужно для стажировки: {question}"[:300]
            return LLMReply(tool_calls=[ToolCall(id="scn_create_access_request", name="create_access_request",
                                                 arguments={"resource_id": match["id"], "level": "read",
                                                            "justification": justification})])
        titles = ", ".join(r["title"] for r in resources) or "—"
        return LLMReply(content=f"Уточни, какой доступ нужен: {titles}.")

    def _requests(self, result: dict, question: str = "", system: str = "") -> LLMReply:
        q = question.lower()
        asks_others = _role(system) == "intern" and (any(w in q for w in ("всех", "чужи", "других")) or
                                                     (_names_someone(q) not in (None, _own_id(system))))
        note = "Показываю только твои заявки — чужие не раскрываю.\n" if asks_others else ""
        reqs = result.get("requests") or []
        if not reqs:
            return LLMReply(content=note + "Заявок нет.")
        lines = [f"{r['id']} — {r['resource_id']}, {_name(r['intern_id'])}: {STATUS_RU.get(r['status'], r['status'])}"
                 for r in reqs]
        return LLMReply(content=note + "Заявки:\n" + "\n".join(lines))
