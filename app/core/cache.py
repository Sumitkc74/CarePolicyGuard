import time
import re
from typing import Any, Dict, Optional, Tuple, List
from threading import Lock

class CacheSecurityException(Exception):
    """Raised when an attempt is made to cache sensitive Protected Health Information (PHI)."""
    pass

class PolicyCacheManager:
    """
    Enterprise-grade Thread-Safe In-Memory Cache-Aside Manager with TTL,
    explicit invalidation, hit/miss metrics, and strict HIPAA PHI guardrails.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._lock = Lock()
        self._default_ttl = default_ttl_seconds
        # Storage format: key -> (value, expiry_timestamp_float)
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._hits: int = 0
        self._misses: int = 0

        # Patterns that strictly forbid caching to prevent HIPAA PHI leaks
        self._phi_forbidden_patterns = [
            r"(?i)\bpatient\b",
            r"(?i)\bpt-\b",
            r"(?i)\bmrn\b",
            r"(?i)\bssn\b",
            r"(?i)\bdob\b",
            r"(?i)\behr\b",
            r"(?i)\bnarrative\b",
            r"(?i)\bclinical_note\b"
        ]

    def _assert_cache_key_safe(self, key: str) -> None:
        """
        HIPAA Safe Harbor Guardrail:
        Strictly prevents caching any key that contains patient identifiers or EHR data.
        """
        for pattern in self._phi_forbidden_patterns:
            if re.search(pattern, key):
                raise CacheSecurityException(
                    f"Security violation: Caching forbidden for sensitive or PHI-related key pattern: '{key}'"
                )

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves a value from cache if present and not expired.
        Increments hit or miss counter.
        """
        self._assert_cache_key_safe(key)
        now = time.time()
        with self._lock:
            if key in self._store:
                val, expires_at = self._store[key]
                if expires_at > now:
                    self._hits += 1
                    return val
                else:
                    # Expired, clean up
                    del self._store[key]

            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Stores a value with an associated TTL.
        """
        self._assert_cache_key_safe(key)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl
        with self._lock:
            self._store[key] = (value, expires_at)

    def invalidate(self, key: str) -> bool:
        """
        Invalidates a specific cache key. Returns True if key was present.
        """
        with self._lock:
            return self._store.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Invalidates all keys starting with the given prefix. Returns count of deleted keys.
        """
        with self._lock:
            to_remove = [k for k in self._store.keys() if k.startswith(prefix)]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)

    def clear(self) -> None:
        """
        Clears the entire cache store and resets metrics.
        """
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def get_metrics(self) -> Dict[str, Any]:
        """
        Returns telemetry metrics for monitoring cache efficiency.
        """
        now = time.time()
        with self._lock:
            active_keys = sum(1 for _, exp in self._store.values() if exp > now)
            total = self._hits + self._misses
            hit_ratio = round(self._hits / total, 4) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total,
                "hit_ratio": hit_ratio,
                "active_cached_keys": active_keys,
                "default_ttl_seconds": self._default_ttl
            }

# Singleton instance for CMS policies and clinical criteria
policy_cache = PolicyCacheManager(default_ttl_seconds=3600)

