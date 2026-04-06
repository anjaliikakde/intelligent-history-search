"""
validator.py — Input sanitization and validation.

Every piece of data entering the system passes through here first.
Nothing else should trust raw input directly.

Design principle:
- Never raise exceptions to callers — return a result object.
- Sanitize (fix what you can), then validate (reject what you can't fix).
- Be strict on types, lenient on content (we're not a firewall).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any, Optional

from config import (
    MAX_URL_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_CONTENT_LENGTH,
    MAX_QUERY_LENGTH,
    MIN_QUERY_LENGTH,
    BLOCKED_URL_PREFIXES,
    BLOCKED_DOMAINS,
    MsgType,
)
from logger import get_logger

log = get_logger("validator")


# ---------------------------------------------------------------------------
# Result type — callers check .ok before using .value
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    ok:    bool
    value: Any            # sanitized value if ok=True
    error: str = ""       # human-readable reason if ok=False

    @classmethod
    def success(cls, value: Any) -> "ValidationResult":
        return cls(ok=True, value=value)

    @classmethod
    def fail(cls, reason: str) -> "ValidationResult":
        log.warning("Validation failed: %s", reason)
        return cls(ok=False, value=None, error=reason)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def validate_url(raw: Any) -> ValidationResult:
    """
    Accepts a raw value, returns a sanitized URL string or failure.
    Rules:
    - Must be a non-empty string
    - Must not exceed MAX_URL_LENGTH
    - Must not start with a blocked prefix
    - Must have a valid scheme (http / https only)
    - Must have a non-empty netloc (domain)
    """
    if not isinstance(raw, str):
        return ValidationResult.fail(f"URL must be a string, got {type(raw).__name__}")

    url = raw.strip()

    if not url:
        return ValidationResult.fail("URL is empty")

    if len(url) > MAX_URL_LENGTH:
        return ValidationResult.fail(
            f"URL too long: {len(url)} chars (max {MAX_URL_LENGTH})"
        )

    # Block internal / non-http schemes
    for prefix in BLOCKED_URL_PREFIXES:
        if url.startswith(prefix):
            return ValidationResult.fail(f"Blocked URL prefix: {prefix}")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        return ValidationResult.fail(f"URL parse error: {exc}")

    if parsed.scheme not in ("http", "https"):
        return ValidationResult.fail(f"Unsupported scheme: {parsed.scheme!r}")

    netloc = parsed.netloc.lower().split(":")[0]  # strip port
    if not netloc:
        return ValidationResult.fail("URL has no domain")

    if netloc in BLOCKED_DOMAINS:
        return ValidationResult.fail(f"Blocked domain: {netloc}")

    return ValidationResult.success(url)


# ---------------------------------------------------------------------------
# Title validation
# ---------------------------------------------------------------------------

def validate_title(raw: Any) -> ValidationResult:
    """
    Sanitizes a page title.
    - Coerces to string
    - Strips whitespace and control characters
    - Truncates to MAX_TITLE_LENGTH
    - Falls back to empty string (not a hard failure — title is optional)
    """
    if raw is None:
        return ValidationResult.success("")

    title = str(raw).strip()

    # Strip control characters (tabs, newlines, nulls etc.)
    title = re.sub(r"[\x00-\x1f\x7f]", " ", title)

    # Collapse multiple spaces
    title = re.sub(r" {2,}", " ", title).strip()

    # Truncate
    if len(title) > MAX_TITLE_LENGTH:
        title = title[:MAX_TITLE_LENGTH].rstrip()

    return ValidationResult.success(title)


# ---------------------------------------------------------------------------
# Page content validation
# ---------------------------------------------------------------------------

def validate_content(raw: Any) -> ValidationResult:
    """
    Sanitizes extracted page body text.
    - Coerces to string
    - Strips HTML tags (basic — content.js should already strip them)
    - Strips control characters
    - Truncates to MAX_CONTENT_LENGTH
    """
    if raw is None:
        return ValidationResult.success("")

    content = str(raw).strip()

    # Strip any residual HTML tags
    content = re.sub(r"<[^>]+>", " ", content)

    # Strip control characters
    content = re.sub(r"[\x00-\x1f\x7f]", " ", content)

    # Collapse whitespace
    content = re.sub(r"\s+", " ", content).strip()

    # Truncate
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH].rstrip()

    return ValidationResult.success(content)


# ---------------------------------------------------------------------------
# Search query validation
# ---------------------------------------------------------------------------

def validate_query(raw: Any) -> ValidationResult:
    """
    Validates a user search query.
    - Must be a string
    - Stripped length must be >= MIN_QUERY_LENGTH
    - Truncated to MAX_QUERY_LENGTH
    """
    if not isinstance(raw, str):
        return ValidationResult.fail(
            f"Query must be a string, got {type(raw).__name__}"
        )

    query = raw.strip()

    if len(query) < MIN_QUERY_LENGTH:
        return ValidationResult.fail("Query is empty")

    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH].rstrip()

    # Strip control characters
    query = re.sub(r"[\x00-\x1f\x7f]", " ", query).strip()

    if not query:
        return ValidationResult.fail("Query is empty after sanitization")

    return ValidationResult.success(query)


# ---------------------------------------------------------------------------
# Expiry days validation (for settings)
# ---------------------------------------------------------------------------

def validate_expiry_days(raw: Any) -> ValidationResult:
    """
    Validates the auto-expiry setting.
    - Must be an integer
    - 0 = disabled
    - Max 3650 (10 years — effectively permanent)
    """
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return ValidationResult.fail(f"expiry_days must be an integer, got {raw!r}")

    if days < 0:
        return ValidationResult.fail("expiry_days cannot be negative")

    if days > 3650:
        return ValidationResult.fail("expiry_days cannot exceed 3650 (10 years)")

    return ValidationResult.success(days)


# ---------------------------------------------------------------------------
# Full incoming message validation
# ---------------------------------------------------------------------------

def validate_message(raw: Any) -> ValidationResult:
    """
    Top-level validator for every message arriving from the extension.
    Checks structure and type field before routing to specific validators.
    """
    if not isinstance(raw, dict):
        return ValidationResult.fail(
            f"Message must be a JSON object, got {type(raw).__name__}"
        )

    msg_type = raw.get("type")
    if not isinstance(msg_type, str) or not msg_type:
        return ValidationResult.fail("Message missing required 'type' field")

    valid_types = {
        MsgType.INGEST,
        MsgType.SEARCH,
        MsgType.DELETE,
        MsgType.CLEAR,
        MsgType.PING,
        MsgType.SETTINGS,
    }
    if msg_type not in valid_types:
        return ValidationResult.fail(f"Unknown message type: {msg_type!r}")

    return ValidationResult.success(raw)


# ---------------------------------------------------------------------------
# Ingest payload validation — used by host.py for INGEST messages
# ---------------------------------------------------------------------------

@dataclass
class IngestPayload:
    url:     str
    title:   str
    content: str


def validate_ingest_payload(raw: dict) -> ValidationResult:
    """
    Validates and sanitizes a full ingest payload.
    Returns an IngestPayload on success.
    """
    url_result     = validate_url(raw.get("url"))
    title_result   = validate_title(raw.get("title"))
    content_result = validate_content(raw.get("content"))

    if not url_result.ok:
        return ValidationResult.fail(f"Invalid URL: {url_result.error}")

    # Title and content are optional — failures are non-fatal
    title   = title_result.value   if title_result.ok   else ""
    content = content_result.value if content_result.ok else ""

    return ValidationResult.success(
        IngestPayload(
            url=url_result.value,
            title=title,
            content=content,
        )
    )