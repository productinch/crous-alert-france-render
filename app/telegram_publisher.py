from __future__ import annotations

import logging
import re
import time
import unicodedata
from typing import Any

import httpx

from .config import Settings
from .formatter import format_offer
from .models import Offer

logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


def _normalise_city(value: str | None) -> str:
    """
    Normalise le nom d'une ville.

    Exemple:
    Évry-Courcouronnes
    evry courcouronnes
    EVRY COURCOURONNES

    deviennent la même valeur.
    """
    if not value:
        return ""

    decomposed = unicodedata.normalize("NFKD", value)

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        without_accents.lower(),
    ).strip()


def _city_matches(
    offer_city: str | None,
    target_city: str,
) -> bool:
    """
    Vérifie si la ville de l'offre correspond à la ville demandée.
    """
    offer_value = _normalise_city(offer_city)
    target_value = _normalise_city(target_city)

    if not offer_value or not target_value:
        return False

    return (
        offer_value == target_value
        or offer_value in target_value
        or target_value in offer_value
    )


class TelegramPublisher:
    def __init__(self, settings: Settings) -> None:
        settings.require_telegram()

        self.settings = settings

        self.base_url = (
            f"https://api.telegram.org/"
            f"bot{settings.telegram_bot_token}"
        )

        self.client = httpx.Client(
            timeout=settings.http_timeout_seconds
        )

        # Chaînes générales:
        # Trial + Premium
        self.chat_ids = tuple(
            dict.fromkeys(
                (
                    settings.telegram_trial_chat_id,
                    settings.telegram_premium_chat_id,
                )
            )
        )

        # Chaîne personnalisée
        self.personal_chat_id = (
            settings.telegram_personal_chat_id
        )
        self.personal_city = (
            settings.telegram_personal_city
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "TelegramPublisher":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _call(
        self,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        last_network_error = False

        for attempt in range(4):
            try:
                response = self.client.post(
                    f"{self.base_url}/{method}",
                    json=payload,
                )

                data = response.json()

            except (httpx.HTTPError, ValueError):
                last_network_error = True

                if attempt + 1 < 4:
                    time.sleep(
                        min(2**attempt, 30)
                    )
                    continue

                break

            if (
                response.status_code == 200
                and data.get("ok")
            ):
                return data["result"]

            if response.status_code == 429:
                delay = min(
                    int(
                        data.get(
                            "parameters",
                            {},
                        ).get(
                            "retry_after",
                            2**attempt,
                        )
                    ),
                    60,
                )

                logger.warning(
                    "Telegram rate limit; retrying in %ss",
                    delay,
                )

                time.sleep(delay)
                continue

            raise TelegramError(
                f"Telegram {method} failed: "
                f"HTTP {response.status_code} "
                f"{data.get('description', '')}"
            )

        detail = (
            "network/JSON error"
            if last_network_error
            else "rate limit"
        )

        raise TelegramError(
            f"Telegram {method} failed "
            f"after retries ({detail})"
        ) from None

    def _send_text(
        self,
        chat_id: str,
        text: str,
        offer: Offer,
    ) -> None:
        self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "protect_content": (
                    self.settings.protect_content
                ),
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": (
                                    "Voir l’offre officielle"
                                ),
                                "url": offer.official_url,
                            }
                        ]
                    ]
                },
            },
        )

    def _send_photo(
        self,
        chat_id: str,
        text: str,
        offer: Offer,
    ) -> None:
        self._call(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": offer.image_url,
                "caption": text[:1024],
                "parse_mode": "HTML",
                "protect_content": (
                    self.settings.protect_content
                ),
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": (
                                    "Voir l’offre officielle"
                                ),
                                "url": offer.official_url,
                            }
                        ]
                    ]
                },
            },
        )

    def _publish_to_chat(
        self,
        chat_id: str,
        offer: Offer,
        text: str,
    ) -> None:
        """
        Envoie une offre vers une chaîne Telegram.
        """

        if (
            self.settings.enable_images
            and offer.image_url
        ):
            try:
                self._send_photo(
                    chat_id,
                    text,
                    offer,
                )

                logger.info(
                    "Offer %s sent with photo to %s",
                    offer.offer_id,
                    chat_id,
                )

                return

            except (
                TelegramError,
                httpx.HTTPError,
                ValueError,
            ) as exc:
                logger.warning(
                    "Photo failed for offer %s; "
                    "using text fallback: %s",
                    offer.offer_id,
                    exc,
                )

        self._send_text(
            chat_id,
            text,
            offer,
        )

        logger.info(
            "Offer %s sent as text to %s",
            offer.offer_id,
            chat_id,
        )

    def publish(self, offer: Offer) -> None:
        text = format_offer(offer)

        # Trial et Premium reçoivent
        # toutes les nouvelles offres.
        for chat_id in self.chat_ids:
            self._publish_to_chat(
                chat_id,
                offer,
                text,
            )

        # La chaîne personnalisée reçoit
        # uniquement les offres de la ville choisie.
        if (
            self.personal_chat_id
            and self.personal_city
            and self.personal_chat_id
            not in self.chat_ids
            and _city_matches(
                offer.city,
                self.personal_city,
            )
        ):
            self._publish_to_chat(
                self.personal_chat_id,
                offer,
                text,
            )

            logger.info(
                "Personal alert matched: "
                "target_city=%s "
                "offer_city=%s "
                "offer=%s",
                self.personal_city,
                offer.city,
                offer.offer_id,
            )