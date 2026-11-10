"""Проверка seed в T1; --reset сбрасывает только память текущего процесса."""
import argparse

from app.agent.users import DEFAULT_USER_ID, DEMO_USERS
from app.async_runner import run

from . import load_seed, reset_demo


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate onboarding seed only (T1); does not populate a server or database")
    parser.add_argument("--reset", action="store_true", help="Reset only this short-lived process, not a running server")
    args = parser.parse_args(argv)
    if args.reset:
        run(reset_demo(DEMO_USERS[DEFAULT_USER_ID]))
        print("Onboarding demo reset in process-local memory only; running servers and databases are unchanged")
    else:
        seed = load_seed()
        print(f"Seed validated: {len(seed.interns)} interns, {len(seed.items)} items; T1 validation only, no server or database was populated")


if __name__ == "__main__":
    main()
