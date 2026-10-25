import time
from typing import Any, Dict, Optional, Tuple, Callable
from collections import defaultdict
from threading import Lock

class IdempotencyRecord:
    def __init__(self, payload: Any, status_code: int = 200, headers: Optional[Dict[str, str]] = None, ttl_seconds: int = 86400):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class IdempotencyEngine:
    """
    Enterprise Idempotency & Distributed Lock Engine.
    Implements IETF HTTP Idempotency Key specification to prevent duplicate claim creation,
    race conditions, and accidental re-adjudication during EHR network retries.
    """

    def __init__(self, default_ttl_seconds: int = 86400):
        self._master_lock = Lock()
        self._default_ttl = default_ttl_seconds
        self._completed_records: Dict[str, IdempotencyRecord] = {}
        self._in_flight_locks: Dict[str, Lock] = defaultdict(Lock)

    def get_existing(self, idempotency_key: str) -> Optional[Tuple[Any, int, Dict[str, str]]]:
        """
        Returns (payload, status_code, headers) if an unexpired record exists for this key.
        """
        now = time.time()
        with self._master_lock:
            rec = self._completed_records.get(idempotency_key)
            if rec:
                if rec.is_expired():
                    del self._completed_records[idempotency_key]
                    return None
                return rec.payload, rec.status_code, rec.headers
            return None

    def store_result(
        self,
        idempotency_key: str,
        payload: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Persists a completed response for replay.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        with self._master_lock:
            self._completed_records[idempotency_key] = IdempotencyRecord(
                payload=payload,
                status_code=status_code,
                headers=headers,
                ttl_seconds=ttl
            )

    def execute_idempotent(
        self,
        idempotency_key: str,
        action: Callable[[], Tuple[Any, int, Optional[Dict[str, str]]]],
        ttl_seconds: Optional[int] = None
    ) -> Tuple[Any, int, Dict[str, str], bool]:
        """
        Executes an action with full race-condition and replay protection:
        1. If already completed, returns (payload, status_code, headers, is_replay=True).
        2. If another concurrent thread is already processing the same key, waits for it
           and returns that result rather than running duplicate clinical logic.
        3. If new, acquires lock, computes result, stores it, and returns (payload, status_code, headers, is_replay=False).
        """
        existing = self.get_existing(idempotency_key)
        if existing:
            payload, status_code, headers = existing
            return payload, status_code, headers, True

        # Acquire lock for this specific key
        with self._master_lock:
            key_lock = self._in_flight_locks[idempotency_key]

        with key_lock:
            # Double-check if another worker just finished while we were waiting
            existing_after_wait = self.get_existing(idempotency_key)
            if existing_after_wait:
                payload, status_code, headers = existing_after_wait
                return payload, status_code, headers, True

            # Execute the underlying action
            payload, status_code, custom_headers = action()
            headers = custom_headers or {}
            self.store_result(
                idempotency_key=idempotency_key,
                payload=payload,
                status_code=status_code,
                headers=headers,
                ttl_seconds=ttl_seconds
            )
            return payload, status_code, headers, False

    def clear(self) -> None:
        """Clears all records (used for test teardown)."""
        with self._master_lock:
            self._completed_records.clear()
            self._in_flight_locks.clear()

# Global singleton engine
idempotency_engine = IdempotencyEngine()

