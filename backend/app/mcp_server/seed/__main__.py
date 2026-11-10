"""Идемпотентный seed выбранного хранилища; --reset заменяет его состояние."""
import argparse

from app.agent.users import DEFAULT_USER_ID, DEMO_USERS
from app.async_runner import run

from . import load_seed, reset_demo
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

    async def seed_store():
        try:
            if args.reset:
                await reset_demo(DEMO_USERS[DEFAULT_USER_ID])
            else:
                await store.initialize(load_seed())
        finally:
            await store.close()

    run(seed_store())
    print(f"Onboarding seed {'reset' if args.reset else 'initialized (existing data preserved)'} via {type(store).__name__}")


if __name__ == "__main__":
    main()
