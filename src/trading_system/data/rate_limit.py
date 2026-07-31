"""YFinance Rate Limiter with circuit breaker, backoff, and per-symbol failure tracking (DD, §4.1).

Adapted from TIP/python/ingestion/rate_limit.py.
Replaces the simple sliding-window RateLimiter in acquisition.py.

Features:
- Configurable delay with jitter
- Sliding window request limit
- Exponential backoff with retries
- Circuit breaker (closed/open/half-open)
- Per-symbol failure reporting
- Environment variable configuration
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RateLimitResult(Generic[T]):
    """Result of a rate-limited operation."""
    data: T | None = None
    error: str | None = None
    attempts: int = 0
    total_wait_seconds: float = 0.0


@dataclass
class SymbolFailure:
    """Per-symbol failure record."""
    symbol: str
    error: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class YFinanceRateLimiter:
    """Configurable rate limiter for yfinance requests.

    Env vars:
        YFINANCE_MIN_DELAY: minimum delay between requests in seconds (default: 2.0)
        YFINANCE_MAX_DELAY: maximum delay (jitter upper bound) in seconds (default: 5.0)
        YFINANCE_MAX_REQUESTS: max requests per sliding window (default: 100)
        YFINANCE_WINDOW_SECONDS: sliding window size in seconds (default: 3600)
        YFINANCE_MAX_RETRIES: max retry attempts per symbol (default: 3)
        YFINANCE_BACKOFF_BASE: exponential backoff base in seconds (default: 2.0)
        YFINANCE_BACKOFF_MAX: max backoff wait in seconds (default: 60.0)
        YFINANCE_CIRCUIT_THRESHOLD: consecutive failures to open circuit (default: 5)
        YFINANCE_CIRCUIT_RESET_SECONDS: seconds before half-open attempt (default: 120)
    """

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_requests: int = 100,
        window_seconds: int = 3600,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
        circuit_threshold: int = 5,
        circuit_reset_seconds: int = 120,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.circuit_threshold = circuit_threshold
        self.circuit_reset_seconds = circuit_reset_seconds

        self._request_timestamps: list[float] = []
        self._consecutive_failures = 0
        self._circuit_state = CircuitState.CLOSED
        self._circuit_opened_at: float | None = None
        self._failures: list[SymbolFailure] = []
        self._last_request_time: float = 0.0

    @classmethod
    def from_env(cls) -> YFinanceRateLimiter:
        return cls(
            min_delay=float(os.getenv("YFINANCE_MIN_DELAY", "2.0")),
            max_delay=float(os.getenv("YFINANCE_MAX_DELAY", "5.0")),
            max_requests=int(os.getenv("YFINANCE_MAX_REQUESTS", "100")),
            window_seconds=int(os.getenv("YFINANCE_WINDOW_SECONDS", "3600")),
            max_retries=int(os.getenv("YFINANCE_MAX_RETRIES", "3")),
            backoff_base=float(os.getenv("YFINANCE_BACKOFF_BASE", "2.0")),
            backoff_max=float(os.getenv("YFINANCE_BACKOFF_MAX", "60.0")),
            circuit_threshold=int(os.getenv("YFINANCE_CIRCUIT_THRESHOLD", "5")),
            circuit_reset_seconds=int(os.getenv("YFINANCE_CIRCUIT_RESET_SECONDS", "120")),
        )

    @property
    def failures(self) -> list[SymbolFailure]:
        return list(self._failures)

    @property
    def circuit_state(self) -> CircuitState:
        return self._circuit_state

    def _wait_min_delay(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_delay:
            wait = self.min_delay - elapsed
            time.sleep(wait)
        self._last_request_time = time.monotonic()

    def _apply_jitter(self) -> None:
        jitter = random.uniform(0, self.max_delay - self.min_delay)
        if jitter > 0:
            time.sleep(jitter)

    def _prune_window(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]

    def _check_window_limit(self) -> None:
        self._prune_window()
        while len(self._request_timestamps) >= self.max_requests:
            oldest = min(self._request_timestamps)
            wait = oldest + self.window_seconds - time.monotonic()
            if wait > 0:
                time.sleep(min(wait, self.window_seconds))
            self._prune_window()

    def _check_circuit(self) -> bool:
        if self._circuit_state == CircuitState.OPEN:
            if self._circuit_opened_at is None:
                self._circuit_state = CircuitState.HALF_OPEN
                return True
            elapsed = time.monotonic() - self._circuit_opened_at
            if elapsed >= self.circuit_reset_seconds:
                self._circuit_state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_state = CircuitState.CLOSED
        self._circuit_opened_at = None

    def _record_failure(self, symbol: str, error: str) -> None:
        self._consecutive_failures += 1
        self._failures.append(SymbolFailure(symbol=symbol, error=error))
        if self._consecutive_failures >= self.circuit_threshold:
            self._circuit_state = CircuitState.OPEN
            self._circuit_opened_at = time.monotonic()

    def _compute_backoff(self, attempt: int) -> float:
        wait = self.backoff_base ** attempt
        return min(wait, self.backoff_max)

    def execute(self, symbol: str, func: Callable[[], T]) -> RateLimitResult[T]:
        """Execute a function with rate limiting, retries, and circuit breaker.

        Args:
            symbol: The symbol being fetched (for failure reporting).
            func: Callable that performs the actual fetch.

        Returns:
            RateLimitResult with data or error.
        """
        total_wait = 0.0
        last_error: str | None = None

        for attempt in range(self.max_retries + 1):
            if not self._check_circuit():
                return RateLimitResult(
                    error="Circuit breaker is open — too many consecutive failures",
                    attempts=attempt,
                    total_wait_seconds=total_wait,
                )

            self._check_window_limit()
            self._wait_min_delay()
            self._apply_jitter()

            self._request_timestamps.append(time.monotonic())

            try:
                data = func()
                self._record_success()
                return RateLimitResult(
                    data=data,
                    attempts=attempt + 1,
                    total_wait_seconds=total_wait,
                )
            except Exception as e:
                last_error = str(e)
                self._record_failure(symbol, last_error)

                if attempt < self.max_retries:
                    backoff = self._compute_backoff(attempt + 1)
                    time.sleep(backoff)
                    total_wait += backoff

        return RateLimitResult(
            error=last_error,
            attempts=self.max_retries + 1,
            total_wait_seconds=total_wait,
        )

    def reset(self) -> None:
        """Reset all state (for testing)."""
        self._request_timestamps.clear()
        self._consecutive_failures = 0
        self._circuit_state = CircuitState.CLOSED
        self._circuit_opened_at = None
        self._failures.clear()
        self._last_request_time = 0.0
