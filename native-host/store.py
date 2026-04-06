"""
store.py — All EdgeShard operations: upsert, search, delete, expiry.

Fixed for qdrant-edge-py 0.6.1:
- VectorDataConfig → EdgeVectorParams
- EdgeConfig(vector_data=...) → EdgeConfig(vectors=...)
- EdgeShard(path, config) → EdgeShard.create(path, config)
- EdgeShard(path) → EdgeShard.load(path)
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from qdrant_edge import (
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeVectorParams,
    FieldCondition,
    Filter,
    Point,
    Query,
    QueryRequest,
    RangeFloat,
    UpdateOperation,
)

from config import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    SHARD_DIR,
    VECTOR_DIMENSION,
    VECTOR_NAME,
    DEFAULT_EXPIRY_DAYS,
)
from embedder import url_to_point_id
from logger import get_logger

log = get_logger("store")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class StoreResult:
    ok:    bool
    value: Any   = None
    error: str   = ""

    @classmethod
    def success(cls, value: Any = None) -> "StoreResult":
        return cls(ok=True, value=value)

    @classmethod
    def fail(cls, reason: str) -> "StoreResult":
        log.error("Store operation failed: %s", reason)
        return cls(ok=False, error=reason)


# ---------------------------------------------------------------------------
# Search result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    url:        str
    title:      str
    visited_at: float
    score:      float


# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------

class Store:
    def __init__(self) -> None:
        self._shard: Optional[EdgeShard] = None
        self._lock  = threading.Lock()
        self._open  = False

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def open(self) -> bool:
        if self._open:
            log.info("Shard already open")
            return True

        log.info("Opening EdgeShard at %s", SHARD_DIR)

        config = EdgeConfig(
            vectors={
                VECTOR_NAME: EdgeVectorParams(
                    size=VECTOR_DIMENSION,
                    distance=Distance.Cosine,
                )
            }
        )

        try:
            shard_has_data = (
                SHARD_DIR.exists() and any(SHARD_DIR.iterdir())
            )

            if shard_has_data:
                self._shard = EdgeShard.load(str(SHARD_DIR))
                log.info("Loaded existing EdgeShard")
            else:
                self._shard = EdgeShard.create(str(SHARD_DIR), config)
                log.info("Created new EdgeShard")

            self._open = True
            log.info("EdgeShard opened successfully")
            return True

        except Exception as exc:
            log.error("Failed to open EdgeShard: %s", exc, exc_info=True)
            return False

    def close(self) -> None:
        if not self._open or self._shard is None:
            return
        try:
            self._shard.close()
            self._open  = False
            self._shard = None
            log.info("EdgeShard closed cleanly")
        except Exception as exc:
            log.error("Error closing EdgeShard: %s", exc, exc_info=True)

    def is_open(self) -> bool:
        return self._open and self._shard is not None

    # -----------------------------------------------------------------------
    # Upsert
    # -----------------------------------------------------------------------

    def upsert(
        self,
        url:        str,
        title:      str,
        vector:     list[float],
        visited_at: Optional[float] = None,
    ) -> StoreResult:
        if not self.is_open():
            return StoreResult.fail("Shard is not open")

        point_id   = url_to_point_id(url)
        visited_at = visited_at or time.time()

        payload = {
            "url":        url,
            "title":      title,
            "visited_at": visited_at,
        }

        point = Point(
            id=point_id,
            vector={VECTOR_NAME: vector},
            payload=payload,
        )

        try:
            with self._lock:
                self._shard.update(
                    UpdateOperation.upsert_points([point])
                )
            log.debug("Upserted: %s | %r", url[:80], title[:50])
            return StoreResult.success(point_id)

        except Exception as exc:
            return StoreResult.fail(f"Upsert failed: {exc}")

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        limit:        int = DEFAULT_SEARCH_LIMIT,
    ) -> StoreResult:
        if not self.is_open():
            return StoreResult.fail("Shard is not open")

        limit = min(limit, MAX_SEARCH_LIMIT)

        try:
            with self._lock:
                raw_results = self._shard.query(
                    QueryRequest(
                        query=Query.Nearest(
                            query_vector,
                            using=VECTOR_NAME,
                        ),
                        limit=limit,
                        with_vector=False,
                        with_payload=True,
                    )
                )

            results = []
            for r in raw_results:
                payload = r.payload or {}
                results.append(
                    SearchResult(
                        url        = payload.get("url", ""),
                        title      = payload.get("title", ""),
                        visited_at = payload.get("visited_at", 0.0),
                        score      = round(float(r.score), 4),
                    )
                )

            log.debug("Search returned %d results", len(results))
            return StoreResult.success(results)

        except Exception as exc:
            return StoreResult.fail(f"Search failed: {exc}")

    # -----------------------------------------------------------------------
    # Delete single entry
    # -----------------------------------------------------------------------

    def delete_by_url(self, url: str) -> StoreResult:
        if not self.is_open():
            return StoreResult.fail("Shard is not open")

        point_id = url_to_point_id(url)

        try:
            with self._lock:
                self._shard.update(
                    UpdateOperation.delete_points([point_id])
                )
            log.info("Deleted: %s", url[:80])
            return StoreResult.success(point_id)

        except Exception as exc:
            return StoreResult.fail(f"Delete failed: {exc}")

    # -----------------------------------------------------------------------
    # Clear all
    # -----------------------------------------------------------------------

    def clear_all(self) -> StoreResult:
        if not self.is_open():
            return StoreResult.fail("Shard is not open")

        log.warning("clear_all() — wiping all history data")

        try:
            with self._lock:
                self.close()
                shutil.rmtree(str(SHARD_DIR), ignore_errors=True)
                SHARD_DIR.mkdir(parents=True, exist_ok=True)
                success = self.open()
                if not success:
                    return StoreResult.fail("Failed to reopen shard after clear")

            log.info("All data cleared")
            return StoreResult.success()

        except Exception as exc:
            return StoreResult.fail(f"clear_all failed: {exc}")

    # -----------------------------------------------------------------------
    # Expiry
    # -----------------------------------------------------------------------

    def run_expiry(self, expiry_days: int = DEFAULT_EXPIRY_DAYS) -> StoreResult:
        if expiry_days <= 0:
            log.info("Expiry disabled")
            return StoreResult.success()

        if not self.is_open():
            return StoreResult.fail("Shard is not open")

        cutoff = time.time() - (expiry_days * 86400)
        log.info("Running expiry: cutoff=%.0f (%d days)", cutoff, expiry_days)

        try:
            with self._lock:
                self._shard.update(
                    UpdateOperation.delete_points_by_filter(
                        Filter(
                            must=[
                                FieldCondition(
                                    key="visited_at",
                                    range=RangeFloat(lt=cutoff),
                                )
                            ]
                        )
                    )
                )
            log.info("Expiry complete")
            return StoreResult.success()

        except Exception as exc:
            return StoreResult.fail(f"Expiry failed: {exc}")

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    def health(self) -> dict:
        return {
            "shard_open": self.is_open(),
            "shard_dir":  str(SHARD_DIR),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

store = Store()