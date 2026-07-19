from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Offer


class _SqliteOfferStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "_SqliteOfferStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS offers (
                offer_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                residence TEXT NOT NULL,
                city TEXT,
                postal_code TEXT,
                housing_type TEXT,
                rent TEXT,
                charges TEXT,
                surface TEXT,
                availability_date TEXT,
                short_description TEXT,
                image_url TEXT,
                official_url TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                raw_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_offers_active ON offers(active);
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self.connection.commit()

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM offers").fetchone()[0])

    def apply_scan(self, offers: list[Offer]) -> list[Offer]:
        now = datetime.now(timezone.utc).isoformat()
        current_ids = {offer.offer_id for offer in offers}
        notifications: list[Offer] = []
        with self.connection:
            for offer in offers:
                previous = self.connection.execute(
                    "SELECT active, content_hash FROM offers WHERE offer_id = ?",
                    (offer.offer_id,),
                ).fetchone()
                if previous is None or not bool(previous["active"]):
                    notifications.append(offer)
                values = asdict(offer)
                raw_json = json.dumps(values.pop("raw"), ensure_ascii=False)
                self.connection.execute(
                    """
                    INSERT INTO offers (
                        offer_id, title, residence, city, postal_code, housing_type,
                        rent, charges, surface, availability_date, short_description,
                        image_url, official_url, content_hash, first_seen_at,
                        last_seen_at, active, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(offer_id) DO UPDATE SET
                        title=excluded.title, residence=excluded.residence,
                        city=excluded.city, postal_code=excluded.postal_code,
                        housing_type=excluded.housing_type, rent=excluded.rent,
                        charges=excluded.charges, surface=excluded.surface,
                        availability_date=excluded.availability_date,
                        short_description=excluded.short_description,
                        image_url=excluded.image_url, official_url=excluded.official_url,
                        content_hash=excluded.content_hash,
                        last_seen_at=excluded.last_seen_at, active=excluded.active,
                        raw_json=excluded.raw_json
                    """,
                    (
                        offer.offer_id,
                        offer.title,
                        offer.residence,
                        offer.city,
                        offer.postal_code,
                        offer.housing_type,
                        offer.rent,
                        offer.charges,
                        offer.surface,
                        offer.availability_date,
                        offer.short_description,
                        offer.image_url,
                        offer.official_url,
                        offer.content_hash,
                        now,
                        now,
                        int(offer.active),
                        raw_json,
                    ),
                )
            if current_ids:
                placeholders = ",".join("?" for _ in current_ids)
                self.connection.execute(
                    f"UPDATE offers SET active = 0 WHERE offer_id NOT IN ({placeholders})",
                    tuple(current_ids),
                )
            else:
                self.connection.execute("UPDATE offers SET active = 0")
        return notifications


class _PostgresOfferStore:
    """Persistent store used by Render through a Neon DATABASE_URL."""

    _LOCK_ID = 1_127_504_709

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - dependency is installed on Render
            raise RuntimeError(
                "PostgreSQL requires psycopg; install the project requirements"
            ) from exc
        self._jsonb: Any
        from psycopg.types.json import Jsonb

        self._jsonb = Jsonb
        # Autocommit keeps read-only count() calls from holding an open transaction;
        # writes below still use explicit atomic transaction blocks.
        self.connection = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "_PostgresOfferStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _migrate(self) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS offers (
                    offer_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    residence TEXT NOT NULL,
                    city TEXT,
                    postal_code TEXT,
                    housing_type TEXT,
                    rent TEXT,
                    charges TEXT,
                    surface TEXT,
                    availability_date TEXT,
                    short_description TEXT,
                    image_url TEXT,
                    official_url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_seen_at TIMESTAMPTZ NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    raw_json JSONB NOT NULL
                )
                """
            )
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_offers_active ON offers(active)"
            )

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS total FROM offers").fetchone()
        return int(row["total"])

    def apply_scan(self, offers: list[Offer]) -> list[Offer]:
        now = datetime.now(timezone.utc)
        current_ids = {offer.offer_id for offer in offers}
        notifications: list[Offer] = []
        with self.connection.transaction():
            # Serialise overlapping deploys/scans so one offer cannot be announced twice.
            self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (self._LOCK_ID,))
            for offer in offers:
                previous = self.connection.execute(
                    "SELECT active, content_hash FROM offers WHERE offer_id = %s",
                    (offer.offer_id,),
                ).fetchone()
                if previous is None or not bool(previous["active"]):
                    notifications.append(offer)
                values = asdict(offer)
                raw_json = self._jsonb(values.pop("raw"))
                self.connection.execute(
                    """
                    INSERT INTO offers (
                        offer_id, title, residence, city, postal_code, housing_type,
                        rent, charges, surface, availability_date, short_description,
                        image_url, official_url, content_hash, first_seen_at,
                        last_seen_at, active, raw_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT(offer_id) DO UPDATE SET
                        title=excluded.title, residence=excluded.residence,
                        city=excluded.city, postal_code=excluded.postal_code,
                        housing_type=excluded.housing_type, rent=excluded.rent,
                        charges=excluded.charges, surface=excluded.surface,
                        availability_date=excluded.availability_date,
                        short_description=excluded.short_description,
                        image_url=excluded.image_url, official_url=excluded.official_url,
                        content_hash=excluded.content_hash,
                        last_seen_at=excluded.last_seen_at, active=excluded.active,
                        raw_json=excluded.raw_json
                    """,
                    (
                        offer.offer_id,
                        offer.title,
                        offer.residence,
                        offer.city,
                        offer.postal_code,
                        offer.housing_type,
                        offer.rent,
                        offer.charges,
                        offer.surface,
                        offer.availability_date,
                        offer.short_description,
                        offer.image_url,
                        offer.official_url,
                        offer.content_hash,
                        now,
                        now,
                        bool(offer.active),
                        raw_json,
                    ),
                )
            if current_ids:
                placeholders = ",".join("%s" for _ in current_ids)
                self.connection.execute(
                    f"UPDATE offers SET active = FALSE "
                    f"WHERE offer_id NOT IN ({placeholders})",
                    tuple(current_ids),
                )
            else:
                self.connection.execute("UPDATE offers SET active = FALSE")
        return notifications


class OfferStore:
    """Backend-selecting wrapper kept compatible with the original SQLite API."""

    def __init__(self, target: str | Path) -> None:
        if isinstance(target, str) and target.startswith(("postgres://", "postgresql://")):
            self._backend: Any = _PostgresOfferStore(target)
        else:
            self._backend = _SqliteOfferStore(Path(target))

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> "OfferStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def count(self) -> int:
        return self._backend.count()

    def apply_scan(self, offers: list[Offer]) -> list[Offer]:
        return self._backend.apply_scan(offers)
