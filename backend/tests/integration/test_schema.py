"""Tests of the cache schema and of the rules that rebuild it, on real temporary SQLite files."""

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, inspect, select

from app.db import schema
from app.db.engine import create_sqlite_engine, enable_wal, write_transaction
from app.db.schema import SCHEMA_VERSION, SchemaAction, cache_info, ensure_schema, measurements

ConcurrentRunner = Callable[[int, Callable[[int], None]], list[BaseException]]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "cache.sqlite3")
    enable_wal(engine)
    yield engine
    engine.dispose()


def _user_version(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.exec_driver_sql("PRAGMA user_version").scalar_one())


def _set_user_version(engine: Engine, version: int) -> None:
    with write_transaction(engine) as connection:
        connection.exec_driver_sql(f"PRAGMA user_version = {version:d}")


def _store_measurement(engine: Engine) -> None:
    with write_transaction(engine) as connection:
        connection.execute(
            insert(measurements).values(station_id="juan-carlos-i", ts_utc=0, temperature=1.5)
        )


def _measurement_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return len(connection.execute(select(measurements)).all())


def _stored_data_source(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(select(cache_info.c.data_source)).scalar_one())


def test_a_new_file_gets_the_current_schema(engine: Engine) -> None:
    assert ensure_schema(engine, "demo") == "created"

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {"measurements", "fetched_chunks", "cache_info"}
    assert inspector.get_pk_constraint("measurements")["constrained_columns"] == [
        "station_id",
        "ts_utc",
    ]
    assert inspector.get_pk_constraint("fetched_chunks")["constrained_columns"] == [
        "station_id",
        "chunk_start",
    ]
    assert _user_version(engine) == SCHEMA_VERSION
    assert _stored_data_source(engine) == "demo"


def test_reopening_a_current_file_keeps_its_data(engine: Engine) -> None:
    ensure_schema(engine, "demo")
    _store_measurement(engine)

    assert ensure_schema(engine, "demo") == "unchanged"
    assert _measurement_count(engine) == 1


@pytest.mark.parametrize(
    "file_version", [SCHEMA_VERSION - 1, SCHEMA_VERSION + 1], ids=["older", "newer"]
)
def test_a_file_with_another_schema_version_is_rebuilt(
    engine: Engine, file_version: int, caplog: pytest.LogCaptureFixture
) -> None:
    ensure_schema(engine, "demo")
    _store_measurement(engine)
    _set_user_version(engine, file_version)

    with caplog.at_level(logging.WARNING, logger="app.db.schema"):
        assert ensure_schema(engine, "demo") == "recreated"

    assert _measurement_count(engine) == 0
    assert _user_version(engine) == SCHEMA_VERSION
    assert "Rebuilding the cache database" in caplog.text


def test_a_file_for_another_data_source_is_rebuilt(engine: Engine) -> None:
    # Demo data cached as "no data" for most months must never be served as real AEMET data.
    ensure_schema(engine, "demo")
    _store_measurement(engine)

    assert ensure_schema(engine, "aemet") == "recreated"
    assert _measurement_count(engine) == 0
    assert _stored_data_source(engine) == "aemet"


def test_tables_of_an_unknown_schema_are_dropped(engine: Engine) -> None:
    with write_transaction(engine) as connection:
        connection.exec_driver_sql("CREATE TABLE old_measurements (x INTEGER)")
    _set_user_version(engine, 7)

    assert ensure_schema(engine, "aemet") == "recreated"
    assert "old_measurements" not in inspect(engine).get_table_names()


def test_a_failed_rebuild_leaves_the_previous_schema_untouched(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ensure_schema(engine, "demo")
    _store_measurement(engine)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    # The old tables are already dropped when creating the new ones fails.
    monkeypatch.setattr(schema.metadata, "create_all", fail)
    with pytest.raises(RuntimeError, match="disk full"):
        ensure_schema(engine, "aemet")

    assert _measurement_count(engine) == 1
    assert _user_version(engine) == SCHEMA_VERSION
    assert _stored_data_source(engine) == "demo"


def test_workers_starting_together_create_the_schema_once(
    tmp_path: Path, run_concurrently: ConcurrentRunner
) -> None:
    # Each thread plays a worker process with its own engine, all opening a brand-new file at
    # the same instant. This races both the switch to WAL and the schema transaction.
    workers = 8
    for attempt in range(5):
        path = tmp_path / f"cache-{attempt}.sqlite3"
        actions: list[SchemaAction] = []

        def start_worker(
            _index: int, path: Path = path, actions: list[SchemaAction] = actions
        ) -> None:
            engine = create_sqlite_engine(path)
            try:
                enable_wal(engine)
                actions.append(ensure_schema(engine, "demo"))
            finally:
                engine.dispose()

        errors = run_concurrently(workers, start_worker)

        assert errors == []
        assert sorted(actions) == ["created"] + ["unchanged"] * (workers - 1)
