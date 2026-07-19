from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Offer:
    offer_id: str
    title: str
    residence: str
    city: str | None
    postal_code: str | None
    housing_type: str | None
    rent: str | None
    charges: str | None
    surface: str | None
    availability_date: str | None
    short_description: str | None
    image_url: str | None
    official_url: str
    content_hash: str
    active: bool = True
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
