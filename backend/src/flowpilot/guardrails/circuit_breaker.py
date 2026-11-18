"""Provider/tier circuit breaker preventing cascading upstream LLM outages."""

from __future__ import annotations

import time
from dataclasses import dataclass

from flowpilot.guardrails.exceptions import CircuitBreakerOpenError
from flowpilot.observability.metrics import CIRCUIT_BREAKER_STATE, GUARDRAIL_TRIPS_TOTAL

STATE_TO_NUM = {"closed": 0, "half_open": 1, "open": 2}


@dataclass
class CircuitBreaker:
    key: str
    failure_threshold: int = 5
    recovery_seconds: int = 60
    state: str = "closed"
    failure_count: int = 0
    opened_at: float | None = None

    def _emit_metric(self) -> None:
        CIRCUIT_BREAKER_STATE.labels(provider_key=self.key).set(STATE_TO_NUM[self.state])

    def allow_request(self) -> None:
        if self.state == "open":
            now = time.monotonic()
            if self.opened_at is not None and (now - self.opened_at) >= self.recovery_seconds:
                self.state = "half_open"
                self._emit_metric()
                return
            GUARDRAIL_TRIPS_TOTAL.labels(guardrail_type="circuit_breaker_open").inc()
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.key}' is OPEN due to repeated upstream failures.",
                details={
                    "key": self.key,
                    "failure_count": self.failure_count,
                    "recovery_seconds": self.recovery_seconds,
                },
            )

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None
        self.state = "closed"
        self._emit_metric()

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.state == "half_open" or self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()
        self._emit_metric()

    def reset(self) -> None:
        self.record_success()

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_seconds": self.recovery_seconds,
            "opened_at": self.opened_at,
        }


class CircuitBreakerRegistry:
    """Manages circuit breakers keyed by provider:tier."""

    def __init__(self, *, failure_threshold: int = 5, recovery_seconds: int = 60) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, key: str) -> CircuitBreaker:
        if key not in self._breakers:
            cb = CircuitBreaker(
                key=key,
                failure_threshold=self._failure_threshold,
                recovery_seconds=self._recovery_seconds,
            )
            cb._emit_metric()
            self._breakers[key] = cb
        return self._breakers[key]

    def list_all(self) -> list[dict[str, object]]:
        return [cb.to_dict() for cb in self._breakers.values()]

    def reset(self, key: str) -> bool:
        if key in self._breakers:
            self._breakers[key].reset()
            return True
        return False

    def clear(self) -> None:
        self._breakers.clear()


_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    return _registry
