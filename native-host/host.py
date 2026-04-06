"""
host.py — Native Messaging host entry point.

This is the process Chrome launches when the extension needs to communicate
with the local Python backend.

Native Messaging protocol (Chrome spec):
- Chrome writes a message to this process's stdin
- Message format: [4-byte little-endian length][JSON bytes]
- This process writes a response to stdout in the same format
- One message in → one message out (request/response)
- Process stays alive until Chrome closes the pipe (extension unloads)

CRITICAL RULES for this file:
1. stdout is OWNED by the protocol — never print() or log to stdout
2. stderr is silently discarded by Chrome — use file logger only
3. Any unhandled exception that reaches main() must be caught and
   returned as an error message — never let the process crash silently
4. Startup must complete fast — Chrome has a connection timeout (~5s)
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Path setup — ensure native-host/ dir is on sys.path when launched by Chrome
# Chrome launches host.py from an arbitrary working directory.
# We must add our own directory explicitly.
# ---------------------------------------------------------------------------

_HOST_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOST_DIR not in sys.path:
    sys.path.insert(0, _HOST_DIR)

# ---------------------------------------------------------------------------
# Now safe to import our modules
# ---------------------------------------------------------------------------

from config import (
    MsgType,
    NATIVE_MESSAGE_MAX_BYTES,
    DEFAULT_SEARCH_LIMIT,
)
from logger import get_logger
from validator import (
    validate_message,
    validate_query,
    validate_ingest_payload,
    validate_expiry_days,
)
from embedder import embedder
from store import store
from privacy import privacy

log = get_logger("host")


# ---------------------------------------------------------------------------
# Native Messaging I/O
# ---------------------------------------------------------------------------

def _read_message() -> Optional[dict]:
    """
    Reads one message from stdin using Chrome's Native Messaging protocol.

    Format: [4 bytes little-endian length][JSON payload]

    Returns parsed dict or None if pipe is closed (Chrome disconnected).
    Raises on malformed input — caller handles.
    """
    # Read 4-byte length prefix
    raw_len = sys.stdin.buffer.read(4)
    if len(raw_len) == 0:
        # Pipe closed — Chrome disconnected cleanly
        log.info("stdin closed — Chrome disconnected")
        return None
    if len(raw_len) != 4:
        raise IOError(f"Expected 4-byte length prefix, got {len(raw_len)} bytes")

    msg_len = struct.unpack("<I", raw_len)[0]  # little-endian unsigned int

    if msg_len > NATIVE_MESSAGE_MAX_BYTES:
        raise ValueError(
            f"Message too large: {msg_len} bytes "
            f"(max {NATIVE_MESSAGE_MAX_BYTES})"
        )

    raw_body = sys.stdin.buffer.read(msg_len)
    if len(raw_body) != msg_len:
        raise IOError(
            f"Expected {msg_len} bytes, got {len(raw_body)}"
        )

    return json.loads(raw_body.decode("utf-8"))


def _write_message(payload: dict) -> None:
    """
    Writes one response to stdout using Chrome's Native Messaging protocol.

    Format: [4 bytes little-endian length][JSON payload]

    CRITICAL: This is the ONLY place we write to stdout.
    Any other stdout write corrupts the protocol.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    length_prefix = struct.pack("<I", len(body))
    sys.stdout.buffer.write(length_prefix + body)
    sys.stdout.buffer.flush()


def _send_success(data: Any = None) -> None:
    _write_message({"type": MsgType.SUCCESS, "data": data})


def _send_error(message: str) -> None:
    log.warning("Sending error to extension: %s", message)
    _write_message({"type": MsgType.ERROR, "error": message})


def _send_results(results: list) -> None:
    _write_message({"type": MsgType.RESULTS, "results": results})


def _send_pong(health: dict) -> None:
    _write_message({"type": MsgType.PONG, "health": health})


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

def _handle_ping() -> None:
    """
    Health check — extension can send PING to verify host is alive.
    Returns combined health from all subsystems.
    """
    health = {
        "host":     "ok",
        "embedder": embedder.is_ready(),
        **store.health(),
        **privacy.health(),
    }
    log.debug("PING received — health: %s", health)
    _send_pong(health)


def _handle_ingest(msg: dict) -> None:
    """
    Stores a new page visit.

    Flow:
    1. Validate + sanitize payload
    2. Privacy check (incognito, pause, blocked domain)
    3. Embed page (title + content → vector)
    4. Upsert into EdgeShard
    """
    # 1. Validate payload
    result = validate_ingest_payload(msg)
    if not result.ok:
        _send_error(f"Invalid ingest payload: {result.error}")
        return

    payload     = result.value
    is_incognito = bool(msg.get("incognito", False))

    # 2. Privacy check
    allowed, reason = privacy.should_ingest(payload.url, is_incognito)
    if not allowed:
        log.debug("Ingest skipped: %s | url=%s", reason, payload.url[:80])
        # Send success (not error) — skipping is expected behaviour
        _send_success({"skipped": True, "reason": reason})
        return

    # 3. Embed
    vector = embedder.embed_page(payload.title, payload.content)
    if vector is None:
        _send_error("Embedding failed — model may not be ready")
        return

    # 4. Store
    store_result = store.upsert(
        url        = payload.url,
        title      = payload.title,
        vector     = vector,
        visited_at = msg.get("visited_at") or time.time(),
    )
    if not store_result.ok:
        _send_error(f"Storage failed: {store_result.error}")
        return

    log.info("Ingested: %s | %r", payload.url[:80], payload.title[:50])
    _send_success({"point_id": store_result.value})


def _handle_search(msg: dict) -> None:
    """
    Semantic search over stored history.

    Flow:
    1. Validate query string
    2. Embed query → vector
    3. Query EdgeShard
    4. Return ranked results
    """
    # 1. Validate
    query_result = validate_query(msg.get("query"))
    if not query_result.ok:
        _send_error(f"Invalid query: {query_result.error}")
        return

    query = query_result.value
    limit = int(msg.get("limit", privacy.search_limit))

    # 2. Embed query
    vector = embedder.embed(query)
    if vector is None:
        _send_error("Query embedding failed")
        return

    # 3. Search
    search_result = store.search(query_vector=vector, limit=limit)
    if not search_result.ok:
        _send_error(f"Search failed: {search_result.error}")
        return

    # 4. Serialize results
    results = [
        {
            "url":        r.url,
            "title":      r.title,
            "visited_at": r.visited_at,
            "score":      r.score,
        }
        for r in search_result.value
    ]

    log.info(
        "Search: %r → %d results",
        query[:50],
        len(results),
    )
    _send_results(results)


def _handle_delete(msg: dict) -> None:
    """
    Deletes a single history entry by URL.
    """
    from validator import validate_url

    url_result = validate_url(msg.get("url"))
    if not url_result.ok:
        _send_error(f"Invalid URL for delete: {url_result.error}")
        return

    result = store.delete_by_url(url_result.value)
    if not result.ok:
        _send_error(f"Delete failed: {result.error}")
        return

    log.info("Deleted: %s", url_result.value[:80])
    _send_success()


def _handle_clear() -> None:
    """
    Wipes all stored history data.
    Irreversible — extension should confirm with user before calling.
    """
    log.warning("CLEAR requested by extension")
    result = store.clear_all()
    if not result.ok:
        _send_error(f"Clear failed: {result.error}")
        return

    _send_success()


def _handle_settings(msg: dict) -> None:
    """
    Updates one or more settings from the extension.
    Accepted keys: pause_tracking, expiry_days, search_limit
    """
    updated = privacy.update_settings(msg)
    _send_success(updated)


# ---------------------------------------------------------------------------
# Message router
# ---------------------------------------------------------------------------

_HANDLERS = {
    MsgType.PING:     lambda msg: _handle_ping(),
    MsgType.INGEST:   _handle_ingest,
    MsgType.SEARCH:   _handle_search,
    MsgType.DELETE:   _handle_delete,
    MsgType.CLEAR:    lambda msg: _handle_clear(),
    MsgType.SETTINGS: _handle_settings,
}


def _route(msg: dict) -> None:
    """
    Routes a validated message to the correct handler.
    Wraps handler call in try/except — no exception escapes to main().
    """
    msg_type = msg.get("type")
    handler  = _HANDLERS.get(msg_type)

    if handler is None:
        _send_error(f"No handler for message type: {msg_type!r}")
        return

    try:
        handler(msg)
    except Exception as exc:
        log.error(
            "Unhandled exception in handler for %r: %s",
            msg_type,
            exc,
            exc_info=True,
        )
        _send_error(f"Internal error: {exc}")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _startup() -> bool:
    """
    Initialises all subsystems in order.
    Returns True if ready to serve requests.

    Order matters:
    1. Privacy  — settings must be loaded before any ingest check
    2. Store    — shard must be open before embedder warms up
    3. Embedder — model load is slow (~2-3s), do last so store is ready
    4. Expiry   — clean up old data after shard is open
    """
    log.info("=== Native host starting ===")

    # 1. Privacy / settings
    if not privacy.load():
        log.error("Failed to load privacy settings")
        return False

    # 2. EdgeShard
    if not store.open():
        log.error("Failed to open EdgeShard")
        return False

    # 3. Embedding model
    if not embedder.load():
        log.error("Failed to load embedding model")
        return False

    # 4. Expiry — delete old entries
    expiry_result = store.run_expiry(privacy.expiry_days)
    if not expiry_result.ok:
        # Non-fatal — log and continue
        log.warning("Expiry run failed: %s", expiry_result.error)

    log.info("=== Native host ready ===")
    return True


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def _shutdown() -> None:
    """
    Gracefully closes all subsystems.
    Called on normal exit and on KeyboardInterrupt.
    """
    log.info("=== Native host shutting down ===")
    store.close()
    log.info("=== Native host stopped ===")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Entry point. Returns exit code.

    Message loop:
    - Read one message
    - Validate structure
    - Route to handler
    - Repeat until pipe closes
    """
    if not _startup():
        # Can't even start — send error and exit
        _send_error("Native host failed to start — check logs")
        return 1

    log.info("Entering message loop")

    while True:
        try:
            msg = _read_message()

            # None = Chrome closed the pipe cleanly
            if msg is None:
                break

            # Top-level structure validation
            validation = validate_message(msg)
            if not validation.ok:
                _send_error(f"Invalid message: {validation.error}")
                continue

            _route(validation.value)

        except KeyboardInterrupt:
            log.info("KeyboardInterrupt received")
            break

        except json.JSONDecodeError as exc:
            log.error("JSON decode error: %s", exc)
            _send_error("Malformed JSON in message")
            continue

        except IOError as exc:
            # Pipe broken — Chrome crashed or extension unloaded
            log.error("Pipe I/O error: %s", exc)
            break

        except Exception as exc:
            # Unexpected — log it, keep running
            log.error(
                "Unexpected error in message loop: %s",
                exc,
                exc_info=True,
            )
            _send_error(f"Unexpected error: {exc}")
            continue

    _shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())