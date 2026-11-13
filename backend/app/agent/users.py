"""Пользователи и роли — ИМИТАЦИЯ.

В Авито авторизация и ролевая модель уже есть (ТЗ, «Пространство решений»). В прототипе их заменяет
этот модуль: набор синтетических пользователей и права по ролям. При внедрении `get_user()` и
`ROLE_PERMISSIONS` подменяются вызовами корпоративной авторизации — остальной код агента не меняется.
"""
from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    INTERN = "intern"  # стажёр
    MENTOR = "mentor"  # наставник (buddy)
    LEAD = "lead"  # руководитель команды
    HRBP = "hrbp"  # HR BP
    CURATOR = "curator"  # куратор стажировки


class User(BaseModel):
    id: str
    name: str
    role: Role
    team: str
    mentor_id: str | None = None  # для стажёра — его наставник
    lead_id: str | None = None  # руководитель команды
    female: bool = False  # для согласования: «ответила», «поискала»
    # Падежи имени: родительный (у кого), дательный (кому), творительный (с кем). Модель склоняет имена с ошибками
    # («к наставнику Петра Волкова», проверка 13.11) — даём ей готовые формы, сервер тоже берёт их отсюда.
    forms: tuple[str, str, str] | None = None


# Права — строки «ресурс:действие». Решают, какие инструменты показать модели; точную проверку
# (свой стажёр, свой пункт, назначенный согласующий) делают имитации сервисов в app/mcp_server.
_BASE = frozenset({"profile:read"})
ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.INTERN: _BASE | {"reminders:write", "plan:read", "plan:write", "access:request", "access:read", "skills:read",
                          "absence:request", "absence:read"},
    Role.MENTOR: _BASE | {"interns:read", "plan:read", "plan:write", "access:read", "access:approve", "skills:read"},
    Role.LEAD: _BASE | {"interns:read", "plan:read", "plan:write", "absence:read"},
    Role.HRBP: _BASE | {"interns:read"},
    Role.CURATOR: _BASE | {"interns:read", "plan:read"},
}

# Синтетические данные (ТЗ: реальные данные сотрудников не используем).
DEMO_USERS: dict[str, User] = {
    u.id: u
    for u in [
        User(id="intern-anya", name="Аня Смирнова", role=Role.INTERN, team="Платформа объявлений",
             mentor_id="mentor-petr", lead_id="lead-olga",
             forms=("Ани Смирновой", "Ане Смирновой", "Аней Смирновой"), female=True),
        User(id="intern-ivan", name="Иван Кузнецов", role=Role.INTERN, team="Авито Доставка",
             mentor_id="mentor-maria", lead_id="lead-sergey",
             forms=("Ивана Кузнецова", "Ивану Кузнецову", "Иваном Кузнецовым")),
        # Вторые стажёры у наставников — для экрана сравнения планов (SPEC 3.1, 5; решение 11.11).
        User(id="intern-kirill", name="Кирилл Егоров", role=Role.INTERN, team="Платформа объявлений",
             mentor_id="mentor-petr", lead_id="lead-olga",
             forms=("Кирилла Егорова", "Кириллу Егорову", "Кириллом Егоровым")),
        User(id="intern-liza", name="Лиза Ковалёва", role=Role.INTERN, team="Авито Доставка",
             mentor_id="mentor-maria", lead_id="lead-sergey",
             forms=("Лизы Ковалёвой", "Лизе Ковалёвой", "Лизой Ковалёвой"), female=True),
        User(id="mentor-petr", name="Пётр Волков", role=Role.MENTOR, team="Платформа объявлений", lead_id="lead-olga",
             forms=("Петра Волкова", "Петру Волкову", "Петром Волковым")),
        User(id="mentor-maria", name="Мария Орлова", role=Role.MENTOR, team="Авито Доставка", lead_id="lead-sergey",
             forms=("Марии Орловой", "Марии Орловой", "Марией Орловой"), female=True),
        User(id="lead-olga", name="Ольга Новикова", role=Role.LEAD, team="Платформа объявлений",
             forms=("Ольги Новиковой", "Ольге Новиковой", "Ольгой Новиковой"), female=True),
        User(id="lead-sergey", name="Сергей Лебедев", role=Role.LEAD, team="Авито Доставка",
             forms=("Сергея Лебедева", "Сергею Лебедеву", "Сергеем Лебедевым")),
        User(id="hrbp-elena", name="Елена Морозова", role=Role.HRBP, team="HR",
             forms=("Елены Морозовой", "Елене Морозовой", "Еленой Морозовой"), female=True),
        User(id="curator-dmitry", name="Дмитрий Соколов", role=Role.CURATOR, team="Avito Start",
             forms=("Дмитрия Соколова", "Дмитрию Соколову", "Дмитрием Соколовым")),
    ]
}

DEFAULT_USER_ID = "intern-anya"

CASES = {"gen": 0, "dat": 1, "ins": 2}


def name_in(user: User | None, case: str, fallback: str = "") -> str:
    """Имя в падеже: name_in(petr, "dat") → «Петру Волкову». Без готовой формы — именительный."""
    if user is None:
        return fallback
    return user.forms[CASES[case]] if user.forms else user.name


def by_gender(user: User | None, masc: str, fem: str) -> str:
    """«ответил» / «ответила» по человеку; неизвестный человек — мужская форма, как в общих шаблонах."""
    return fem if user is not None and user.female else masc


def find_by_name(name: str) -> User | None:
    return next((u for u in DEMO_USERS.values() if u.name == name), None)


def get_user(user_id: str | None) -> User | None:
    """Текущий пользователь по id из имитации входа. Пустой или неизвестный id → None (401, аудит D8)."""
    return DEMO_USERS.get(user_id) if user_id else None


def has_permission(user: User, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def can_view_intern(viewer: User, intern: User) -> bool:
    """Чужие данные стажёра видят только его наставник, руководитель, HR BP и куратор."""
    if viewer.id == intern.id:
        return True
    if viewer.role == Role.MENTOR:
        return intern.mentor_id == viewer.id
    if viewer.role == Role.LEAD:
        return intern.lead_id == viewer.id
    return viewer.role in (Role.HRBP, Role.CURATOR)
