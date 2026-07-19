from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .parser import parse_offers
from .scraper import CrousClient
from .storage import OfferStore
from .telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)
PARIS = ZoneInfo("Europe/Paris")


@dataclass(slots=True)
class ScanSummary:
    fetched: int
    notified: int
    initial_seed: bool


def scan_once(settings: Settings, publisher: TelegramPublisher | None) -> ScanSummary:
    with CrousClient(settings) as crous, OfferStore(settings.database_target) as store:
        initial_seed = store.count() == 0
        fetched = crous.fetch_all()
        offers = parse_offers(
            fetched.items, settings.crous_base_url, settings.crous_tool_id
        )
        to_notify = store.apply_scan(offers)
        if initial_seed and not settings.publish_existing_on_first_run:
            logger.info("Initial seed: %s offers stored without publication", len(offers))
            to_notify = []
        if publisher:
            for offer in to_notify:
                publisher.publish(offer)
        return ScanSummary(
            fetched=len(offers), notified=len(to_notify), initial_seed=initial_seed
        )


def run_forever(settings: Settings) -> None:
    settings.require_telegram()
    consecutive_errors = 0
    with TelegramPublisher(settings) as publisher:
        while True:
            started = time.monotonic()
            try:
                summary = scan_once(settings, publisher)
                consecutive_errors = 0
                logger.info(
                    "Scan done: fetched=%s notified=%s initial_seed=%s",
                    summary.fetched,
                    summary.notified,
                    summary.initial_seed,
                )
            except Exception:
                consecutive_errors += 1
                logger.exception("Scan failed (consecutive=%s)", consecutive_errors)
            elapsed = time.monotonic() - started
            base_delay = settings.poll_interval_seconds
            if consecutive_errors:
                base_delay = min(base_delay * (2**min(consecutive_errors, 5)), 3600)
            time.sleep(max(1, base_delay - elapsed))
