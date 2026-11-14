"""Спека 304: события продукта дублируются в Apache Kafka, и Kafka не может помешать работе."""
import asyncio
from datetime import datetime, timezone

import pytest

from .conftest import as_user

from app import event_stream
from app.config import settings
from app.mcp_server import storage
from app.mcp_server.models import Event
from app.mcp_server.seed import load_seed


class FakeFuture:
    def __init__(self, error=None):
        self.error = error

    def get(self, timeout=None):
        if self.error:
            raise self.error


class FakeProducer:
    def __init__(self, fail=0):
        self.sent, self.fail = [], fail

    def send(self, topic, key=None, value=None):
        if self.fail:
            self.fail -= 1
            return FakeFuture(ConnectionError("брокер недоступен"))
        self.sent.append((topic, key, value))
        return FakeFuture()


@pytest.fixture
def stream(monkeypatch):
    """Поток включён, вместо брокера — поддельный продюсер; повтор без ожидания."""
    monkeypatch.setattr(settings, "kafka_bootstrap", "kafka.invalid:9092")
    monkeypatch.setattr(settings, "kafka_topic", "")
    monkeypatch.setattr(event_stream, "RETRY_SECONDS", 0)
    monkeypatch.setattr(event_stream, "_stats", {"sent": 0, "dropped": 0})
    producer = FakeProducer()
    monkeypatch.setattr(event_stream, "_producer", None)
    monkeypatch.setattr(event_stream, "_make_producer", lambda: producer)
    yield producer
    event_stream.flush()


def _event(type="chat_answered", **payload):
    return Event(ts=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc), user_id="intern-anya", role="intern",
                 team="Платформа объявлений", type=type, payload=payload)


def test_disabled_without_bootstrap(monkeypatch):
    monkeypatch.setattr(settings, "kafka_bootstrap", "")
    before = event_stream.status()
    event_stream.publish([_event()])
    assert event_stream.status() == before and before["enabled"] is False and before["topic"] is None


def test_event_goes_to_topic_in_clickstream_shape(stream):
    event_stream.publish([_event(topic="git", sources=1)])
    assert event_stream.flush()
    [(topic, key, value)] = stream.sent
    assert topic == "ai-buddy.events" and key == "intern-anya"
    assert value == {"event": "chat_answered", "ts": "2026-11-14T12:00:00+00:00", "user_id": "intern-anya",
                     "role": "intern", "team": "Платформа объявлений", "payload": {"topic": "git", "sources": 1},
                     "source": "ai-buddy"}
    status = event_stream.status()
    assert status["sent"] == 1 and status["dropped"] == 0 and status["connected"] and status["queued"] == 0


def test_broker_down_retries_then_drops_without_raising(stream, monkeypatch):
    stream.fail = 2  # две неудачи — третья попытка проходит
    event_stream.publish([_event()])
    assert event_stream.flush() and len(stream.sent) == 1
    stream.fail = 99  # брокер так и не поднялся — событие пропущено, исключений нет
    event_stream.publish([_event()])
    assert event_stream.flush()
    assert event_stream.status()["dropped"] == 1 and event_stream.status()["sent"] == 1


def test_producer_cannot_be_created(stream, monkeypatch):
    def broken():
        raise RuntimeError("нет сети")
    monkeypatch.setattr(event_stream, "_make_producer", broken)
    event_stream.publish([_event()])
    assert event_stream.flush() and event_stream.status()["dropped"] == 1 and not event_stream.status()["connected"]


def test_full_queue_drops_instead_of_blocking(stream, monkeypatch):
    import queue
    monkeypatch.setattr(event_stream, "_queue", queue.Queue(maxsize=1))
    monkeypatch.setattr(event_stream, "_ensure_worker", lambda: None)  # никто не разбирает очередь
    event_stream.publish([_event(), _event(), _event()])
    assert event_stream.status()["queued"] == 1 and event_stream.status()["dropped"] == 2


def test_store_publishes_only_committed_events(stream):
    """Хранилище сервисов: событие уходит после успешной записи; отменённая операция в Kafka не попадает."""
    store = storage.DemoStore.__new__(storage.DemoStore)
    store._store, store._ready, store._lock = storage.InMemoryStore(load_seed()), True, asyncio.Lock()

    async def scenario():
        async with store.transaction(include_events=False, copy_on_commit=False) as data:
            data.events.append(_event("plan_item_done", item_id="anya.w1.notes"))
        with pytest.raises(ValueError):
            async with store.transaction(include_events=False, copy_on_commit=False) as data:
                data.events.append(_event("must_not_leak"))
                raise ValueError("операция отменена")
        async with store.read() as data:
            data.events.append(_event("plan_viewed"))

    asyncio.run(scenario())
    assert event_stream.flush()
    assert [value["event"] for _, _, value in stream.sent] == ["plan_item_done", "plan_viewed"]


def test_status_http(client, stream):
    assert client.get("/events/stream").status_code == 401
    body = client.get("/events/stream", headers=as_user("intern-anya")).get_json()
    assert body["enabled"] is True and body["topic"] == "ai-buddy.events" and set(body) == {
        "enabled", "topic", "connected", "queued", "sent", "dropped"}
