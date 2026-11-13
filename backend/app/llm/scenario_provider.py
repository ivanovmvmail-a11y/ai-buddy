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
                 "взять выходной", "на прием", "на приём", "на экзамен", "отлучиться", "отпусти")
WEEKDAY_FORMS = (r"понедельник\w*", r"вторник\w*", r"сред[ауые]", r"четверг\w*", r"пятниц[ауые]", r"суббот[ауые]",
                 r"воскресень[ея]")
_WORD_NUMBERS = {"два": 2, "две": 2, "двух": 2, "три": 3, "трех": 3, "трёх": 3, "четыре": 4, "пять": 5, "несколько": 2}
MULTI_DAY = re.compile(r"на\s+(\d+|два|две|двух|три|трех|трёх|четыре|пять|несколько)\s+(дн|день|дня)|на\s+(всю\s+)?недел")
# Попытка переписать правила или вытащить служебные инструкции — отвечаем одинаково для любой модели.
INJECTION_WORDS = ("системный промпт", "системные инструкции", "system prompt", "забудь все", "забудь правила",
                   "забудь инструкции", "игнорируй", "ты теперь", "jailbreak", "режим разработчика", "developer mode")
# Ранжирование стажёров — не делаем (SPEC 11); наставнику показываем факты по каждому.
RANKING_WORDS = ("отста", "рейтинг", "кто лучше", "кто хуже", "кто из стажёров", "кто из стажеров", "лучший стаж",
                 "худший стаж", "все стажёры", "все стажеры", "мои стажёры", "мои стажеры", "как дела у стажёр",
                 "как дела у стажер", "моих стажёр", "моих стажер", "стажёров моей", "стажеров моей",
                 "стажёры моей", "стажеры моей", "прогресс стажёр", "прогресс стажер", "прогресс у стажёр",
                 "прогресс у стажер")
# Проверка 13.11: «отмени мой отгул» → честно, что отмены нет; «подними Ане уровень» → где это делает наставник.
CANCEL_WORDS = ("отмени", "отменить", "отмена", "отзови", "отозвать", "передумал")
CANCEL_OBJECTS = ("отгул", "заявлен", "заявк", "отсутств")
LEVEL_CHANGE = ("подними", "повысь", "понизь", "опусти", "поставь", "смени", "измени", "поменяй")
FREQUENT_WORDS = ("чаще всего", "частые", "частых", "популярн", "о чём спрашивают", "о чем спрашивают")
EMOTION_WORDS = ("страшно", "боюсь", "не успева", "тревож", "паник", "волнуюсь", "перегруж", "устал", "выгора",
                 "ничего не получается", "запутал", "растерял", "не справля")
MARK_DONE = ("отметь", "я прошла", "я прошел", "я прошёл", "я сделала", "я сделал", "я закончила", "я закончил",
             "я закрыла", "я закрыл", "уже сделал", "уже прошл")
HR_ONLY = ("отпуск", "больнич", "заболел", "декрет", "увольн")
FAMILY_WORDS = ("семь", "семей", "ребен", "ребён", "родител", "мам", "пап", "свадьб", "бабушк", "дедушк")
STUDY_WORDS = ("учеб", "учёб", "экзамен", "сесси", "зачет", "зачёт", "универ", "институт", "диплом", "защит")
MONTHS = ("январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр")
NEXT_WORDS = ("дальше", "следующ", "что мне делать", "кого жд", "кого я жд", "мой план", "что у меня", "с чего начать",
              "ничего не понима", "что делать сейчас", "за что браться", "сколько мне осталось", "до конца недел", "сколько пунктов",
              # проверка 13.11 «глазами эксперта»: «че мне щас делать», «скок я уже закрыла по плану»
              "что сейчас делать", "что мне сейчас делать", "делать по плану", "сколько я закрыл", "сколько закрыл",
              "сколько я уже закрыл", "сколько уже закрыл", "сколько сделан", "сколько я сделал", "сколько уже сдела",
              "what should i do", "what to do", "next step", "what's next", "whats next")
# «Что делать, пока жду доступ?» — вопрос к документу («Пока доступ на согласовании»), а не «следующий шаг» по плану
# (проверка 13.11: «что мне делать» уводило в сводку плана).
WAITING_WORDS = ("пока жд", "пока я жд", "пока не выдал", "пока нет доступ", "пока нет ноутбук", "пока доступ",
                 "пока заявк", "пока согласу")


# Разговорные сокращения для распознавания намерения: «че/чо» → «что», «щас» → «сейчас», «скок» → «сколько».
COLLOQUIAL = ((re.compile(r"(?<![а-яё])ч[еёо](?![а-яё])"), "что"), (re.compile(r"(?<![а-яё])щас(?![а-яё])"), "сейчас"),
              (re.compile(r"(?<![а-яё])скок[а-яё]*(?![а-яё])"), "сколько"))


def colloquial(q: str) -> str:
    q = q.lower()
    for pattern, word in COLLOQUIAL:
        q = pattern.sub(word, q)
    return q


def asks_next(q: str) -> bool:
    """Вопрос о следующем шаге по плану; «что делать, пока жду…» — не он."""
    q = colloquial(q)
    return any(w in q for w in NEXT_WORDS) and not any(w in q for w in WAITING_WORDS)


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
    (re.compile(r"окружени[а-яё]*"), " сервис локально "),
    (re.compile(r"(?<![а-яё])гит[а-яё]*"), " git "),
    (re.compile(r"code\s*-?\s*review|код\s*-?\s*ревью"), " code review код-ревью "),
    (re.compile(r"(?<![а-яё])(эс-?ку-?эл|скуэл|скл)(?![а-яё])"), " sql "),
    (re.compile(r"митинг[а-яё]*|созвон[а-яё]*|стендап[а-яё]*"), " встречи "),
    (re.compile(r"удален[а-яё]*|удаленк[а-яё]*|на удаленк[а-яё]*"), " удаленной работы из дома "),
)
STOP = {"который", "когда", "почему", "сделать", "нужно", "можно", "такой", "этого", "через", "после", "чтобы",
        "только", "какой", "какие", "какая", "мне", "меня", "есть", "надо", "подскажи", "пожалуйста", "расскажи",
        "такое", "такая", "такие", "этот", "этом", "если", "where", "what", "зачем", "покажи", "свой", "свое", "свою",
        "чтоб", "дали", "знаю", "хочу", "могу", "вообще", "объясни", "объясните", "новичка", "новичок", "новичку",
        "простыми", "словами", "понятно", "просто", "настроить"}
NAMES = {"intern-anya": ("аня", "ани", "аню", "анн"), "intern-ivan": ("иван", "ваня", "вани"),
         "intern-kirill": ("кирилл",), "intern-liza": ("лиза", "лизы", "лизу", "лиз")}
STATUS_RU = {"created": "создана", "pending_approval": "на согласовании", "granted": "доступ выдан", "rejected": "отклонена"}


# Короткие названия инструментов — значимые слова, хотя в них меньше четырёх букв («практикум по гиту» → Git).
SHORT_TERMS = {"git", "sql", "okr", "api", "jira"}


def _words(text: str) -> set[str]:
    words = re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е"))
    return {w for w in words if (len(w) >= 4 or w in SHORT_TERMS) and w not in STOP}


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
    if _absent_terms(question, system):  # «VPN» нет ни в одном документе — совпадение прочих слов не ответ
        return (0, "", ""), wanted, need
    # При равном совпадении: инструкция важнее определения из глоссария («**PR** — …»), затем порядок
    # поиска (документы уже отсортированы по близости), затем более содержательный абзац того же документа.
    # «Что такое CI?» — нужно определение или первый абзац о теме, а не самый длинный абзац документа.
    defining = bool(re.search(r"(что|кто) так(ое|ой|ая)|что значит|что это", question.lower()))
    best, best_key = (0, "", ""), None
    for rank, (title, content) in enumerate(_docs(system)):
        for index, (heading, unit) in enumerate(_units(content)):
            # Название документа тоже участвует: «статусы отправления в Доставке» → «Авито Доставка — статусы…».
            score = _overlap(wanted, f"{title} {heading} {unit}")
            definition = bool(re.match(r"^([-*]\s+)?\*\*", unit))
            # При равном совпадении — абзац, чей заголовок или документ про то же («статусы отправления» →
            # документ «…статусы учебного отправления», а не песочница, где слово «статус» встречается мимоходом).
            topical = _overlap(wanted, f"{title} {heading}")
            key = (score, definition if defining else not definition, topical, -rank,
                   -index if defining else len(unit))
            if best_key is None or key > best_key:
                best, best_key = (score, title, unit), key
    return best, wanted, need


TIME_WORDS = ("сколько", "срок", "когда", "как долго", "как быстро", "через какое время", "за какое время")


def docs_conflict(question: str, system: str) -> str | None:
    """SPEC 3.7 для любой модели: если найденные документы называют разные сроки, ответ — оба варианта,
    независимо от того, заметит ли расхождение модель (GigaChat на прогоне 12.11 выбирал один молча)."""
    q = question.lower()
    # «Когда дейли?» — время встречи, а не срок ожидания; «когда» считаем вопросом о сроке только про ожидание.
    if not (any(w in q for w in TIME_WORDS if w != "когда") or ("когда" in q and re.search(r"жд|ответ|приде|придё", q))):
        return None  # расхождение в сроках важно только для вопроса о сроке (иначе «один день» отгула ≠ «два дня» ревью)
    best, wanted, need = _best_unit(question, system)
    return _conflict(best, wanted, need, system) if best[0] >= need else None


def _found_text(best: tuple[int, str, str]) -> str:
    # Пункт глоссария «- **OKR** — …» → «OKR — …»: чат показывает текст как есть, без разметки.
    text = re.sub(r"^([-*]|\d+\.)\s+", "", best[2]).replace("**", "")
    fragment = text if len(text) <= 700 else text[:700].rsplit(" ", 1)[0] + "…"
    if best[1].startswith("Ответ наставника"):
        # «Память» (13.11): ответ, который наставник уже давал и добавил в базу знаний команды.
        return (f"Наставник уже отвечал на такой вопрос («{best[1]}»):\n\n{fragment}\n\n"
                "Если в твоём случае что-то иначе — спроси наставника.")
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
def says_not_found(text: str) -> bool:
    """Ответ говорит «в документах этого нет». Фраза — отдельными словами: «в плане указан» ≠ «не указан»
    (прогон GigaChat 13.11: ответ про buddy потерял источник из-за «пла-не указан»)."""
    low = text.lower().replace("ё", "е")
    return any(re.search(rf"(?<![а-яa-z]){re.escape(p)}", low) for p in MISSING_PHRASES)


def is_hr_question(q: str) -> bool:
    """Организационный вопрос — сразу к HR BP (больничный, отпуск, зарплата, ДМС…)."""
    return any(w in q for w in ORG_WORDS) or bool(SALARY.search(q))


def hr_reply(question: str) -> str:
    return (f"Это организационный вопрос — с ним лучше сразу к HR BP ({_hr_name()}): наставник на такие "
            f"вопросы не отвечает. Черновик сообщения, можно скопировать:\n\n«Здравствуйте! {_as_sentence(question)} "
            "Подскажите, пожалуйста, как это оформить.»")


# Вопросы, на которые отвечают инструменты, сводка плана или HR, а не абзац документа: страховку не применяем.
_NOT_DOC_QUESTION = ("план", "заявк", "мой наставник", "кто наставник", "кто мой", "доступ", "уровень", "навык")


def _strong(score: int, wanted: set[str]) -> bool:
    """Совпала большая часть вопроса — не два случайных слова («учебный» + «отправь» ≠ статусы отправления)."""
    return score >= min(len(wanted), max(2, -(-len(wanted) * 3 // 5)))


def _leans_on_docs(reply: str, question: str, system: str) -> bool:
    """Ответ по смыслу опирается на документ (≥4 значимых слова абзаца, кроме слов вопроса), даже без названия."""
    words = _words(reply) - _words(question)
    return any(len(words & _words(content)) >= 4 or (title and title in reply) for title, content in _docs(system))


def _absent_terms(question: str, system: str) -> set[str]:
    """Короткие латинские термины вопроса (VPN, SSO, DNS…), которых нет ни в одном найденном документе.
    Такой термин — суть вопроса, а не фон: совпадение остальных слов («работы», «дома») ответа не даёт.
    Разговорные «CI», «PR» к этому моменту уже заменены словами документов (SYNONYMS)."""
    docs = _docs(system)
    if not docs:
        return set()
    terms = set(re.findall(r"(?<![a-z])[a-z]{2,4}(?![a-z])", _normalize(question)))
    text = " ".join(f"{title} {content}" for title, content in docs).lower()
    return {t for t in terms if not re.search(rf"(?<![a-z]){t}(?![a-z])", text)}


def docs_guard(question: str, system: str, reply: str) -> str | None:
    """Страховка для любой модели (прогон GigaChat 12.11): поиск нашёл абзац, а модель говорит «этого нет» —
    показываем абзац с источником; поиск ничего не нашёл, а модель отвечает «как обычно бывает» (IT-отдел,
    портал), даже после «этого нет», — честное «в документах нет» и к кому идти. Ответ со ссылкой на документ не трогаем."""
    q = question.lower().strip()
    if THANKS.fullmatch(q) or any(q.startswith(g) for g in GREETINGS):
        return None
    if asks_next(q) or any(w in q for w in (*STUCK_WORDS, *LEVEL_WORDS, *ORG_WORDS, *ABSENCE_WORDS, *_NOT_DOC_QUESTION)):
        return None
    if _absent_terms(question, system):
        # «Как настроить VPN для работы из дома?»: абзац про удалёнку совпадает словами «работы», «дома», но о VPN
        # в найденных документах ни слова — значит, ответ модели про VPN не из документов (13.11, PR #105).
        return _missing_text(question, system)
    best, wanted, need = _best_unit(question, system)
    if len(wanted) < 2:
        return None
    low = reply.lower().replace("ё", "е")
    says_missing = says_not_found(low)
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


def _weekday(q: str, today: date) -> date | None:
    """«в понедельник» — ближайший понедельник после сегодня; «в следующий понедельник» / «на следующей неделе
    во вторник» — день следующей недели; «на следующей неделе» без дня — её понедельник."""
    next_week = bool(re.search(r"следующ\w*\s+недел|на\s+той\s+неделе", q))
    for index, form in enumerate(WEEKDAY_FORMS):
        if re.search(rf"(?<![а-яё]){form}(?![а-яё])", q):
            if next_week:
                return today + timedelta(days=7 - today.weekday() + index)
            ahead = (index - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead)
    if next_week:
        return today + timedelta(days=7 - today.weekday())
    return None


def absence_plan(q: str, today: date) -> tuple[date | None, str | None]:
    """Дата отгула из фразы и пояснение, если черновик готовить нельзя: «на 3 дня» — это отпуск (к HR BP),
    суббота и воскресенье — выходные. Возвращает (дата, None) или (None, текст ответа)."""
    q = q.lower().replace("ё", "е")
    if found := MULTI_DAY.search(q):
        count = found.group(1)
        n = int(count) if count and count.isdigit() else _WORD_NUMBERS.get(count or "", 7)
        if n != 1:
            return None, (
                "Отгул оформляется только на один день. Если нужно несколько дней подряд — это уже отпуск, его "
                f"оформляет HR BP ({_hr_name()}). Черновик сообщения, можно скопировать:\n\n«Здравствуйте! Мне нужно "
                "несколько дней отсутствия подряд. Подскажите, пожалуйста, как оформить отпуск.»\n\n"
                "Если хватит одного дня — напиши дату, и я подготовлю заявление руководителю.")
    day = _absence_day(q, today)
    if day.weekday() >= 5:
        return None, (f"{day:%d.%m} — {('суббота', 'воскресенье')[day.weekday() - 5]}, выходной: отгул не нужен. "
                      "Если имел в виду рабочий день — напиши дату, например «отгул в понедельник».")
    return day, None


def _absence_day(q: str, today: date) -> date:
    """«послезавтра», «сегодня», «14.11», «14 ноября», «в пятницу», «в следующий понедельник»; по умолчанию — завтра.
    Прошлое → завтра (задним числом нельзя)."""
    if "послезавтра" in q:
        return today + timedelta(days=2)
    if "сегодня" in q:
        return today
    if weekday := _weekday(q, today):
        return weekday
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


REMINDER_START = re.compile(r"^\s*(?:пожалуйста,?\s+|можешь\s+|а\s+)?(?:напомни(?:те)?|поставь\s+напоминани\w*|"
                            r"создай\s+напоминани\w*)(?:\s+мне)?\b", re.IGNORECASE)
_REMINDER_WHEN = re.compile(
    r"\b(?:послезавтра|завтра|сегодня)\b|\bчерез\s+(?:\d+|два|две|три|четыре|пять)?\s*(?:дн\w*|день|недел\w*)\b|"
    r"\b(?:в|во|на)\s+(?:следующ\w+\s+)?(?:%s)\b|\bна\s+следующ\w+\s+недел\w*\b|\b(?:на|к)\s+\d{1,2}\.\d{1,2}\b|"
    r"\b\d{1,2}\.\d{1,2}\b|\b\d{1,2}\s+(?:%s)\w*\b|\bутром\b|\bвечером\b|\bднём\b|\bднем\b"
    % ("|".join(WEEKDAY_FORMS), "|".join(MONTHS)), re.IGNORECASE)


def is_reminder_request(q: str) -> bool:
    """Вся просьба — напоминание себе («напомни в пятницу про 1:1»), а не «напомни наставнику»."""
    return bool(REMINDER_START.match(q)) and not re.search(r"напомни\s+(моему\s+)?наставник", q, re.IGNORECASE)


def reminder_plan(question: str, today: date) -> tuple[date | None, str]:
    """Дата и текст напоминания из фразы. «через 3 дня», «через неделю», иначе как у отгула («в пятницу», «14.11»,
    «послезавтра»; по умолчанию — завтра). Возвращает (дата, текст) или (None, ответ «о чём напомнить?»)."""
    q = question.lower().replace("ё", "е")
    if found := re.search(r"через\s+(\d+|два|две|три|четыре|пять)?\s*(дн|день|недел)", q):
        count = found.group(1)
        n = int(count) if count and count.isdigit() else _WORD_NUMBERS.get(count or "", 1)
        day = today + timedelta(days=n * (7 if found.group(2) == "недел" else 1))
    else:
        day = _absence_day(q, today)
    text = _REMINDER_WHEN.sub(" ", REMINDER_START.sub("", question, count=1))
    text = re.sub(r"\s+", " ", text).strip(" ,.:;!?—-")
    if not text or re.fullmatch(r"(?:про|о|об|что|насч[её]т|чтобы)", text, re.IGNORECASE):
        return None, ("О чём напомнить? Напиши одним сообщением, например: «напомни в пятницу про 1:1 с наставником».")
    return day, text[:300]  # «про 1:1 с наставником», «оформить пропуск» — как сказал стажёр


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
        return (f"\n\nПро «{second}»: делаю по одному действию за раз. Напиши это отдельным сообщением — "
                "поставлю напоминание.")
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
    if any(w in q for w in INJECTION_WORDS):
        return ("Так не могу: правила и права задаёт сервер, в чате их не поменять, а служебные инструкции я не "
                "показываю. Работаю от имени того, кто вошёл, и вижу только его данные. Чем помочь по стажировке? "
                "Например: «что мне делать дальше?»")
    # Только если вся просьба — напоминание («оформи доступ и напомни завтра» — две просьбы, их делит агент).
    # Стажёру напоминание ставит агент (черновик → «Подтвердить», 13.11); остальным ролям — честный отказ.
    if is_reminder_request(q) and "create_reminder" not in available:
        return ("Напоминания по просьбе я ставлю стажёрам — по их демо-дням стажировки. Тебе удобнее поставить его "
                "в рабочий календарь. За заявками и вопросами стажёров слежу сам: они приходят в колокольчик 🔔.")
    if role == "hrbp" and any(w in q for w in RANKING_WORDS):
        return ("Стажёров не сравниваю и не ранжирую. Планы и прогресс видят наставник, руководитель и куратор; "
                "HR BP в AI-buddy доступен только профиль стажёра (имя, команда, наставник). Если есть повод "
                "для беспокойства — лучше спросить наставника стажёра.")
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
    # Проверка 13.11: «отмени мой отгул» готовил черновик НОВОГО отгула. Отмены в сервисах нет — говорим честно.
    if role == "intern" and any(w in q for w in CANCEL_WORDS) and any(w in q for w in CANCEL_OBJECTS):
        lead = re.search(r"Руководитель: ([^.]+)\.", system)
        mentor = re.search(r"Наставник: ([^.]+)\.", system)
        return ("Отправленную заявку из чата не отменяю. Если это ещё черновик — нажми «Отменить» на его карточке: "
                "без «Подтвердить» он никуда не ушёл. Если уже отправлено — напиши тому, кто решает: заявление на "
                f"отгул — руководителю ({lead.group(1) if lead else 'руководитель команды'}), заявку на доступ — "
                f"наставнику ({mentor.group(1) if mentor else 'твой наставник'}).")
    # Уровень меняет только наставник — в своём кабинете (проверка 13.11: GigaChat отвечал наставнику «обсудите
    # с наставником»).
    if any(w in q for w in LEVEL_CHANGE) and "уров" in q:
        if role == "mentor":
            return ("Уровень ставишь ты: в карточке стажёра блок «Уровень по темам» — выбери новый уровень, и "
                    "персональные пункты плана пересоберутся сами. Сам я уровни не меняю: только предлагаю, "
                    "когда стажёр закрыл пункты темы, — решаешь ты.")
        if role == "intern":
            return ("Уровень по темам ставит наставник — я его не меняю. Если тема тебе уже знакома, нажми «Это я "
                    "уже знаю» у пункта в плане: наставник получит предложение и решит одной кнопкой.")
        return "Уровень по темам ставит только наставник стажёра."
    if any(w in q for w in ("сравн", "сопостав")) and _names_someone(q):
        if role == "mentor":
            return ("Сравнение планов — на твоём экране, блок «Сравнить планы»: общие пункты у стажёров одинаковые, "
                    "персональные подобраны по карте навыков. Это не рейтинг: кто лучше, я не оцениваю.")
        return "Стажёров не сравниваю и не ранжирую. Планы своих стажёров рядом видит только их наставник."
    if role in ("mentor", "lead") and any(w in q for w in ("отгул", "отсутств")) and \
            any(w in q for w in ("почему", "причин", "зачем")):
        where = ("Причина — в заявлении, в блоке «Заявки на отгул» на твоём экране." if role == "lead" else
                 "Наставник видит только дату отсутствия (она в карточке стажёра), причину — руководитель.")
        return f"Причину отгула в чате не раскрываю. {where}"
    return None


_SENTENCE = re.compile(r"[^.!?\n]*[.!?]?")
_QUOTED = re.compile(r"«([^»]{3,80})»")


def scrub_reply(text: str, tool_names: set[str], doc_titles: set[str]) -> str:
    """Убрать из ответа модели то, что стажёру видеть нельзя или что выдумано (прогон 12.11 на Railway):
    имена внутренних инструментов («вызови инструмент: create_absence_request») и ссылку на документ, которого
    нет среди найденных («в документах это называется «Практика CI/CD»»). Убираем предложение целиком."""
    def bad(sentence: str) -> bool:
        low = sentence.lower()
        if any(name in sentence for name in tool_names) or "инструмент:" in low or "вызови инструмент" in low:
            return True
        if "документ" in low:
            return any(t not in doc_titles for t in _QUOTED.findall(sentence))
        return False
    lines = []
    for line in text.split("\n"):
        kept = "".join(s for s in _SENTENCE.findall(line) if s and not bad(s))
        lines.append(kept.rstrip() if kept.strip() else ("" if line.strip() else line))
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned or text


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
                day, note = absence_plan(q, today)
                if note:
                    return LLMReply(content=note)
                return call("create_absence_request", {"day": day.isoformat(), "reason": _reason(q)})
        if "get_plan" in available and role == "intern" and (
                any(w in q for w in EMOTION_WORDS) or any(w in q for w in MARK_DONE)):
            return call("get_plan")
        if role == "lead" and "заявк" in q and "list_absence_requests" in available:
            return call("list_absence_requests")
        if is_hr_question(q):
            return LLMReply(content=hr_reply(question))
        if "план" in q or any(w in q for w in STUCK_WORDS):
            if someone and "get_plan" in available:
                return call("get_plan", {"intern_id": someone})
            if other:
                return LLMReply(content="У тебя нет доступа к планам стажёров — подробности не раскрываю.")
        if asks_next(q) and "get_plan" in available:
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
        q = question.lower()
        if msg.name == "get_plan" and any(w in q for w in MARK_DONE):
            return self._mark_done(result, question, available)
        handler = {
            "get_plan": lambda r: self._plan(r, own=not _names_someone(q), calm=any(w in q for w in EMOTION_WORDS)),
            "list_access_resources": lambda r: self._pick_resource(r, question, available),
            "list_access_requests": lambda r: self._requests(r, question, system),
            "list_absence_requests": lambda r: self._absences(r),
            "get_skill_profile": self._levels,
        }.get(msg.name or "")
        return handler(result) if handler else LLMReply(content="Готово, данные сервиса получены.")

    def _mark_done(self, plan: dict, question: str, available: set[str]) -> LLMReply:
        """«Отметь, что я прошла практикум по Git» → черновик отметки «сделано» у самого похожего своего пункта."""
        wanted = _query_words(question) - {"отметь", "прошла", "прошел", "сделала", "сделал", "закончила", "закончил",
                                           "закрыла", "закрыл", "уже"}
        mine = [i for i in plan.get("items") or [] if i.get("owner_role") == "intern" and i.get("status") != "done"]
        scored = sorted(((_overlap(wanted, i["title"]), i) for i in mine), key=lambda p: -p[0])
        if not scored or scored[0][0] == 0 or "set_plan_item_status" not in available:
            open_items = ", ".join(f"«{i['title']}»" for i in mine[:4]) or "—"
            return LLMReply(content=("Не понял, какой пункт отметить. Твои незакрытые пункты: "
                                     f"{open_items}. Напиши название или нажми «Готово» у пункта в плане слева."))
        item = scored[0][1]
        if item.get("resource_id"):
            return LLMReply(content=(f"Пункт «{item['title']}» закрывается заявкой на доступ, а не отметкой: нажми у "
                                     "него «Сделать за меня» — подготовлю черновик заявки."))
        return LLMReply(tool_calls=[ToolCall(id="scn_set_plan_item_status", name="set_plan_item_status",
                                             arguments={"item_id": item["id"], "status": "done",
                                                        "title": item["title"]})])

    def _absences(self, result: dict) -> LLMReply:
        reasons = {"personal": "личные дела", "family": "семейные дела", "study": "учебные дела"}
        reqs = result.get("requests") or []
        pending = [r for r in reqs if r.get("status") in ("pending", "submitted", "created")]
        if not pending:
            return LLMReply(content="Сейчас ничего не ждёт твоего решения: новых заявлений на отгул нет. "
                                    "Когда стажёр подаст заявление, оно появится в колокольчике 🔔 и в блоке «Заявки на отгул».")
        lines = [f"• {_name(r.get('intern_id'))} — {date.fromisoformat(r['day']):%d.%m}, "
                 f"{reasons.get(r.get('reason'), r.get('reason'))}" for r in pending]
        return LLMReply(content="Ждут твоего решения — заявления на отгул:\n" + "\n".join(lines) +
                                "\n\nРешить можно в блоке «Заявки на отгул» слева: «Согласовать» или «Отклонить».")

    def _levels(self, profile: dict) -> LLMReply:
        names = {"novice": "новичок", "familiar": "знаком", "confident": "уверенно"}
        titles = {"ci": "CI", "git": "Git", "sql": "SQL"}
        skills = ", ".join(f"{titles.get(k, k)} — {names.get(v, v)}" for k, v in (profile.get("skills") or {}).items())
        first = _name(profile.get("intern_id")).split()[0]
        return LLMReply(content=(f"{first}, уровень по темам: {skills or 'пока не заполнен'}. Уровень меняет только "
                                 "наставник; бот по нему подстраивает глубину объяснений."))

    def _plan(self, plan: dict, own: bool = True, calm: bool = False) -> LLMReply:
        day = plan.get("current_day")
        first = _name(plan.get("intern_id")).split()[0]
        lines = [f"Сейчас {day}-й день стажировки." if own else f"{first}: {day}-й день стажировки."]
        items = plan.get("items") or []
        done = sum(1 for i in items if i.get("status") == "done")
        if own and items:
            left = 14 - int(day or 0)
            tail = f", до конца недель 1–2 — {_days(left)}" if left > 0 else ""
            lines.append(f"Недели 1–2: закрыто {done} из {len(items)}{tail}.")
        elif items:
            lines.append(f"Недели 1–2: закрыто {done} из {len(items)}.")
        if calm:
            lines.insert(0, "Понимаю, в первые недели так бывает у многих — это нормально. Не нужно делать всё сразу, "
                            "давай по одному шагу.")
        step = plan.get("next_step")
        if step:
            late = " Срок уже прошёл — лучше заняться им первым." if step.get("overdue") else ""
            # Наставнику и руководителю следующий шаг — их собственный пункт в плане стажёра (проверка 13.11).
            lines.append(f"{'Следующий шаг' if own else 'Твой следующий шаг в этом плане'} — «{step['title']}».{late}")
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
        # Чужой план: «закрыты» — только если закрыты все пункты (проверка 13.11: куратору на 2-й день Ани
        # писали «пункты закрыты» при 1 из 12 — у куратора просто нет своих пунктов).
        if own and not step and not plan.get("waiting"):
            lines.append("Свои пункты недель 1–2 закрыты — дальше «Месяц 1».")
        elif not own and items and done == len(items):
            lines.append("Недели 1–2 закрыты — дальше «Месяц 1».")
        if calm:
            lines.append("Если задач слишком много — покажи список наставнику и попросите вместе выбрать главное: "
                         "приоритет определяет команда, а не стажёр в одиночку (документ «Как приоритизировать "
                         "задачи»). Застрял(а) — пиши наставнику сразу, ждать встречи 1:1 не нужно.")
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
        elif any(w in q for w in ("bitbucket", "битбакет", "пространств", "репозитор", "команд", "гит", "git")):
            match = next((r for r in resources if r.get("kind") == "team_space"), None)
        if match and "create_access_request" in available:
            # Обоснование — по делу, а не текст вопроса («Нужно для стажировки: как получить доступ к джире», проверка 13.11).
            justification = f"Для учебных задач стажировки: {match['title']}"[:300]
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
