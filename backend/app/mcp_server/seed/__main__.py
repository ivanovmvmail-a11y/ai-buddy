"""uv run python -m app.mcp_server.seed [--reset]. Только память в T1."""
import argparse

from app.agent.users import DEFAULT_USER_ID, DEMO_USERS
from app.async_runner import run

from . import load_seed, reset_demo
from ..storage import get_store


def main(argv=None):
    parser = argparse.ArgumentParser(description="Load synthetic onboarding demo (process-local memory in T1)")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(argv)
    if args.reset:
        run(reset_demo(DEMO_USERS[DEFAULT_USER_ID]))
    else:
        run(get_store().initialize(load_seed()))
    print("Onboarding demo initialized in process-local memory; persistent seed is T3")


if __name__ == "__main__":
    main()
