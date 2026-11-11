"""Идемпотентный seed выбранного хранилища; --reset заменяет его состояние."""
import argparse

from app.agent.users import DEFAULT_USER_ID, DEMO_USERS
from app.async_runner import run
from psycopg.errors import UndefinedTable

from . import _reset_store, load_seed
from .. import storage


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialize onboarding seed via DATABASE_URL (or process-local memory)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reset", action="store_true", help="Replace all onboarding state in the selected store with demo seed")
    mode.add_argument("--validate", action="store_true", help="Validate seed only, without opening the store")
    args = parser.parse_args(argv)
    if args.validate:
        seed = load_seed()
        print(f"Seed validated: {len(seed.interns)} interns, {len(seed.items)} items; validation only, no server or database was populated")
        return
    store = storage.get_store()
    if isinstance(store, storage.DemoStore):
        # CLI сообщает правду о результате БД; fallback предназначен для сервера.
        store = store.primary

    async def seed_store():
        try:
            seed = load_seed()
            await store.initialize(seed)
            if args.reset:
                await _reset_store(DEMO_USERS[DEFAULT_USER_ID], store)
        finally:
            try:
                await store.close()
            finally:
                from app import rag
                service = rag.cached_service()
                if service is not None:
                    await service.store.close()

    try:
        run(seed_store())
    except Exception as error:
        if isinstance(error, UndefinedTable):
            storage.log.warning(storage.MISSING_SCHEMA_WARNING)
        else:
            storage.log.warning("Seed онбординга не выполнен (%s); сервер может продолжить в демо-режиме.", type(error).__name__)
        raise SystemExit(1) from None
    print(f"Onboarding seed {'reset' if args.reset else 'initialized (existing data preserved)'} via {type(store).__name__}")


if __name__ == "__main__":
    main()
