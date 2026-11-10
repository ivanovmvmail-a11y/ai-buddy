"""Единственный системный субъект; не десериализуется из пользовательского JSON."""

from .errors import Forbidden
from .models import Actor, SystemActor

SYSTEM_ACTOR = SystemActor()


def require_system(actor: Actor):
    # Только внутренний singleton; одинаковый id/role в JSON не даёт системных прав.
    if actor is not SYSTEM_ACTOR:
        raise Forbidden("Операция доступна только системе")
