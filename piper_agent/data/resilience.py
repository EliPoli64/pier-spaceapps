"""Retry with exponential backoff and a circuit breaker for live calls.

Used by the data modules when PIER_DEMO_MODE=0 (production path).
In demo mode none of this runs: everything is served from the cache.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger("pier.data.resilience")

FAILURE_THRESHOLD = int(os.environ.get("PIER_CB_THRESHOLD", "3"))
RESET_SECONDS = int(os.environ.get("PIER_CB_RESET", "300"))


class CircuitBreaker:
    """Opens after `threshold` consecutive failures and blocks calls for `reset_seconds`."""

    def __init__(self, name: str = "live", threshold: int = FAILURE_THRESHOLD,
                 reset_seconds: int = RESET_SECONDS):
        self.name = name
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def record_failure(self, reason: str = "") -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.time()
            logger.warning(
                "Circuit breaker '%s' OPENED after %d consecutive failures (%s); using synthetic cache",
                self.name, self.failures, reason,
            )

    def record_success(self) -> None:
        if self.failures or self.opened_at is not None:
            logger.info("Circuit breaker '%s' CLOSED: the live source responded", self.name)
        self.failures = 0
        self.opened_at = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.reset_seconds:
            # Half-open: allow one trial call.
            self.opened_at = None
            self.failures = 0
            return False
        return True


# Circuit breaker shared by every live source in PIER.
live_circuit_breaker = CircuitBreaker()


def call_with_retry(
    func: Callable[[], Any],
    attempts: int = 3,
    backoff_base: float = 2.0,
    circuit_breaker: CircuitBreaker | None = None,
    description: str = "live call",
    sleep: Callable[[float], None] | None = None,
) -> Any:
    """Run `func` up to `attempts` times with exponential backoff.

    Raises RuntimeError if the circuit breaker is open or every attempt fails.
    """
    cb = circuit_breaker if circuit_breaker is not None else live_circuit_breaker
    if cb.is_open():
        raise RuntimeError(f"Circuit breaker '{cb.name}' is open; skipping {description}")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = func()
            cb.record_success()
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("%s: attempt %d/%d failed: %s", description, attempt, attempts, exc)
            if attempt < attempts:
                (sleep or time.sleep)(backoff_base ** attempt)

    cb.record_failure(str(last_error))
    raise RuntimeError(f"{description} failed after {attempts} attempts: {last_error}") from last_error


__all__ = ["CircuitBreaker", "live_circuit_breaker", "call_with_retry"]
