from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import Offer

PARIS = ZoneInfo("Europe/Paris")


def _line(label: str, value: str | None) -> str | None:
    if not value:
        return None
    return f"{label} : {html.escape(value)}"


def format_offer(offer: Offer, detected_at: datetime | None = None) -> str:
    now = (detected_at or datetime.now(PARIS)).astimezone(PARIS)
    location = " ".join(value for value in (offer.postal_code, offer.city) if value)
    lines = [
        "🟢 <b>Nouvelle offre CROUS</b>",
        "",
        _line("📍 Ville", location or "Non précisée"),
        _line("🏢 Résidence", offer.residence),
        _line("🏠 Type", offer.housing_type),
        _line("💶 Loyer", offer.rent),
        _line("📐 Surface", offer.surface),
        _line("📅 Disponible", offer.availability_date),
        f"🕐 Détectée à : {now:%d/%m/%Y %H:%M:%S}",
        "",
        "<i>Source : trouverunlogement.lescrous.fr — relevé le "
        f"{now:%d/%m/%Y à %H:%M}.</i>",
        "",
        "<i>Service indépendant non affilié au CROUS. Aucune réservation ni "
        "attribution de logement n’est garantie.</i>",
    ]
    return "\n".join(line for line in lines if line is not None)
