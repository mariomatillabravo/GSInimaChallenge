"""Tests of the SQLite engine on real temporary files (WAL needs a file, not ``:memory:``)."""

import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.pool import QueuePool

from app.db.database import open_database
from app.db.engine import BUSY_TIMEOUT_MS, create_sqlite_engine, enable_wal, write_transaction
from app.db.schema import SCHEMA_VERSION

ConcurrentRunner = Callable[[int, Callable[[int], None]], list[BaseException]]

SYNCHRONOUS_NORMAL = 1
"""Value returned by ``PRAGMA synchronous`` for NORMAL."""


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "cache.sqlite3")
    enable_wal(engine)
    yield engine
    engine.dispose()


def _pragmas(engine: Engine) -> tuple[str, int, int]:
    with engine.connect() as connection:
        return (
            connection.exec_driver_sql("PRAGMA journal_mode").scalar_one(),
            connection.exec_driver_sql("PRAGMA synchronous").scalar_one(),
            connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
        )


def test_open_database_prepares_a_ready_to_use_file(tmp_path: Path) -> None:
    path = tmp_path / "missing-folder" / "cache.sqlite3"

    engine = open_database(path, data_source="demo")
    try:
        assert path.exists()
        assert _pragmas(engine) == ("wal", SYNCHRONOUS_NORMAL, BUSY_TIMEOUT_MS)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA user_version").scalar() == SCHEMA_VERSION
    finally:
        engine.dispose()


def test_file_database_uses_a_pool_without_the_same_thread_check(engine: Engine) -> None:
    # The pool lends each connection to one thread at a time, so connections may move between
    # threads; sqlite3's check_same_thread guard would forbid that (behaviour of SQLAlchemy 2.x).
    _, connect_kwargs = engine.dialect.create_connect_args(engine.url)

    assert isinstance(engine.pool, QueuePool)
    assert connect_kwargs["check_same_thread"] is False


def test_connections_opened_by_other_threads_get_the_same_settings(
    engine: Engine, run_concurrently: ConcurrentRunner
) -> None:
    # Eight connections open at the same time: more than the pool keeps (five), so some are
    # created on the fly, each one in a different thread.
    threads = 8
    all_open = threading.Barrier(threads)
    seen: list[tuple[str, int, int]] = []

    def read_settings(_index: int) -> None:
        with engine.connect() as connection:
            seen.append(
                (
                    connection.exec_driver_sql("PRAGMA journal_mode").scalar_one(),
                    connection.exec_driver_sql("PRAGMA synchronous").scalar_one(),
                    connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
                )
            )
            all_open.wait()

    errors = run_concurrently(threads, read_settings)

    assert errors == []
    assert seen == [("wal", SYNCHRONOUS_NORMAL, BUSY_TIMEOUT_MS)] * threads


def _run_then_fail(engine: Engine, *statements: str) -> None:
    """Run ``statements`` in a write transaction that then raises, so it must roll back."""
    with write_transaction(engine) as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        raise RuntimeError("fail on purpose")


def test_write_transaction_commits_on_success_and_rolls_back_on_error(engine: Engine) -> None:
    with write_transaction(engine) as connection:
        connection.exec_driver_sql("CREATE TABLE t (x INTEGER)")
        connection.exec_driver_sql("INSERT INTO t VALUES (1)")
    with pytest.raises(RuntimeError, match="fail on purpose"):
        _run_then_fail(engine, "INSERT INTO t VALUES (2)")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT x FROM t").scalars().all() == [1]


def test_schema_changes_are_rolled_back_with_the_transaction(engine: Engine) -> None:
    # In sqlite3's default "legacy" mode, CREATE TABLE and PRAGMA user_version would survive the
    # rollback; the engine makes them part of the transaction.
    with pytest.raises(RuntimeError, match="fail on purpose"):
        _run_then_fail(engine, "CREATE TABLE t (x INTEGER)", "PRAGMA user_version = 42")

    with engine.connect() as connection:
        tables = connection.exec_driver_sql("SELECT name FROM sqlite_master").scalars().all()
        assert tables == []
        assert connection.exec_driver_sql("PRAGMA user_version").scalar() == 0


def test_concurrent_writers_and_readers_share_one_engine(
    engine: Engine, run_concurrently: ConcurrentRunner
) -> None:
    # Each writer reads the current maximum and inserts the next number: a read-then-write that
    # fails at once with "database is locked" under a plain BEGIN, and that would produce
    # duplicate numbers if two writers could interleave.
    with write_transaction(engine) as connection:
        connection.exec_driver_sql("CREATE TABLE counter (n INTEGER PRIMARY KEY)")
    writers, readers, rounds = 8, 8, 25

    def work(index: int) -> None:
        for _ in range(rounds):
            if index < writers:
                with write_transaction(engine) as connection:
                    current = connection.exec_driver_sql("SELECT MAX(n) FROM counter").scalar()
                    connection.execute(
                        text("INSERT INTO counter (n) VALUES (:n)"), {"n": (current or 0) + 1}
                    )
            else:
                with engine.connect() as connection:
                    connection.exec_driver_sql("SELECT COUNT(*) FROM counter").scalar_one()

    errors = run_concurrently(writers + readers, work)

    assert errors == []
    with engine.connect() as connection:
        numbers = connection.exec_driver_sql("SELECT n FROM counter ORDER BY n").scalars().all()
    assert numbers == list(range(1, writers * rounds + 1))
