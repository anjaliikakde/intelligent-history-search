"""
privacy.py — Privacy controls: pause mode, settings persistence, domain blocklist.

Design decisions:
- Settings are persisted to a JSON file (SETTINGS_FILE) — survive restarts
- Pause mode is checked by host.py before any ingest operation
- Blocked domains are checked before embedding — no data ever enters store
- All operations are synchronous — settings file is tiny, no async needed
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from config import (
    SETTINGS_FILE,
    DEFAULT_SETTINGS,
    DEFAULT_EXPIRY_DAYS,
    DEFAULT_SEARCH_LIMIT,
    BLOCKED_DOMAINS,
    BLOCKED_URL_PREFIXES,
)
from logger import get_logger

log = get_logger("privacy")


# ---------------------------------------------------------------------------
# Settings dataclass — single source of truth for runtime settings
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    expiry_days:     int   = DEFAULT_EXPIRY_DAYS
    pause_tracking:  bool  = False
    search_limit:    int   = DEFAULT_SEARCH_LIMIT

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        return cls(
            expiry_days    = int(data.get("expiry_days",    DEFAULT_EXPIRY_DAYS)),
            pause_tracking = bool(data.get("pause_tracking", False)),
            search_limit   = int(data.get("search_limit",   DEFAULT_SEARCH_LIMIT)),
        )


# ---------------------------------------------------------------------------
# PrivacyManager class
# ---------------------------------------------------------------------------

class PrivacyManager:
    """
    Manages all privacy-related state and checks.

    Responsibilities:
    - Load / save settings from disk
    - Expose pause_tracking flag to host.py
    - Check if a URL should be ingested (blocked domains, pause mode)
    - Update settings from extension messages
    """

    def __init__(self) -> None:
        self._settings: Settings = Settings()
        self._loaded:   bool     = False

    # -----------------------------------------------------------------------
    # Settings persistence
    # -----------------------------------------------------------------------

    def load(self) -> bool:
        """
        Loads settings from SETTINGS_FILE.
        Creates the file with defaults if it does not exist.
        Returns True on success.
        """
        if SETTINGS_FILE.exists():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                self._settings = Settings.from_dict(raw)
                self._loaded   = True
                log.info("Settings loaded: %s", self._settings.to_dict())
                return True
            except Exception as exc:
                log.error(
                    "Failed to load settings from %s: %s — using defaults",
                    SETTINGS_FILE,
                    exc,
                )
                # Fall through to defaults

        # File missing or corrupt — write defaults
        self._settings = Settings()
        self._loaded   = True
        self._save()
        log.info("Settings file created with defaults at %s", SETTINGS_FILE)
        return True

    def _save(self) -> None:
        """
        Persists current settings to SETTINGS_FILE.
        Writes atomically via a temp file to avoid partial writes.
        """
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(self._settings.to_dict(), indent=2),
                encoding="utf-8",
            )
            tmp.replace(SETTINGS_FILE)  # atomic on POSIX, best-effort on Windows
            log.debug("Settings saved: %s", self._settings.to_dict())
        except Exception as exc:
            log.error("Failed to save settings: %s", exc, exc_info=True)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # Settings access
    # -----------------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def is_tracking_paused(self) -> bool:
        """True if user has paused tracking via popup toggle."""
        return self._settings.pause_tracking

    @property
    def expiry_days(self) -> int:
        return self._settings.expiry_days

    @property
    def search_limit(self) -> int:
        return self._settings.search_limit

    # -----------------------------------------------------------------------
    # Update settings from extension message
    # -----------------------------------------------------------------------

    def update_settings(self, payload: dict) -> dict:
        """
        Updates settings from a SETTINGS message sent by the extension.
        Only updates fields that are present in payload.
        Returns updated settings dict.

        Accepted payload keys:
        - pause_tracking  : bool
        - expiry_days     : int (0 = disabled)
        - search_limit    : int
        """
        changed = False

        if "pause_tracking" in payload:
            new_val = bool(payload["pause_tracking"])
            if new_val != self._settings.pause_tracking:
                self._settings.pause_tracking = new_val
                log.info(
                    "Tracking %s by user",
                    "paused" if new_val else "resumed",
                )
                changed = True

        if "expiry_days" in payload:
            try:
                new_val = int(payload["expiry_days"])
                if 0 <= new_val <= 3650:
                    if new_val != self._settings.expiry_days:
                        self._settings.expiry_days = new_val
                        log.info("Expiry days updated to %d", new_val)
                        changed = True
                else:
                    log.warning("expiry_days out of range: %d", new_val)
            except (TypeError, ValueError) as exc:
                log.warning("Invalid expiry_days value: %s", exc)

        if "search_limit" in payload:
            try:
                new_val = int(payload["search_limit"])
                if 1 <= new_val <= 50:
                    if new_val != self._settings.search_limit:
                        self._settings.search_limit = new_val
                        log.info("Search limit updated to %d", new_val)
                        changed = True
                else:
                    log.warning("search_limit out of range: %d", new_val)
            except (TypeError, ValueError) as exc:
                log.warning("Invalid search_limit value: %s", exc)

        if changed:
            self._save()

        return self._settings.to_dict()

    # -----------------------------------------------------------------------
    # Core privacy check — should this URL be ingested?
    # -----------------------------------------------------------------------

    def should_ingest(self, url: str, is_incognito: bool) -> tuple[bool, str]:
        """
        Single entry point for all ingest permission checks.

        Returns (allowed: bool, reason: str).
        Reason is logged and returned to extension for debugging.

        Check order matters — cheapest checks first:
        1. Incognito tab → always block (Chrome flag)
        2. Pause mode    → user toggled off
        3. Blocked URL prefix → chrome://, file://, etc.
        4. Blocked domain → localhost, 127.0.0.1, etc.
        """

        # 1. Incognito — Chrome already respects this, but we enforce it too
        if is_incognito:
            return False, "incognito tab — tracking disabled"

        # 2. User paused tracking
        if self._settings.pause_tracking:
            return False, "tracking paused by user"

        # 3. Blocked URL prefix
        for prefix in BLOCKED_URL_PREFIXES:
            if url.startswith(prefix):
                return False, f"blocked URL prefix: {prefix}"

        # 4. Blocked domain
        try:
            from urllib.parse import urlparse
            netloc = urlparse(url).netloc.lower().split(":")[0]
            if netloc in BLOCKED_DOMAINS:
                return False, f"blocked domain: {netloc}"
        except Exception:
            return False, "URL parse error during domain check"

        return True, "ok"

    # -----------------------------------------------------------------------
    # Pause / Resume shortcuts
    # -----------------------------------------------------------------------

    def pause(self) -> None:
        """Pauses tracking and persists."""
        self._settings.pause_tracking = True
        self._save()
        log.info("Tracking paused")

    def resume(self) -> None:
        """Resumes tracking and persists."""
        self._settings.pause_tracking = False
        self._save()
        log.info("Tracking resumed")

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------

    def health(self) -> dict:
        return {
            "loaded":          self._loaded,
            "pause_tracking":  self._settings.pause_tracking,
            "expiry_days":     self._settings.expiry_days,
            "search_limit":    self._settings.search_limit,
            "settings_file":   str(SETTINGS_FILE),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

privacy = PrivacyManager()