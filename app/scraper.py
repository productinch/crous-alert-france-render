from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class CrousError(RuntimeError):
    pass


@dataclass(slots=True)
class FetchResult:
    items: list[dict[str, Any]]
    total: int


class CrousClient:
    PAGE_SIZE = 100

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.crous_base_url,
            timeout=settings.http_timeout_seconds,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/ld+json, application/json",
                "Content-Type": "application/json",
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "CrousClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _payload(self, page: int, aggregate: bool) -> dict[str, Any]:
        return {
            "idTool": self.settings.crous_tool_id,
            "need_aggregation": aggregate,
            "page": page,
            "pageSize": self.PAGE_SIZE,
            "sector": None,
            "occupationModes": [],
            "location": None,
            "residence": None,
            "precision": None,
            "equipment": [],
            "price": {"max": 10_000_000},
            "area": {"min": 0},
            "adaptedPmr": False,
            "toolMechanism": self.settings.crous_tool_mechanism,
        }

    @staticmethod
    def _retry_after(response: httpx.Response, fallback: float) -> float:
        header = response.headers.get("Retry-After")
        if not header:
            return fallback
        try:
            return min(float(header), 300.0)
        except ValueError:
            try:
                delay = parsedate_to_datetime(header).timestamp() - time.time()
                return min(max(delay, 0.0), 300.0)
            except (TypeError, ValueError):
                return fallback

    def _post_page(self, page: int, aggregate: bool) -> dict[str, Any]:
        endpoint = f"/api/fr/search/{self.settings.crous_tool_id}"
        last_error: Exception | None = None
        for attempt in range(self.settings.http_max_retries):
            try:
                response = self.client.post(
                    endpoint, json=self._payload(page=page, aggregate=aggregate)
                )
                if response.status_code == 200:
                    data = response.json()
                    if not isinstance(data, dict) or "results" not in data:
                        raise CrousError("Unexpected CROUS JSON structure")
                    return data
                if response.status_code in {403, 429} or response.status_code >= 500:
                    delay = self._retry_after(response, min(2**attempt, 60))
                    logger.warning(
                        "CROUS HTTP %s; retrying in %.1fs",
                        response.status_code,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise CrousError(f"CROUS returned HTTP {response.status_code}")
            except (httpx.HTTPError, ValueError, CrousError) as exc:
                last_error = exc
                if attempt + 1 >= self.settings.http_max_retries:
                    break
                delay = min(2**attempt, 60)
                logger.warning("CROUS request failed; retrying in %ss: %s", delay, exc)
                time.sleep(delay)
        raise CrousError(f"CROUS request failed after retries: {last_error}")

    def fetch_all(self) -> FetchResult:
        first = self._post_page(page=1, aggregate=True)
        results = first["results"]
        total = int(results.get("total", {}).get("value", 0))
        items = list(results.get("items", []))
        page_count = max(1, math.ceil(total / self.PAGE_SIZE))
        for page in range(2, page_count + 1):
            time.sleep(1)
            page_data = self._post_page(page=page, aggregate=False)
            items.extend(page_data["results"].get("items", []))
        if len(items) < total:
            raise CrousError(f"Incomplete CROUS result: got {len(items)} of {total}")
        logger.info("CROUS scan successful: %s offers", len(items))
        return FetchResult(items=items, total=total)
