from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import Settings
from .formatter import format_offer
from .models import Offer

logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


class TelegramPublisher:
    def __init__(self, settings: Settings) -> None:
        settings.require_telegram()
        self.settings = settings
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self.client = httpx.Client(timeout=settings.http_timeout_seconds)
        self.chat_ids = (
            settings.telegram_trial_chat_id,
            settings.telegram_premium_chat_id,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "TelegramPublisher":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_network_error = False
        for attempt in range(4):
            try:
                response = self.client.post(f"{self.base_url}/{method}", json=payload)
                data = response.json()
            except (httpx.HTTPError, ValueError):
                last_network_error = True
                if attempt + 1 < 4:
                    time.sleep(min(2**attempt, 30))
                    continue
                break
            if response.status_code == 200 and data.get("ok"):
                return data["result"]
            if response.status_code == 429:
                delay = min(
                    int(data.get("parameters", {}).get("retry_after", 2**attempt)),
                    60,
                )
                logger.warning("Telegram rate limit; retrying in %ss", delay)
                time.sleep(delay)
                continue
            raise TelegramError(
                f"Telegram {method} failed: HTTP {response.status_code} "
                f"{data.get('description', '')}"
            )
        detail = "network/JSON error" if last_network_error else "rate limit"
        raise TelegramError(
            f"Telegram {method} failed after retries ({detail})"
        ) from None

    def _send_text(self, chat_id: str, text: str, offer: Offer) -> None:
        self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "protect_content": self.settings.protect_content,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Voir l’offre officielle", "url": offer.official_url}]
                    ]
                },
            },
        )

    def _send_photo(self, chat_id: str, text: str, offer: Offer) -> None:
        self._call(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": offer.image_url,
                "caption": text[:1024],
                "parse_mode": "HTML",
                "protect_content": self.settings.protect_content,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Voir l’offre officielle", "url": offer.official_url}]
                    ]
                },
            },
        )

    def publish(self, offer: Offer) -> None:
        text = format_offer(offer)
        for chat_id in self.chat_ids:
            if self.settings.enable_images and offer.image_url:
                try:
                    self._send_photo(chat_id, text, offer)
                    logger.info("Offer %s sent with photo to %s", offer.offer_id, chat_id)
                    continue
                except (TelegramError, httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "Photo failed for offer %s; using text fallback: %s",
                        offer.offer_id,
                        exc,
                    )
            self._send_text(chat_id, text, offer)
            logger.info("Offer %s sent as text to %s", offer.offer_id, chat_id)
