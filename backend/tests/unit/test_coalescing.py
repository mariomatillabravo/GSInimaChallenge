"""Unit tests of SingleFlight with real threads.

The leader's call is held until every other caller is waiting for it (``waiting``), so the
tests never depend on timing.
"""

import contextlib
import threading
import time
from collections.abc import Callable

import pytest

from app.services.coalescing import SingleFlight

TIMEOUT = 5.0


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("Condition not reached in time.")
        time.sleep(0.005)


class HeldCall:
    """A function that counts its calls and blocks until released."""

    def __init__(self, result: str = "value", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self) -> str:
        self.calls += 1
        self.started.set()
        if not self.release.wait(TIMEOUT):
            raise AssertionError("Never released.")
        if self.error is not None:
            raise self.error
        return self.result


def run_callers(
    flights: SingleFlight[str, str], function: HeldCall, callers: int
) -> list[str | BaseException]:
    """Start a leader, then the other callers once it runs; release it when all of them wait."""
    outcomes: list[str | BaseException] = []

    def call() -> None:
        try:
            outcomes.append(flights.run("key", function))
        except BaseException as error:
            outcomes.append(error)

    leader = threading.Thread(target=call)
    leader.start()
    assert function.started.wait(TIMEOUT)
    others = [threading.Thread(target=call) for _ in range(callers - 1)]
    for thread in others:
        thread.start()
    wait_until(lambda: flights.waiting("key") == callers - 1)
    function.release.set()
    for thread in [leader, *others]:
        thread.join(TIMEOUT)
    return outcomes


def test_concurrent_callers_share_one_call() -> None:
    flights: SingleFlight[str, str] = SingleFlight()
    function = HeldCall()

    outcomes = run_callers(flights, function, callers=8)

    assert outcomes == ["value"] * 8
    assert function.calls == 1


def test_a_failure_reaches_every_caller_and_the_call_is_not_repeated() -> None:
    flights: SingleFlight[str, str] = SingleFlight()
    error = RuntimeError("AEMET is down")
    function = HeldCall(error=error)

    outcomes = run_callers(flights, function, callers=8)

    assert outcomes == [error] * 8
    assert function.calls == 1


def test_different_keys_run_at_the_same_time() -> None:
    flights: SingleFlight[str, str] = SingleFlight()
    # Each call waits for the other one: if the keys were serialized, the barrier would time out.
    both_running = threading.Barrier(2, timeout=TIMEOUT)
    outcomes: list[str] = []

    def call(key: str) -> None:
        outcomes.append(flights.run(key, lambda: str(both_running.wait())))

    threads = [threading.Thread(target=call, args=(key,)) for key in ("january", "february")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)

    assert sorted(outcomes) == ["0", "1"]


@pytest.mark.parametrize("fails", [False, True], ids=["after success", "after failure"])
def test_a_finished_call_is_forgotten(fails: bool) -> None:
    flights: SingleFlight[str, str] = SingleFlight()
    calls: list[int] = []

    def function() -> str:
        calls.append(1)
        if fails:
            raise RuntimeError("AEMET is down")
        return "value"

    for _ in range(2):
        with contextlib.suppress(RuntimeError):
            flights.run("key", function)

    assert len(calls) == 2  # nothing is cached: each later call runs the function again
    assert flights.waiting("key") == 0
