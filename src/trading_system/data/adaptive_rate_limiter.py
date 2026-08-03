"""Adaptive rate limiter for web scraping and API calls.

Provides optimal rate limiting based on:
- Network latency measurement (auto-tune delay)
- Sliding window request limit
- Exponential backoff with jitter
- Circuit breaker (closed/open/half-open)
- Per-symbol failure tracking
- Adaptive delay: speeds up when successful, slows down on errors

Env vars:
    RATE_LIMIT_MIN_DELAY: minimum delay between requests (default: 0.3)
    RATE_LIMIT_MAX_DELAY: maximum delay (default: 2.0)
    RATE_LIMIT_MAX_REQUESTS: max requests per window (default: 2000)
    RATE_LIMIT_WINDOW_SECONDS: sliding window size (default: 3600)
    RATE_LIMIT_MAX_RETRIES: max retry attempts (default: 3)
    RATE_LIMIT_BACKOFF_BASE: exponential backoff base (default: 1.5)
    RATE_LIMIT_BACKOFF_MAX: max backoff wait (default: 30.0)
    RATE_LIMIT_CIRCUIT_THRESHOLD: consecutive failures to open circuit (default: 10)
    RATE_LIMIT_CIRCUIT_RESET_SECONDS: seconds before half-open (default: 60)
    RATE_LIMIT_ADAPTIVE: enable adaptive delay tuning (default: true)
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
    latency: float = 0.0


@dataclass
class SymbolFailure:
    """Per-symbol failure record."""
    symbol: str
    error: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class AdaptiveRateLimiter:
    """Adaptive rate limiter with circuit breaker, backoff, and auto-tuning.

    Features:
    - Configurable delay with random jitter (human-like)
    - Sliding window request limit
    - Exponential backoff with retries
    - Circuit breaker (closed/open/half-open)
    - Per-symbol failure reporting
    - Adaptive delay: measures latency and adjusts min_delay dynamically
    - Environment variable configuration

    Adaptive tuning logic:
    - On success: if latency < min_delay, can safely reduce delay
    - On failure: increase delay (up to max_delay)
    - Target: keep delay at ~2x the observed p95 latency
    """

    def __init__(
        self,
        min_delay: float = 0.3,
        max_delay: float = 2.0,
        max_requests: int = 2000,
        window_seconds: int = 3600,
        max_retries: int = 3,
        backoff_base: float = 1.5,
        backoff_max: float = 30.0,
        circuit_threshold: int = 10,
        circuit_reset_seconds: int = 60,
        adaptive: bool = True,
        jitter_ratio: float = 0.3,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._base_delay = min_delay
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.circuit_threshold = circuit_threshold
        self.circuit_reset_seconds = circuit_reset_seconds
        self.adaptive = adaptive
        self.jitter_ratio = jitter_ratio

        self._request_timestamps: list[float] = []
        self._latencies: list[float] = []
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._circuit_state = CircuitState.CLOSED
        self._circuit_opened_at: float | None = None
        self._failures: list[SymbolFailure] = []
        self._last_request_time: float = 0.0
        self._total_requests = 0
        self._total_successes = 0
        self._total_failures = 0

    @classmethod
    def from_env(cls, prefix: str = "RATE_LIMIT") -> AdaptiveRateLimiter:
        def _env(key: str, default: str) -> str:
            return os.getenv(f"{prefix}_{key}", default)

        return cls(
            min_delay=float(_env("MIN_DELAY", "0.3")),
            max_delay=float(_env("MAX_DELAY", "2.0")),
            max_requests=int(_env("MAX_REQUESTS", "2000")),
            window_seconds=int(_env("WINDOW_SECONDS", "3600")),
            max_retries=int(_env("MAX_RETRIES", "3")),
            backoff_base=float(_env("BACKOFF_BASE", "1.5")),
            backoff_max=float(_env("BACKOFF_MAX", "30.0")),
            circuit_threshold=int(_env("CIRCUIT_THRESHOLD", "10")),
            circuit_reset_seconds=int(_env("CIRCUIT_RESET_SECONDS", "60")),
            adaptive=_env("ADAPTIVE", "true").lower() in ("true", "1", "yes"),
            jitter_ratio=float(_env("JITTER_RATIO", "0.3")),
        )

    @classmethod
    def for_yfinance(cls) -> AdaptiveRateLimiter:
        """Preset for Yahoo Finance API (fast, reliable API).

        Calibrated via scripts/bench/ratelimit_stress.py (Aug 2026):
        - 100% success at 0.0s delay for 30 requests (Yahoo very tolerant)
        - 0.2s min_delay with adaptive tuning + 0.3 jitter ratio
        - max 2000 req/hour (community-known safe zone for Yahoo unofficial API)
        """
        return cls(
            min_delay=0.2,
            max_delay=1.0,
            max_requests=2000,
            window_seconds=3600,
            max_retries=3,
            backoff_base=1.5,
            backoff_max=20.0,
            circuit_threshold=10,
            circuit_reset_seconds=30,
            adaptive=True,
            jitter_ratio=0.3,
        )

    @classmethod
    def for_idx_scraper(cls) -> AdaptiveRateLimiter:
        """Preset for idx.co.id (Cloudflare-protected, needs more care).

        Calibrated via scripts/bench/ratelimit_stress.py (Aug 2026):
        - 100% success at 0.1s and 0.2s delay (20 req each via curl_cffi)
        - 403s at 0.0s (too aggressive) and 0.3s (Cloudflare probabilistic)
        - 0.2s chosen as optimal; idx_batch.py has 3x retry for 403s.
        """
        return cls(
            min_delay=0.2,
            max_delay=2.0,
            max_requests=100,
            window_seconds=60,
            max_retries=5,
            backoff_base=2.0,
            backoff_max=60.0,
            circuit_threshold=5,
            circuit_reset_seconds=120,
            adaptive=True,
            jitter_ratio=0.5,
        )

    @classmethod
    def for_rss(cls) -> AdaptiveRateLimiter:
        """Preset for RSS feeds (polite crawling)."""
        return cls(
            min_delay=1.0,
            max_delay=3.0,
            max_requests=60,
            window_seconds=60,
            max_retries=2,
            backoff_base=2.0,
            backoff_max=30.0,
            circuit_threshold=3,
            circuit_reset_seconds=60,
            adaptive=False,
            jitter_ratio=0.4,
        )

    @property
    def stats(self) -> dict:
        """Return current statistics."""
        avg_latency = sum(self._latencies[-100:]) / max(len(self._latencies[-100:]), 1)
        return {
            "total_requests": self._total_requests,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "circuit_state": self._circuit_state.value,
            "current_delay": self._base_delay,
            "avg_latency": avg_latency,
            "failures": len(self._failures),
        }

    @property
    def failures(self) -> list[SymbolFailure]:
        return list(self._failures)

    @property
    def circuit_state(self) -> CircuitState:
        return self._circuit_state

    def _compute_delay(self) -> float:
        """Compute actual delay with jitter."""
        base = self._base_delay
        jitter = random.uniform(0, base * self.jitter_ratio)
        return base + jitter

    def _wait_delay(self) -> None:
        """Wait for the computed delay since last request."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        delay = self._compute_delay()
        wait = delay - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.monotonic()

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

    def _record_success(self, latency: float) -> None:
        self._consecutive_failures = 0
        self._consecutive_successes += 1
        self._circuit_state = CircuitState.CLOSED
        self._circuit_opened_at = None
        self._total_successes += 1

        if self.adaptive and latency > 0:
            self._latencies.append(latency)
            # Keep only last 100 latencies
            if len(self._latencies) > 100:
                self._latencies = self._latencies[-100:]

            # Adaptive tuning: after 10 successes, adjust delay
            if self._consecutive_successes >= 10 and len(self._latencies) >= 10:
                recent = self._latencies[-20:]
                p95 = sorted(recent)[int(len(recent) * 0.95)] if len(recent) >= 2 else recent[0]
                # Target delay = 2x p95 latency, but within [min_delay, max_delay]
                target = max(self.min_delay, min(self.max_delay, p95 * 2))
                # Smooth adjustment (move 20% toward target)
                self._base_delay = self._base_delay * 0.8 + target * 0.2
                self._consecutive_successes = 0  # reset counter

    def _record_failure(self, symbol: str, error: str) -> None:
        self._consecutive_failures += 1
        self._consecutive_successes = 0
        self._total_failures += 1
        self._failures.append(SymbolFailure(symbol=symbol, error=error))

        # Adaptive: increase delay on failure
        if self.adaptive:
            self._base_delay = min(self.max_delay, self._base_delay * 1.5)

        if self._consecutive_failures >= self.circuit_threshold:
            self._circuit_state = CircuitState.OPEN
            self._circuit_opened_at = time.monotonic()

    def _compute_backoff(self, attempt: int) -> float:
        wait = self.backoff_base ** attempt
        # Add jitter to backoff
        jitter = random.uniform(0, wait * 0.3)
        return min(wait + jitter, self.backoff_max)

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
                    error="Circuit breaker is open - too many consecutive failures",
                    attempts=attempt,
                    total_wait_seconds=total_wait,
                )

            self._check_window_limit()
            self._wait_delay()

            self._request_timestamps.append(time.monotonic())
            self._total_requests += 1

            t0 = time.monotonic()
            try:
                data = func()
                latency = time.monotonic() - t0
                self._record_success(latency)
                return RateLimitResult(
                    data=data,
                    attempts=attempt + 1,
                    total_wait_seconds=total_wait,
                    latency=latency,
                )
            except Exception as e:
                latency = time.monotonic() - t0
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
        self._latencies.clear()
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._circuit_state = CircuitState.CLOSED
        self._circuit_opened_at = None
        self._failures.clear()
        self._last_request_time = 0.0
        self._total_requests = 0
        self._total_successes = 0
        self._total_failures = 0
        self._base_delay = self.min_delay
