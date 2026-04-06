"""
embedder.py — FastEmbed wrapper for local, offline text embedding.

Design decisions:
- Model is loaded ONCE at startup, not per request (expensive operation ~2-3s)
- local_files_only=True — no network calls ever, even accidentally
- Returns None on failure — callers decide what to do, no silent crashes
- Thread-safe: FastEmbed models are stateless after loading
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional

from fastembed import TextEmbedding

from config import (
    EMBEDDING_MODEL_NAME,
    MODELS_DIR,
    VECTOR_DIMENSION,
)
from logger import get_logger

log = get_logger("embedder")


# ---------------------------------------------------------------------------
# Embedder class
# ---------------------------------------------------------------------------

class Embedder:
    """
    Wraps FastEmbed TextEmbedding model.
    
    Usage:
        embedder = Embedder()
        embedder.load()                    # call once at startup
        vector = embedder.embed("hello")   # call per request
    """

    def __init__(self) -> None:
        self._model: Optional[TextEmbedding] = None
        self._loaded: bool = False

    # -----------------------------------------------------------------------
    # Load model
    # -----------------------------------------------------------------------

    def load(self) -> bool:
        """
        Loads the embedding model from local cache.
        
        Returns True on success, False on failure.
        Call this once at startup — not per request.
        
        Why local_files_only=True?
        If the model isn't cached yet, FastEmbed would silently download it.
        We never want network calls in production — model must be
        pre-downloaded by the install script.
        """
        if self._loaded:
            log.info("Model already loaded, skipping")
            return True

        log.info(
            "Loading embedding model: %s from %s",
            EMBEDDING_MODEL_NAME,
            MODELS_DIR,
        )

        start = time.perf_counter()

        try:
            self._model = TextEmbedding(
                model_name=EMBEDDING_MODEL_NAME,
                cache_dir=str(MODELS_DIR),
                local_files_only=True,   # never hit the network
            )

            # Warm up — first inference is always slower due to JIT compilation
            # Do it now so the first real request is fast
            _ = list(self._model.embed(["warmup"]))

            elapsed = time.perf_counter() - start
            log.info("Model loaded and warmed up in %.2fs", elapsed)
            self._loaded = True
            return True

        except Exception as exc:
            log.error(
                "Failed to load model %s: %s",
                EMBEDDING_MODEL_NAME,
                exc,
                exc_info=True,
            )
            self._model = None
            self._loaded = False
            return False

    # -----------------------------------------------------------------------
    # Embed single text
    # -----------------------------------------------------------------------

    def embed(self, text: str) -> Optional[list[float]]:
        """
        Converts text to a vector embedding.

        Args:
            text: Any non-empty string.

        Returns:
            List of floats (length = VECTOR_DIMENSION) or None on failure.

        Why list[float] and not numpy array?
        EdgeShard expects plain Python lists. Avoids numpy dependency
        bleeding into store.py.
        """
        if not self._loaded or self._model is None:
            log.error("embed() called before load() — model not ready")
            return None

        if not text or not text.strip():
            log.warning("embed() called with empty text")
            return None

        try:
            # FastEmbed.embed() is a generator — consume with list()
            vectors = list(self._model.embed([text]))

            if not vectors:
                log.error("FastEmbed returned empty result for text: %r", text[:50])
                return None

            vector = vectors[0].tolist()

            # Sanity check — wrong dimension means model mismatch
            if len(vector) != VECTOR_DIMENSION:
                log.error(
                    "Vector dimension mismatch: expected %d, got %d",
                    VECTOR_DIMENSION,
                    len(vector),
                )
                return None

            return vector

        except Exception as exc:
            log.error("Embedding failed: %s", exc, exc_info=True)
            return None

    # -----------------------------------------------------------------------
    # Embed for ingestion — combines title + content for richer vector
    # -----------------------------------------------------------------------

    def embed_page(self, title: str, content: str) -> Optional[list[float]]:
        """
        Builds a single embedding from page title + content.
        
        Why combine them?
        Title alone loses context. Content alone loses the summary.
        Prepending title gives the model a strong semantic anchor.
        
        Format: "[title] [content]" — simple, effective.
        """
        title   = (title or "").strip()
        content = (content or "").strip()

        if not title and not content:
            log.warning("embed_page() called with both title and content empty")
            return None

        # Title gets double weight by appearing first and being short
        combined = f"{title} {content}".strip()

        log.debug(
            "Embedding page: title=%r, content_len=%d, combined_len=%d",
            title[:50],
            len(content),
            len(combined),
        )

        return self.embed(combined)

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------

    def is_ready(self) -> bool:
        """Returns True if model is loaded and ready to embed."""
        return self._loaded and self._model is not None

    # -----------------------------------------------------------------------
    # Download model (called by install script, not by host.py)
    # -----------------------------------------------------------------------

    @staticmethod
    def download_model() -> bool:
        """
        Downloads the embedding model to MODELS_DIR.
        Called once by install.sh / install.bat — never at runtime.

        Why separate from load()?
        load() uses local_files_only=True — it will fail if model isn't
        cached. This method is the one-time download step.
        """
        log.info("Downloading model: %s", EMBEDDING_MODEL_NAME)
        try:
            # Without local_files_only — will download if not cached
            model = TextEmbedding(
                model_name=EMBEDDING_MODEL_NAME,
                cache_dir=str(MODELS_DIR),
            )
            # Trigger actual download by running one inference
            _ = list(model.embed(["download test"]))
            log.info("Model downloaded successfully to %s", MODELS_DIR)
            return True
        except Exception as exc:
            log.error("Model download failed: %s", exc, exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Text fingerprint — used by store.py to generate stable point IDs from URLs
# ---------------------------------------------------------------------------

def url_to_point_id(url: str) -> str:
    """
    Converts a URL to a stable, unique string ID for EdgeShard.
    
    Why not use the URL directly?
    EdgeShard point IDs must be either unsigned integers or UUIDs.
    URLs are arbitrary strings — we hash them to get a stable UUID-like ID.
    
    Uses SHA-256, truncated to 128 bits, formatted as UUID.
    Same URL always produces same ID — safe to call on re-visits (upsert).
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()

    # Format first 32 hex chars as UUID (8-4-4-4-12)
    return (
        f"{digest[0:8]}-{digest[8:12]}-"
        f"{digest[12:16]}-{digest[16:20]}-"
        f"{digest[20:32]}"
    )


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere
# ---------------------------------------------------------------------------

embedder = Embedder()