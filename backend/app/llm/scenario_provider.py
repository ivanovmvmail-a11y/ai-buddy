"""Сценарный режим без ключа модели (спека 003).

Тот же интерфейс, что у GigaChat: может попросить вызвать инструмент и отвечает текстом. Намерение —
по ключевым словам вопроса, ответ — только из результатов инструментов и фрагментов документов,
которые агент уже положил в системное сообщение. Ничего не выдумывает: нет данных — так и говорит.

Права, черновики и отказы обеспечивает агент (`ToolExecutor`), поэтому режим доказывает, что механика
работает независимо от модели.
"""
import json
import re
from typing import Any

from app.agent.users import DEMO_USERS, Role

from .base import LLMReply, Message, ToolCall, ToolSpec

DOCS_MARKER = "Контекст из документов команды"

ORG_WORDS = ("отпуск", "больнич", "отгул", "зарплат", "компенсац", "справк", "дмс", "увольн", "трудов", "командиров")
NEXT_WORDS = ("дальше", "следующ", "что мне делать", "кого жд", "кого я жд", "мой план", "что у меня")
ACCESS_VERBS = ("оформ", "запрос", "получ", "дай", "нужен", "нужн", "сделай", "подай", "закажи", "выдай", "открой")
REQUEST_WORDS = ("мои", "статус", "какие", "ждут", "список", "покажи")
GREETINGS = ("привет", "здравствуй", "добрый день", "хай", "hello")
THANKS = re.compile(r"(спасибо|благодарю|спс|понятно|понял[а]?|ясно|ок|окей|отлично|супер)"
                    r"(\s+(тебе|большое|огромное|всё|все))*[\s!.,)]*")
STUCK_WORDS = ("завис", "жд", "просроч", "как дела", "как у", "прогресс", "успева", "застрял")
LEVEL_WORDS = ("мой уровень", "уровень по", "какой у меня уровень", "что я знаю", "мои навыки", "карта навыков")
STOP = {"который", "когда", "почему", "сделать", "нужно", "можно", "такой", "этого", "через", "после", "чтобы",
        "только", "какой", "какие", "какая", "мне", "меня", "есть", "надо", "подскажи", "пожалуйста", "расскажи",
        "такое", "такая", "такие", "этот", "этом", "where", "what"}
NAMES = {"intern-anya": ("аня", "ани", "аню", "анн"), "intern-ivan": ("иван", "ваня", "вани")}
STATUS_RU = {"created": "создана", "pending_approval": "на согласовании", "granted": "доступ выдан", "rejected": "отклонена"}


def _words(text: str) -> set[str]:
    words = re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е"))
    return {w for w in words if len(w) >= 4 and w not in STOP}


def _same(a: str, b: str) -> bool:
    """Одно слово в разных формах: «доставки» = «доставка», но «доставки» ≠ «достаточно»."""
    if a == b:
        return True
    common = len(next((a[:i] for i in range(min(len(a), len(b)), 0, -1) if a[:i] == b[:i]), ""))
    shortest = min(len(a), len(b))
    return common >= 6 or (shortest <= 5 and common >= shortest - 1)


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


def _hr_name() -> str:
    return next((u.name for u in DEMO_USERS.values() if u.role == Role.HRBP), "HR BP")


class ScenarioProvider:
    name = "scenario"

    async def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None) -> LLMReply:
        system = next((m.content for m in messages if m.role == "system"), "")
        question = next((m.content for m in reversed(messages) if m.role == "user"), "").strip()
        available = {t.name for t in tools or []}
        last = messages[-1] if messages else None
        if last is not None and last.role == "tool":
            return self._after_tool(last, question, available, system)
        return self._first_step(question.lower(), question, available, system)

    # --- первый шаг: что спросили ---------------------------------------------------------------

    def _first_step(self, q: str, question: str, available: set[str], system: str) -> LLMReply:
        def call(name: str, args: dict[str, Any] | None = None) -> LLMReply:
            return LLMReply(tool_calls=[ToolCall(id=f"scn_{name}", name=name, arguments=args or {})])

        if THANKS.fullmatch(q):
            return LLMReply(content="Пожалуйста! Если появится вопрос — спрашивай. Следующий шаг всегда виден в плане слева.")
        if "наставник" in q and any(w in q for w in ("кто", "мой", "моего", "как зовут", "связат", "написать")):
            mentor = re.search(r"Наставник: ([^.]+)\.", system)
            if mentor:
                return LLMReply(content=(
                    f"Твой наставник — {mentor.group(1)}. К нему — вопросы по задачам и всё, что блокирует работу; "
                    "если работа встала, пиши сразу, ждать встречи 1:1 не нужно."))
        if any(w in q for w in LEVEL_WORDS):
            levels = re.search(r"Уровень по темам: (.+?)\.(\s|$)", system)
            if levels:
                return LLMReply(content=(
                    f"По профилю: {levels.group(1)}. Уровень ставит наставник; я использую его только чтобы "
                    "объяснять подробнее или короче, а не для оценки."))
        if any(w in q for w in ORG_WORDS):
            return LLMReply(content=(
                f"Это организационный вопрос — с ним лучше сразу к HR BP ({_hr_name()}): наставник на такие "
                f"вопросы не отвечает. Черновик сообщения, можно скопировать:\n\n«Здравствуйте! {question} "
                "Подскажите, пожалуйста, как это оформить.»"))
        if ("план" in q or any(w in q for w in STUCK_WORDS)) and "get_plan" in available:
            for intern_id, forms in NAMES.items():
                if any(re.search(rf"\b{f}", q) for f in forms):
                    return call("get_plan", {"intern_id": intern_id})
        if any(w in q for w in NEXT_WORDS) and "get_plan" in available:
            return call("get_plan")
        if "доступ" in q and any(v in q for v in ACCESS_VERBS) and "list_access_resources" in available:
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
        wanted = _words(question)
        # Поиск без ключа всегда отдаёт top-k, поэтому порог свой: совпасть должны хотя бы 2 основы слов
        # (или единственная, если в вопросе одно значимое слово) — иначе честно «в базе нет».
        need = min(2, len(wanted)) or 1
        # При равном совпадении: инструкция важнее определения из глоссария («**PR** — …»), затем порядок
        # поиска (документы уже отсортированы по близости), затем более содержательный абзац того же документа.
        best, best_key = (0, "", ""), None
        for rank, (title, content) in enumerate(_docs(system)):
            for heading, unit in _units(content):
                score = _overlap(wanted, heading + " " + unit)
                definition = bool(re.match(r"^([-*]\s+)?\*\*", unit))
                key = (score, not definition, -rank, len(unit))
                if best_key is None or key > best_key:
                    best, best_key = (score, title, unit), key
        if best[0] >= need and (conflict := _conflict(best, wanted, need, system)):
            return conflict
        if best[0] >= need:
            fragment = best[2] if len(best[2]) <= 700 else best[2][:700].rsplit(" ", 1)[0] + "…"
            return f"Нашёл в документе «{best[1]}»:\n\n{fragment}\n\nЕсли что-то непонятно — спроси, разберём по шагам."
        who = "твой наставник" if _role(system) == "intern" else "коллеги из команды"
        return (
            "В документах, доступных тебе, этого нет — выдумывать не буду. Скорее всего подскажет "
            f"{who}. Черновик вопроса, можно скопировать:\n\n«Привет! Подскажи, пожалуйста: {question} "
            "Я поискал в документах команды, но ответа не нашёл.»")

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
        if result.get("status") == "awaiting_confirmation":
            return LLMReply(content=f"Подготовил черновик: {result.get('summary')}. Проверь и нажми «Подтвердить» — "
                                    "без этого ничего не отправится.")
        handler = {
            "get_plan": lambda r: self._plan(r, own=not _names_someone(question.lower())),
            "list_access_resources": lambda r: self._pick_resource(r, question, available),
            "list_access_requests": self._requests,
        }.get(msg.name or "")
        return handler(result) if handler else LLMReply(content="Готово, данные сервиса получены.")

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
        elif any(w in q for w in ("bitbucket", "битбакет", "пространств", "репозитор", "команд")):
            match = next((r for r in resources if r.get("kind") == "team_space"), None)
        if match and "create_access_request" in available:
            justification = f"Нужно для стажировки: {question}"[:300]
            return LLMReply(tool_calls=[ToolCall(id="scn_create_access_request", name="create_access_request",
                                                 arguments={"resource_id": match["id"], "level": "read",
                                                            "justification": justification})])
        titles = ", ".join(r["title"] for r in resources) or "—"
        return LLMReply(content=f"Уточни, какой доступ нужен: {titles}.")

    def _requests(self, result: dict) -> LLMReply:
        reqs = result.get("requests") or []
        if not reqs:
            return LLMReply(content="Заявок нет.")
        lines = [f"{r['id']} — {r['resource_id']}, {_name(r['intern_id'])}: {STATUS_RU.get(r['status'], r['status'])}"
                 for r in reqs]
        return LLMReply(content="Заявки:\n" + "\n".join(lines))
