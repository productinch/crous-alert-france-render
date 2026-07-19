from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True, slots=True)
class Settings:
    crous_base_url: str
    crous_tool_id: int
    crous_tool_mechanism: str
    poll_interval_seconds: int
    http_timeout_seconds: int
    http_max_retries: int
    user_agent: str
    telegram_bot_token: str
    telegram_trial_chat_id: str
    telegram_premium_chat_id: str
    enable_images: bool
    protect_content: bool
    publish_existing_on_first_run: bool
    database_url: str
    database_path: Path
    log_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            crous_base_url=os.getenv(
                "CROUS_BASE_URL", "https://trouverunlogement.lescrous.fr"
            ).rstrip("/"),
            crous_tool_id=_int("CROUS_TOOL_ID", 47),
            crous_tool_mechanism=os.getenv("CROUS_TOOL_MECHANISM", "residual"),
            poll_interval_seconds=max(_int("POLL_INTERVAL_SECONDS", 120), 30),
            http_timeout_seconds=_int("HTTP_TIMEOUT_SECONDS", 20),
            http_max_retries=_int("HTTP_MAX_RETRIES", 4),
            user_agent=os.getenv(
                "CROUS_USER_AGENT",
                "CROUSAlertFrance/0.1 (independent student project; contact: unset)",
            ),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_trial_chat_id=os.getenv(
                "TELEGRAM_TRIAL_CHAT_ID", "-1004420745494"
            ),
            telegram_premium_chat_id=os.getenv(
                "TELEGRAM_PREMIUM_CHAT_ID", "-1004417792221"
            ),
            enable_images=_bool("ENABLE_IMAGES", False),
            protect_content=_bool("TELEGRAM_PROTECT_CONTENT", True),
            publish_existing_on_first_run=_bool(
                "PUBLISH_EXISTING_ON_FIRST_RUN", False
            ),
            database_url=os.getenv("DATABASE_URL", "").strip(),
            database_path=Path(os.getenv("DATABASE_PATH", "data/offers.sqlite3")),
            log_path=Path(os.getenv("LOG_PATH", "logs/crous-alert.log")),
        )
        if settings.poll_interval_seconds < 30:
            raise ValueError("POLL_INTERVAL_SECONDS must be at least 30 seconds")
        return settings

    @property
    def database_target(self) -> str | Path:
        """Use PostgreSQL in hosted environments, SQLite for local development."""
        return self.database_url or self.database_path

    def require_telegram(self) -> None:
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is missing from the environment")
        if not self.telegram_trial_chat_id or not self.telegram_premium_chat_id:
            raise ValueError("Both Telegram channel IDs are required")
