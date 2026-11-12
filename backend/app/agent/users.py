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


# Права — строки «ресурс:действие». Решают, какие инструменты показать модели; точную проверку
# (свой стажёр, свой пункт, назначенный согласующий) делают имитации сервисов в app/mcp_server.
_BASE = frozenset({"profile:read", "reminders:write"})
ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.INTERN: _BASE | {"plan:read", "plan:write", "access:request", "access:read", "skills:read",
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
             mentor_id="mentor-petr", lead_id="lead-olga"),
        User(id="intern-ivan", name="Иван Кузнецов", role=Role.INTERN, team="Авито Доставка",
             mentor_id="mentor-maria", lead_id="lead-sergey"),
        # Вторые стажёры у наставников — для экрана сравнения планов (SPEC 3.1, 5; решение 11.11).
        User(id="intern-kirill", name="Кирилл Егоров", role=Role.INTERN, team="Платформа объявлений",
             mentor_id="mentor-petr", lead_id="lead-olga"),
        User(id="intern-liza", name="Лиза Ковалёва", role=Role.INTERN, team="Авито Доставка",
             mentor_id="mentor-maria", lead_id="lead-sergey"),
        User(id="mentor-petr", name="Пётр Волков", role=Role.MENTOR, team="Платформа объявлений", lead_id="lead-olga"),
        User(id="mentor-maria", name="Мария Орлова", role=Role.MENTOR, team="Авито Доставка", lead_id="lead-sergey"),
        User(id="lead-olga", name="Ольга Новикова", role=Role.LEAD, team="Платформа объявлений"),
        User(id="lead-sergey", name="Сергей Лебедев", role=Role.LEAD, team="Авито Доставка"),
        User(id="hrbp-elena", name="Елена Морозова", role=Role.HRBP, team="HR"),
        User(id="curator-dmitry", name="Дмитрий Соколов", role=Role.CURATOR, team="Avito Start"),
    ]
}

DEFAULT_USER_ID = "intern-anya"


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
