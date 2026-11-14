"""Поток событий в Apache Kafka (спека 304).

ТЗ: в инфраструктуре Авито есть Clickstream и Kafka. События продукта (вопрос задан, заявка создана, задание сдано…)
по-прежнему пишутся в таблицу `events` — это источник для Grafana. После успешной записи те же события уходят в Kafka,
в топик `KAFKA_TOPIC`, — так их в Авито забрал бы Clickstream. В событиях нет текстов вопросов и ответов.

Kafka не должна мешать работе: отправка идёт в фоновом потоке через очередь в памяти; брокер недоступен или медленный —
запрос пользователя этого не замечает, событие остаётся в таблице, а здесь после трёх попыток считается пропущенным.
`KAFKA_BOOTSTRAP` пуст (тесты, облако без Kafka) — модуль ничего не делает.
"""
import json
import logging
import queue
import threading
import time

from app.config import settings

log = logging.getLogger("ai_buddy.event_stream")

QUEUE_SIZE = 1000
ATTEMPTS = 3
RETRY_SECONDS = 5.0

_queue: "queue.Queue[dict]" = queue.Queue(maxsize=QUEUE_SIZE)
_stats = {"sent": 0, "dropped": 0}
_producer = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def enabled() -> bool:
    return bool(settings.kafka_bootstrap)


def topic() -> str:
    return settings.kafka_topic or "ai-buddy.events"


def to_message(event) -> dict:
    """Событие сервиса → сообщение для Clickstream: тот же состав, что в таблице `events`."""
    return {"event": event.type, "ts": event.ts.isoformat(), "user_id": event.user_id, "role": str(event.role),
            "team": event.team, "payload": event.payload, "source": "ai-buddy"}


def publish(events) -> None:
    """Поставить события в очередь на отправку. Не блокирует и не бросает исключений."""
    if not events or not enabled():
        return
    for event in events:
        try:
            _queue.put_nowait(to_message(event))
        except queue.Full:
            _stats["dropped"] += 1
        except Exception as error:  # noqa: BLE001 — поток событий не должен ронять бизнес-операцию
            log.warning("event stream: skipped event (%s)", type(error).__name__)
            _stats["dropped"] += 1
    _ensure_worker()


def _ensure_worker() -> None:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_work, name="event-stream", daemon=True)
            _thread.start()


def _make_producer():
    from kafka import KafkaProducer  # импорт здесь: без KAFKA_BOOTSTRAP пакет не нужен

    return KafkaProducer(
        bootstrap_servers=[s.strip() for s in settings.kafka_bootstrap.split(",") if s.strip()],
        client_id="ai-buddy", acks=1, retries=0, request_timeout_ms=5000, max_block_ms=5000,
        value_serializer=lambda value: json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"),
        key_serializer=lambda key: key.encode("utf-8"))


def _send(message: dict) -> None:
    global _producer
    if _producer is None:
        _producer = _make_producer()
    _producer.send(topic(), key=message["user_id"], value=message).get(timeout=10)


def _work() -> None:
    global _producer
    while True:
        message = _queue.get()
        try:
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    _send(message)
                    _stats["sent"] += 1
                    break
                except Exception as error:  # noqa: BLE001 — брокер недоступен: пробуем позже, не шумим в журнале
                    _producer = None
                    if attempt == ATTEMPTS:
                        _stats["dropped"] += 1
                        log.warning("event stream: Kafka unavailable (%s), event stays only in the table",
                                    type(error).__name__)
                    else:
                        time.sleep(RETRY_SECONDS)
        finally:
            _queue.task_done()


def flush(timeout: float = 5.0) -> bool:
    """Дождаться отправки очереди (тесты и корректное завершение). True — очередь пуста."""
    deadline = time.monotonic() + timeout
    while _queue.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.01)
    return not _queue.unfinished_tasks


def status() -> dict:
    return {"enabled": enabled(), "topic": topic() if enabled() else None,
            "connected": _producer is not None, "queued": _queue.qsize(), **_stats}
