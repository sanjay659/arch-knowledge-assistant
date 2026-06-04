"""
Response Cache — Avoid repeated LLM calls for same questions
==============================================================

LAYMAN:
    3 architects ask "Explain DataStories architecture" in one day.
    
    Without cache: 3 full pipeline runs (3x embedding + 3x GPT calls)
    With cache:    1 full run + 2 instant responses from memory
    
    Same answer. 67% cost savings. Instant response for cached queries.

NOTE: This is in-memory cache — lost on restart.
Phase 3: Use Redis for persistent caching across restarts.
"""

import hashlib
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Simple in-memory cache with TTL (time-to-live).
    
    Cache key = hash of (question + client)
    Cache value = full query response
    TTL = 1 hour (answers are valid for 1 hour)
    Max entries = 200 (prevents memory bloat)
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 200):
        """
        Args:
            ttl_seconds: How long cached answers stay valid (default 1 hour)
            max_entries: Maximum cached entries (oldest evicted when full)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0
        logger.info(f"ResponseCache initialized: TTL={ttl_seconds}s, max={max_entries}")

    def _make_key(self, question: str, client: Optional[str] = None) -> str:
        """Deterministic cache key from question + client."""
        raw = f"{question.lower().strip()}|{client or 'all'}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, question: str, client: Optional[str] = None) -> Optional[Dict]:
        """
        Check cache. Returns cached response or None.
        
        LAYMAN:
            "Have I answered this exact question before?"
            If yes and answer is less than 1 hour old → return it instantly
            If no → return None (caller must run full pipeline)
        """
        key = self._make_key(question, client)

        if key in self._cache:
            entry = self._cache[key]
            age = time.time() - entry["timestamp"]

            if age < self.ttl:
                self.hits += 1
                logger.info(f"  Cache HIT (age: {age:.0f}s) — returning cached response")
                return entry["response"]
            else:
                # Expired — remove it
                del self._cache[key]
                logger.debug(f"  Cache EXPIRED (age: {age:.0f}s)")

        self.misses += 1
        logger.debug("  Cache MISS")
        return None

    def set(self, question: str, response: Dict, client: Optional[str] = None):
        """Store a response in cache."""
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_entries:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]
            logger.debug("  Cache full — evicted oldest entry")

        key = self._make_key(question, client)
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }
        logger.debug(f"  Cached response (total: {len(self._cache)} entries)")

    def invalidate_all(self):
        """Clear entire cache. Call after re-ingestion."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"  Cache cleared ({count} entries removed)")

    def get_stats(self) -> Dict[str, Any]:
        """Cache statistics for monitoring."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "entries": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl,
        }