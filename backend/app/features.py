"""Feature flags: включить или выключить функцию без правки кода (спека 006).

ТЗ: в Авито есть feature flags — compile-time и runtime. Здесь оба вида:
  - при запуске: переменная `FEATURE_FLAGS="quick_access=off,memory_recall=off"` (как compile-time: задаётся сборкой/стендом);
  - на ходу: `POST /features` меняет флаг без перезапуска. Значение лежит в Redis (`REDIS_URL`, в Docker — служба `redis`),
    поэтому его видят все процессы backend. Без Redis (тесты, облако без Redis) — в памяти процесса.
Redis недоступен — не ошибка: работаем по значениям запуска. Флаг — не право доступа: права проверяет сервер отдельно.
"""
import logging
import time

from app.config import settings

log = logging.getLogger("ai_buddy.features")

# имя → (значение по умолчанию, что делает)
FLAGS: dict[str, tuple[bool, str]] = {
    "quick_access": (True, "«Сделать за меня»: простой доступ на чтение выдаётся в один клик, без черновика"),
    "memory_recall": (True, "«Память»: если в документах нет ответа, модель сверяет вопрос с уже отвеченными "
                            "вопросами команды — находит ответ наставника и на перефразированный вопрос"),
    "practice_by_meaning": (True, "Практикум: факт, не найденный по ключевым словам, модель проверяет по смыслу"),
    "example_guard": (True, "Из ответа модели убираются примеры, команды и «в Авито…», которых нет в документах"),
}
REDIS_KEY = "ai-buddy:features"
CACHE_SECONDS = 2.0

_local: dict[str, bool] = {}  # изменения на ходу, когда Redis нет
_cache: tuple[float, dict[str, bool]] | None = None
_redis = None
_redis_failed_at = 0.0


def _parse(raw: str) -> dict[str, bool]:
    """`a=off,b=on` → {"a": False, "b": True}; неизвестные имена и мусор пропускаем."""
    out = {}
    for part in raw.split(","):
        name, _, value = part.strip().partition("=")
        if name in FLAGS and value.strip().lower() in ("on", "off", "true", "false", "1", "0"):
            out[name] = value.strip().lower() in ("on", "true", "1")
    return out


def _client():
    """Клиент Redis или None. После сбоя 30 секунд не пробуем снова — запрос чата не должен ждать Redis."""
    global _redis, _redis_failed_at
    if not settings.redis_url or time.monotonic() - _redis_failed_at < 30:
        return None
    if _redis is None:
        try:
            import redis  # необязательная зависимость во время работы: без пакета — как без Redis
            _redis = redis.Redis.from_url(settings.redis_url, socket_timeout=0.3, socket_connect_timeout=0.3,
                                          decode_responses=True)
        except Exception as error:  # noqa: BLE001 — любой сбой Redis = работаем без него
            log.warning("feature flags: Redis unavailable (%s), using startup values", type(error).__name__)
            _redis_failed_at = time.monotonic()
            return None
    return _redis


def _runtime() -> tuple[dict[str, bool], str]:
    global _cache, _redis_failed_at
    client = _client()
    if client is None:
        return dict(_local), "memory"
    now = time.monotonic()
    if _cache and now - _cache[0] < CACHE_SECONDS:
        return _cache[1], "redis"
    try:
        stored = {k: v == "1" for k, v in client.hgetall(REDIS_KEY).items() if k in FLAGS}
    except Exception as error:  # noqa: BLE001
        log.warning("feature flags: Redis read failed (%s), using startup values", type(error).__name__)
        _redis_failed_at = now
        return dict(_local), "memory"
    _cache = (now, stored)
    return stored, "redis"


def all_flags() -> dict:
    """Все флаги с описанием и тем, откуда взято значение: default → env → runtime."""
    startup = _parse(settings.feature_flags)
    runtime, store = _runtime()
    flags = []
    for name, (default, about) in FLAGS.items():
        value, source = default, "default"
        if name in startup:
            value, source = startup[name], "env"
        if name in runtime:
            value, source = runtime[name], "runtime"
        flags.append({"name": name, "enabled": value, "source": source, "description": about})
    return {"flags": flags, "store": store}


def enabled(name: str) -> bool:
    runtime, _ = _runtime()
    if name in runtime:
        return runtime[name]
    return _parse(settings.feature_flags).get(name, FLAGS[name][0])


def set_flag(name: str, value: bool) -> None:
    """Переключить на ходу. KeyError — такого флага нет."""
    global _cache, _redis_failed_at
    if name not in FLAGS:
        raise KeyError(name)
    _local[name] = value
    client = _client()
    if client is not None:
        try:
            client.hset(REDIS_KEY, name, "1" if value else "0")
            _cache = None
        except Exception as error:  # noqa: BLE001
            log.warning("feature flags: Redis write failed (%s), kept in memory", type(error).__name__)
            _redis_failed_at = time.monotonic()


def reset() -> None:
    """Вернуть значения запуска («Сброс» в демо-панели и тесты)."""
    global _cache
    _local.clear()
    _cache = None
    client = _client()
    if client is not None:
        try:
            client.delete(REDIS_KEY)
        except Exception:  # noqa: BLE001
            pass
