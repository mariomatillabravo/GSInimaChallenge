"""Tables of the SQLite cache and the check that keeps the file in line with this code.

The cache can always be rebuilt from its data source, so there are no migrations: when the file
was written by a different schema version, or for a different data source, its tables are
dropped and created again (ADR-0008).
"""

import logging
from typing import Final, Literal

from sqlalchemy import (
    CheckConstraint,
    Column,
    Connection,
    Engine,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    insert,
    select,
    text,
)

from app.db.engine import write_transaction

logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = 1
"""Bump it whenever a table changes. Stored in the file header with ``PRAGMA user_version``."""

SchemaAction = Literal["created", "recreated", "unchanged"]

metadata = MetaData()

measurements = Table(
    "measurements",
    metadata,
    Column("station_id", Text, primary_key=True),
    Column("ts_utc", Integer, primary_key=True, autoincrement=False, comment="Unix epoch seconds"),
    Column("temperature", Float),
    Column("pressure", Float),
    Column("speed", Float),
    # Rows are stored in primary key order, which is exactly the range scan the cache does
    # (one station, consecutive timestamps), with no separate index.
    sqlite_with_rowid=False,
)
"""One row per station and ten-minute observation; a missing value is NULL."""

fetched_chunks = Table(
    "fetched_chunks",
    metadata,
    Column("station_id", Text, primary_key=True),
    Column("chunk_start", Text, primary_key=True, comment="Calendar month in UTC, e.g. 2026-01"),
    Column("fetched_at", Integer, nullable=False, comment="Unix epoch seconds"),
    Column("row_count", Integer, nullable=False),
    sqlite_with_rowid=False,
)
"""Which months of which station are cached and when they were fetched (row_count 0 = no data)."""

cache_info = Table(
    "cache_info",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("data_source", Text, nullable=False),
    CheckConstraint("id = 1", name="single_row"),
)
"""A single row naming the data source the cached data came from ("aemet" or "demo")."""


def ensure_schema(engine: Engine, data_source: str) -> SchemaAction:
    """Make sure the file holds the current schema for ``data_source``.

    Runs in one write transaction: concurrent callers (several worker processes starting at once)
    take turns, and an error halfway leaves the previous schema untouched.

    Returns:
        What was done, mainly for logging and tests.
    """
    with write_transaction(engine) as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        existing = _user_tables(connection)
        stored_source = _stored_data_source(connection, existing)
        if version == SCHEMA_VERSION and stored_source == data_source:
            return "unchanged"
        if existing:
            logger.warning(
                "Rebuilding the cache database: found schema version %s for data source %r, "
                "expected version %s for %r. The data will be fetched again.",
                version,
                stored_source,
                SCHEMA_VERSION,
                data_source,
            )
            for name in existing:
                connection.exec_driver_sql(f"DROP TABLE {_quote(connection, name)}")
        metadata.create_all(connection)
        connection.execute(insert(cache_info).values(id=1, data_source=data_source))
        # PRAGMA values cannot be bound parameters; SCHEMA_VERSION is an integer constant.
        connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION:d}")
    return "recreated" if existing else "created"


def _user_tables(connection: Connection) -> list[str]:
    """Tables in the file, excluding SQLite's internal ones (named ``sqlite_*``)."""
    query = text(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND substr(name, 1, 7) != 'sqlite_'"
    )
    return list(connection.execute(query).scalars())


def _stored_data_source(connection: Connection, existing_tables: list[str]) -> str | None:
    if cache_info.name not in existing_tables:
        return None
    return connection.execute(select(cache_info.c.data_source)).scalar_one_or_none()


def _quote(connection: Connection, name: str) -> str:
    return connection.dialect.identifier_preparer.quote_identifier(name)
