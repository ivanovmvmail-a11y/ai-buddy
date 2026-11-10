import pytest

from app import async_runner
from app.mcp_server import storage
from app.mcp_server.seed import load_seed


@pytest.fixture
def store(monkeypatch):
    store = storage.InMemoryStore(load_seed())
    monkeypatch.setattr(storage, "get_store", lambda: store)
    return store


@pytest.fixture
def snapshot(store):
    def read():
        async def get():
            async with store.transaction() as data:
                return data.model_copy(deep=True)
        return async_runner.run(get())
    return read


@pytest.fixture
def edit(store):
    def update(change):
        async def write():
            async with store.transaction() as data:
                change(data)
        return async_runner.run(write())
    return update
