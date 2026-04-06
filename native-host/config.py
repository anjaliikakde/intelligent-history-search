"""
config.py — Single source of truth for all constants, paths, and settings.
Every other module imports from here. Never hardcode values anywhere else.
"""

import os
import sys
import platform
from pathlib import Path


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

PLATFORM = platform.system()  # "Windows", "Darwin", "Linux"
IS_WINDOWS = PLATFORM == "Windows"
IS_MAC     = PLATFORM == "Darwin"
IS_LINUX   = PLATFORM == "Linux"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Root directory of the native host (where host.py lives)
HOST_DIR = Path(__file__).parent.resolve()

# Where EdgeShard data is stored — persists across restarts
if IS_WINDOWS:
    _base = Path(os.environ.get("APPDATA", HOST_DIR))
elif IS_MAC:
    _base = Path.home() / "Library" / "Application Support"
else:
    _base = Path.home() / ".local" / "share"

DATA_DIR        = _base / "browser-history-search"
SHARD_DIR       = DATA_DIR / "qdrant-edge"
MODELS_DIR      = DATA_DIR / "models"
LOG_DIR         = DATA_DIR / "logs"
SETTINGS_FILE   = DATA_DIR / "settings.json"

# Ensure all directories exist at import time
for _dir in [DATA_DIR, SHARD_DIR, MODELS_DIR, LOG_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Native Messaging
# ---------------------------------------------------------------------------

# Must match "name" field in com.historysearch.host.json
HOST_NAME = "com.historysearch.host"

# Chrome sends messages as 4-byte length prefix + JSON body
# Max message size Chrome allows: 1MB
NATIVE_MESSAGE_MAX_BYTES = 1024 * 1024  # 1 MB


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

# Lightweight model — 80MB, 384-dim vectors, runs fully offline
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_DIMENSION     = 384
VECTOR_NAME          = "page-vector"


# ---------------------------------------------------------------------------
# EdgeShard / Search
# ---------------------------------------------------------------------------

# How many results to return for a search query
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT     = 50

# Hybrid search weights (keyword + semantic)
SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT  = 0.3


# ---------------------------------------------------------------------------
# Input validation limits
# ---------------------------------------------------------------------------

MAX_URL_LENGTH      = 2048   # Standard browser URL limit
MAX_TITLE_LENGTH    = 200    # Page title max chars we store
MAX_CONTENT_LENGTH  = 500    # Body text max chars we extract
MAX_QUERY_LENGTH    = 200    # Search query max chars
MIN_QUERY_LENGTH    = 1      # Search query min chars


# ---------------------------------------------------------------------------
# Privacy / Data retention
# ---------------------------------------------------------------------------

# Auto-expiry: entries older than this are deleted on startup
# Set to 0 to disable auto-expiry
DEFAULT_EXPIRY_DAYS = 90

# Domains that are always skipped — never stored
BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "chrome://",
    "chrome-extension://",
    "about:",
    "file://",
    "data:",
}

# URL patterns that are always skipped
BLOCKED_URL_PREFIXES = (
    "chrome://",
    "chrome-extension://",
    "about:",
    "file://",
    "data:",
    "javascript:",
    "blob:",
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE        = LOG_DIR / "host.log"
LOG_MAX_BYTES   = 5 * 1024 * 1024   # 5 MB per log file
LOG_BACKUP_COUNT = 3                 # Keep 3 rotated log files
LOG_LEVEL       = os.environ.get("LOG_LEVEL", "INFO")


# ---------------------------------------------------------------------------
# Message types — protocol between extension and host
# Keep in sync with background.js MESSAGE_TYPES
# ---------------------------------------------------------------------------

class MsgType:
    # Extension → Host
    INGEST  = "ingest"    # Store a new page visit
    SEARCH  = "search"    # Search history
    DELETE  = "delete"    # Delete a single entry by URL
    CLEAR   = "clear"     # Wipe all stored data
    PING    = "ping"      # Health check
    SETTINGS = "settings" # Update settings (expiry days etc.)

    # Host → Extension
    SUCCESS = "success"
    ERROR   = "error"
    RESULTS = "results"
    PONG    = "pong"


# ---------------------------------------------------------------------------
# Settings defaults — written to SETTINGS_FILE on first run
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "expiry_days":    DEFAULT_EXPIRY_DAYS,
    "pause_tracking": False,
    "search_limit":   DEFAULT_SEARCH_LIMIT,
}


# ---------------------------------------------------------------------------
# Sanity check — fail loudly on import if Python version is too old
# ---------------------------------------------------------------------------

if sys.version_info < (3, 9):
    raise RuntimeError(
        f"Python 3.9+ required. Current version: {sys.version}"
    )