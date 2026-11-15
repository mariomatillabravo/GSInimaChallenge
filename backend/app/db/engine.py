"""SQLAlchemy engine for the SQLite cache: connection settings and transaction control.

Three SQLite behaviours shape this module (all verified with concurrent tests):

- Python's ``sqlite3`` driver, in its default "legacy" mode, runs ``CREATE``/``DROP TABLE`` and
  ``PRAGMA user_version`` outside the current transaction, so they cannot be rolled back. Here the
  driver never opens transactions itself (``isolation_level = None``); SQLAlchemy emits ``BEGIN``.
- A transaction that reads and then writes can fail at once with "database is locked" when
  another connection writes in between, whatever ``busy_timeout`` says. Write transactions
  therefore start with ``BEGIN IMMEDIATE``, which takes the write lock before the first read, so
  concurrent writers wait for their turn instead of failing.
- Switching a new database file to WAL can fail at once when several connections try at the same
  time (several worker processes starting together), so that switch is retried.

See ADR-0008 for the full reasoning.
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.pool import ConnectionPoolEntry
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_MS: Final = 5000
"""How long a connection waits for another one's write lock before failing."""

_IMMEDIATE: Final = "sqlite_begin_immediate"
"""Execution option that makes the next transaction start with ``BEGIN IMMEDIATE``."""


def create_sqlite_engine(path: Path) -> Engine:
    """Create the engine of the SQLite file at ``path``, creating its folder if needed.

    For a file database SQLAlchemy uses a ``QueuePool`` and disables ``sqlite3``'s
    ``check_same_thread`` guard: the pool lends each connection to one thread at a time, so a
    connection created in one thread can safely be used later by another. Code must never share a
    ``Connection`` object between threads; each unit of work opens its own.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path)))
    event.listen(engine, "connect", _configure_connection)
    event.listen(engine, "begin", _begin_transaction)
    return engine


def enable_wal(engine: Engine) -> None:
    """Switch the database to write-ahead logging (WAL), once per process at startup.

    WAL lets readers and the single writer work at the same time, which matters with requests
    served from a thread pool. The setting is stored in the database file, so new connections
    inherit it. It cannot be changed inside a transaction, hence the raw driver connection.
    """
    retrying = Retrying(
        retry=retry_if_exception(_is_locked_error),
        stop=stop_after_attempt(10),
        wait=wait_random_exponential(multiplier=0.02, max=0.5),
        reraise=True,
    )
    mode = retrying(_set_wal_mode, engine)
    if mode != "wal":
        # Some file systems (e.g. network shares) do not support WAL. SQLite keeps working in its
        # default journal mode, with less concurrency between readers and the writer.
        logger.warning("SQLite could not enable WAL; journal mode is %r.", mode)


@contextmanager
def write_transaction(engine: Engine) -> Iterator[Connection]:
    """Open a connection with a transaction that holds the write lock from the start.

    Use it for every unit of work that writes. The transaction commits when the block ends and
    rolls back if it raises.
    """
    with engine.connect() as connection:
        connection.execution_options(**{_IMMEDIATE: True})
        with connection.begin():
            yield connection


def _configure_connection(
    dbapi_connection: sqlite3.Connection, _connection_record: ConnectionPoolEntry
) -> None:
    """Prepare every new driver connection. These settings are per connection, not per file."""
    dbapi_connection.isolation_level = None  # sqlite3 stops opening transactions on its own
    cursor = dbapi_connection.cursor()
    cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    # With WAL, NORMAL only risks losing the last transactions on a power cut, never corruption:
    # acceptable for a cache that can always be fetched again.
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


def _begin_transaction(connection: Connection) -> None:
    """Start each transaction with ``BEGIN`` (reads) or ``BEGIN IMMEDIATE`` (writes)."""
    immediate = connection.get_execution_options().get(_IMMEDIATE, False)
    connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")


def _set_wal_mode(engine: Engine) -> str:
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")
        row = cursor.fetchone()
        cursor.close()
    finally:
        connection.close()
    return str(row[0]) if row else ""


def _is_locked_error(error: BaseException) -> bool:
    return isinstance(error, sqlite3.OperationalError) and "database is locked" in str(error)
