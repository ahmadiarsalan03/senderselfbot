"""Entry point for the Telegram self-management bot."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .account_manager import AccountManager
from .config import ConfigError, load_config
from .security import SecretsBox
from .storage import Storage

LOGGER = logging.getLogger(__name__)


async def async_main(config_path: Path | None = None) -> None:
    config = load_config(config_path)
    secrets = SecretsBox(config.encryption_key)
    storage = Storage(config.storage_dir / "state.json", secrets)
    manager = AccountManager(config, storage, secrets)
    await manager.start_existing_clients()
    await manager.ensure_initial_session()

    stop_event = asyncio.Event()

    def _signal_handler(*_: int) -> None:
        LOGGER.info("Received stop signal. Shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    waiter = asyncio.create_task(manager.wait_forever())
    stopper = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait({waiter, stopper}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await manager.stop()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Telegram self-management bot")
    parser.add_argument("--config", type=Path, default=None, help="Path to configuration file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        asyncio.run(async_main(args.config))
    except ConfigError as exc:
        LOGGER.error("Configuration error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user")


if __name__ == "__main__":
    main()
