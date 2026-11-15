"""Coalescing of concurrent calls for the same key, known as "single flight"."""

import logging
import threading
from collections.abc import Callable, Hashable
from concurrent.futures import Future

logger = logging.getLogger(__name__)


class SingleFlight[K: Hashable, T]:
    """Runs at most one call per key at a time; callers that arrive meanwhile share its outcome.

    The first caller for a key (the leader) runs the function. Callers that arrive while it runs
    do not run it again: they wait and receive the same result, or the same exception. When the
    call ends the key is forgotten, so nothing is cached here and the next caller runs the
    function again.

    It coordinates the threads of one process only.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        """Guards the two dictionaries below; never held while a call runs."""
        self._calls: dict[K, Future[T]] = {}
        self._waiting: dict[K, int] = {}

    def run(self, key: K, function: Callable[[], T]) -> T:
        """Return the outcome of ``function``, run once for all concurrent callers of ``key``."""
        with self._lock:
            call = self._calls.get(key)
            is_leader = call is None
            if call is None:
                call = Future()
                self._calls[key] = call
            else:
                self._waiting[key] = self._waiting.get(key, 0) + 1
        if is_leader:
            return self._lead(key, call, function)
        logger.debug("Waiting for the call already running for %r.", key)
        try:
            return call.result()  # raises the leader's exception if it failed
        finally:
            with self._lock:
                self._waiting[key] -= 1
                if not self._waiting[key]:
                    del self._waiting[key]

    def waiting(self, key: K) -> int:
        """How many callers are waiting for the call running for ``key``."""
        with self._lock:
            return self._waiting.get(key, 0)

    def _lead(self, key: K, call: Future[T], function: Callable[[], T]) -> T:
        try:
            result = function()
        except BaseException as error:
            call.set_exception(error)
            raise
        else:
            call.set_result(result)
            return result
        finally:
            with self._lock:
                del self._calls[key]
