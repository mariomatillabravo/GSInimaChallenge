"""Unit tests of the circuit breaker, with a controllable clock and a 60-second cool-down."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from app.services.circuit import CircuitBreaker

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
COOLDOWN = timedelta(seconds=60)


class FakeClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def breaker(clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(COOLDOWN, clock)


def test_a_new_circuit_lets_calls_through(breaker: CircuitBreaker) -> None:
    assert breaker.retry_after_seconds() is None


@pytest.mark.parametrize(
    ("elapsed", "retry_after"),
    [
        (timedelta(0), 60),
        (timedelta(seconds=59), 1),
        (timedelta(seconds=59, milliseconds=500), 1),  # rounded up: never "retry in 0 s"
        (timedelta(seconds=60), None),  # the cool-down is over
    ],
)
def test_a_failure_opens_the_circuit_for_the_cooldown(
    breaker: CircuitBreaker, clock: FakeClock, elapsed: timedelta, retry_after: int | None
) -> None:
    breaker.record_failure()
    clock.now = NOW + elapsed

    assert breaker.retry_after_seconds() == retry_after


def test_a_success_closes_the_circuit(
    breaker: CircuitBreaker, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    breaker.record_failure()
    clock.now = NOW + COOLDOWN

    with caplog.at_level(logging.INFO, logger="app.services.circuit"):
        breaker.record_success()

    assert breaker.retry_after_seconds() is None
    assert "calls are back to normal" in caplog.text


def test_a_failure_after_the_cooldown_opens_it_again(
    breaker: CircuitBreaker, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    breaker.record_failure()
    clock.now = NOW + COOLDOWN + timedelta(seconds=1)

    with caplog.at_level(logging.WARNING, logger="app.services.circuit"):
        breaker.record_failure()

    assert breaker.retry_after_seconds() == 60
    assert "will not be called for 60 seconds" in caplog.text
