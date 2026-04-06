"""
logger.py — Structured, rotating file logger for the native host.

Why file logging and not print()?
- host.py uses stdout to send messages to Chrome — any stray print()
  will corrupt the Native Messaging protocol and crash the extension.
- Rotating file handler ensures logs never fill up the disk.
- Structured format makes production debugging possible.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_LEVEL


# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------
# Example output:
# 2024-01-15 14:23:01,456 | INFO     | store      | Upserted point: abc123
# 2024-01-15 14:23:01,789 | ERROR    | embedder   | Model load failed: ...

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(module)-12s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# Build the logger
# ---------------------------------------------------------------------------

def _build_logger() -> logging.Logger:
    logger = logging.getLogger("history_search")

    # Avoid adding duplicate handlers if module is re-imported
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # Rotating file handler — never fills disk
    file_handler = RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(_FORMATTER)
    logger.addHandler(file_handler)

    # IMPORTANT: Do NOT add a StreamHandler (stdout/stderr).
    # stdout is owned by Native Messaging protocol.
    # stderr goes nowhere useful in production.

    return logger


# ---------------------------------------------------------------------------
# Module-level logger — import this everywhere
# ---------------------------------------------------------------------------

log = _build_logger()


# ---------------------------------------------------------------------------
# Convenience: get a child logger per module
# Usage:  from logger import get_logger
#         log = get_logger(__name__)
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """
    Returns a child logger namespaced under the root logger.
    Example: get_logger("store") → logs as 'history_search.store'
    """
    return logging.getLogger(f"history_search.{name}")