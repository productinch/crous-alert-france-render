from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

from .models import Offer

ADDRESS_RE = re.compile(r"\b(?P<postal>\d{5})\s+(?P<city>[^,]+)\s*$")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None
    parser = _TextExtractor()
    parser.feed(html.unescape(value))
    text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", text) or None


def _location(address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    match = ADDRESS_RE.search(address)
    if not match:
        return None, None
    return match.group("postal"), match.group("city").strip().title()


def _rent(modes: list[dict[str, Any]]) -> str | None:
    values: list[int] = []
    for mode in modes:
        rent = mode.get("rent") or {}
        for key in ("min", "max"):
            if isinstance(rent.get(key), (int, float)):
                values.append(int(rent[key]))
    if not values:
        return None
    low, high = min(values) / 100, max(values) / 100
    return f"{low:.2f} €" if low == high else f"{low:.2f}–{high:.2f} €"


def _surface(area: dict[str, Any] | None) -> str | None:
    if not area:
        return None
    low, high = area.get("min"), area.get("max")
    if low is None and high is None:
        return None
    if low == high or high is None:
        return f"{float(low):g} m²"
    if low is None:
        return f"{float(high):g} m²"
    return f"{float(low):g}–{float(high):g} m²"


def _media_url(base_url: str, item: dict[str, Any]) -> str | None:
    residence = item.get("residence") or {}
    residence_media = residence.get("medias") or []
    item_media = item.get("medias") or []
    media = (residence_media or item_media)
    if not media or not media[0].get("src"):
        return None
    src = quote(str(media[0]["src"]), safe="/")
    return f"{base_url}/media/cache/resolve/preview/{src}"


def parse_offer(item: dict[str, Any], base_url: str, tool_id: int) -> Offer:
    residence = item.get("residence") or {}
    address = residence.get("address")
    postal_code, city = _location(address)
    offer_id = str(item["id"])
    canonical = {
        "id": offer_id,
        "label": item.get("label"),
        "residence": residence.get("label"),
        "address": address,
        "area": item.get("area"),
        "occupationModes": item.get("occupationModes"),
        "available": item.get("available"),
        "medias": item.get("medias"),
        "residenceMedias": residence.get("medias"),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    description = _clean_html(item.get("description") or residence.get("description"))
    if description and len(description) > 240:
        description = description[:237].rstrip() + "…"
    return Offer(
        offer_id=offer_id,
        title=str(item.get("label") or "Logement CROUS"),
        residence=str(residence.get("label") or "Résidence non précisée"),
        city=city,
        postal_code=postal_code,
        housing_type=str(item.get("label")) if item.get("label") else None,
        rent=_rent(item.get("occupationModes") or []),
        charges=None,
        surface=_surface(item.get("area")),
        availability_date=None,
        short_description=description,
        image_url=_media_url(base_url, item),
        official_url=f"{base_url}/tools/{tool_id}/accommodations/{offer_id}",
        content_hash=digest,
        active=bool(item.get("available", True)),
        raw=item,
    )


def parse_offers(
    items: list[dict[str, Any]], base_url: str, tool_id: int
) -> list[Offer]:
    offers: list[Offer] = []
    for item in items:
        if item.get("id") is None:
            continue
        offers.append(parse_offer(item, base_url, tool_id))
    return offers
