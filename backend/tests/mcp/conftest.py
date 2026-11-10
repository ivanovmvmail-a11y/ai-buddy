import pytest
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo

from app import async_runner
from app.mcp_server import storage
from app.mcp_server.seed import load_seed

MIGRATION = Path(__file__).resolve().parents[3] / "supabase/migrations/20261111010000_onboarding.sql"


def pytest_generate_tests(metafunc):
    if "store" in metafunc.fixturenames:
        backends = ["memory", "postgres"] if metafunc.config.getoption("--mcp-postgres") else ["memory"]
        metafunc.parametrize("store", backends, indirect=True)


@pytest.fixture(scope="session")
def onboarding_dsn(request):
    if not request.config.getoption("--mcp-postgres"):
        pytest.skip("Use --mcp-postgres with a cached local pgvector/pgvector:pg17 image")
    environment = {key: value for key, value in os.environ.items() if key not in {
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
    }}
    name = f"ai-buddy-onboarding-tests-{uuid4().hex[:12]}"
    def docker(*args):
        return subprocess.run(["docker", "--host=unix:///var/run/docker.sock", *args], env=environment,
                              capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    docker("run", "--detach", "--rm", "--pull=never", "--name", name,
           "-e", "POSTGRES_USER=onboarding_test", "-e", "POSTGRES_PASSWORD=onboarding-test-only",
           "-p", "127.0.0.1::5432", "pgvector/pgvector:pg17")
    try:
        port = int(docker("port", name, "5432/tcp").split(":")[-1])
        dsn = make_conninfo(host="127.0.0.1", port=port, user="onboarding_test",
                            password="onboarding-test-only", dbname="onboarding_test", connect_timeout=1)
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg.connect(dsn, autocommit=True) as connection:
                    connection.execute(MIGRATION.read_text(encoding="utf-8"))
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        yield dsn
    finally:
        docker("rm", "--force", name)

@pytest.fixture
def store(monkeypatch, request):
    if request.param == "postgres":
        from app.mcp_server.postgres import PostgresStore
        store = PostgresStore(request.getfixturevalue("onboarding_dsn"))
        async_runner.run(store.initialize(load_seed(), reset=True))
    else:
        store = storage.InMemoryStore(load_seed())
    monkeypatch.setattr(storage, "get_store", lambda: store)
    yield store
    async_runner.run(store.close())


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
