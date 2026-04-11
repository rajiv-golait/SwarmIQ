"""Simple disk-backed query result cache.

Prevents redundant DDG + Jina calls for the same query.
Cache key: SHA-256 of normalized query string.
TTL: 24 hours (configurable).
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("SEARCH_CACHE_DIR", "./search_cache"))
CACHE_TTL  = int(os.getenv("SEARCH_CACHE_TTL_HOURS", "24")) * 3600


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def get(query: str) -> list[dict] | None:
    """Return cached results if fresh, else None."""
    path = _cache_path(_cache_key(query))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data["timestamp"] > CACHE_TTL:
            path.unlink()
            return None
        logger.debug(f"Cache hit: {query[:50]}")
        return data["results"]
    except Exception:
        return None


def put(query: str, results: list[dict]) -> None:
    """Write results to cache."""
    try:
        path = _cache_path(_cache_key(query))
        path.write_text(json.dumps({
            "timestamp": time.time(),
            "query":     query,
            "results":   results,
        }))
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")
