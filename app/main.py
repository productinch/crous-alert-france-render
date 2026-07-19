from __future__ import annotations

import argparse
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings
from .monitoring import run_forever, scan_once
from .telegram_publisher import TelegramPublisher


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def configure_logging(settings: Settings) -> None:
    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s — %(message)s"
    )
    file_handler = RotatingFileHandler(
        settings.log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
    # httpx logs the complete request URL at INFO level. Telegram embeds the bot
    # token in that URL, so these transport logs must never be enabled.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="CROUS Alert France")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument(
        "--no-publish", action="store_true", help="Scan and store without Telegram"
    )
    args = parser.parse_args()
    load_env_file()
    settings = Settings.from_env()
    configure_logging(settings)
    if args.once:
        if args.no_publish:
            summary = scan_once(settings, publisher=None)
        else:
            with TelegramPublisher(settings) as publisher:
                summary = scan_once(settings, publisher=publisher)
        print(
            f"Scan OK — fetched={summary.fetched} notified={summary.notified} "
            f"initial_seed={summary.initial_seed}"
        )
        return
    run_forever(settings)


if __name__ == "__main__":
    main()
