from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify

from .config import Settings
from .main import configure_logging, load_env_file
from .monitoring import run_forever

app = Flask(__name__)
logger = logging.getLogger(__name__)
_thread: threading.Thread | None = None
_started_at: str | None = None
_last_error: str | None = None
_lock = threading.Lock()


def _monitor() -> None:
    global _last_error
    try:
        run_forever(Settings.from_env())
    except BaseException as exc:
        _last_error = f"{type(exc).__name__}: {exc}"
        logger.exception("Background monitor stopped")


def start_monitor_once() -> threading.Thread | None:
    global _thread, _started_at
    if os.getenv("MONITOR_ENABLED", "true").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        load_env_file()
        settings = Settings.from_env()
        configure_logging(settings)
        settings.require_telegram()
        if not settings.database_url:
            logger.warning(
                "DATABASE_URL is empty; hosted restarts can lose SQLite state"
            )
        _started_at = datetime.now(timezone.utc).isoformat()
        _thread = threading.Thread(
            target=_monitor, name="crous-monitor", daemon=True
        )
        _thread.start()
        return _thread


@app.get("/")
@app.get("/healthz")
def health() -> tuple[object, int]:
    alive = bool(_thread and _thread.is_alive())
    return (
        jsonify(
            service="crous-alert-france",
            status="ok" if alive else "error",
            monitor_alive=alive,
            started_at=_started_at,
        ),
        200 if alive else 503,
    )


start_monitor_once()
