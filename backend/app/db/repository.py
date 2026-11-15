"""Reads and writes of the cache tables.

There are no freshness rules here: deciding whether a month must be fetched again belongs to the
service. The repository only stores whole months and reads observations back.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import Engine, delete, insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.engine import write_transaction
from app.db.schema import fetched_chunks, measurements
from app.domain.chunks import CachedChunk, MonthChunk
from app.domain.measurements import Observation

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_SECOND: Final = timedelta(seconds=1)


def to_epoch_seconds(moment: datetime) -> int:
    """Whole seconds since 1970-01-01T00:00:00Z, rounded down. Exact: no float arithmetic.

    Raises:
        ValueError: If ``moment`` is naive.
    """
    _require_aware(moment)
    return (moment - _EPOCH) // _SECOND


def from_epoch_seconds(seconds: int) -> datetime:
    """Aware UTC datetime for a number of seconds since 1970-01-01T00:00:00Z."""
    return _EPOCH + timedelta(seconds=seconds)


class CacheRepository:
    """Storage of observations and of the months already fetched, per station."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def cached_chunks(self, station_id: str, keys: Iterable[str]) -> dict[str, CachedChunk]:
        """Return the cached months among ``keys`` (``"YYYY-MM"``); missing months are absent."""
        keys = list(keys)
        if not keys:
            return {}
        query = select(fetched_chunks).where(
            fetched_chunks.c.station_id == station_id,
            fetched_chunks.c.chunk_start.in_(keys),
        )
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
        return {
            row.chunk_start: CachedChunk(
                key=row.chunk_start,
                fetched_at=from_epoch_seconds(row.fetched_at),
                row_count=row.row_count,
            )
            for row in rows
        }

    def save_chunk(
        self,
        station_id: str,
        chunk: MonthChunk,
        observations: Sequence[Observation],
        fetched_at: datetime,
    ) -> None:
        """Store one whole month, replacing whatever was cached for it.

        Everything happens in one write transaction: readers see either the previous month or the
        new one, never a mix, and an error leaves the previous month untouched. Replacing the month
        (instead of updating row by row) drops records the source no longer publishes, and keeps
        ``row_count`` equal to the rows stored. An empty list records that the month has no data.

        Raises:
            ValueError: If an observation falls outside the month, or ``fetched_at`` is naive.
        """
        outside = [o.timestamp for o in observations if not chunk.start <= o.timestamp <= chunk.end]
        if outside:
            raise ValueError(f"Observations outside {chunk.key}, e.g. {outside[0].isoformat()}.")
        rows = [
            {
                "station_id": station_id,
                "ts_utc": to_epoch_seconds(o.timestamp),
                "temperature": o.temperature,
                "pressure": o.pressure,
                "speed": o.speed,
            }
            for o in observations
        ]
        chunk_row = sqlite_insert(fetched_chunks).values(
            station_id=station_id,
            chunk_start=chunk.key,
            fetched_at=to_epoch_seconds(fetched_at),
            row_count=len(rows),
        )
        upsert_chunk_row = chunk_row.on_conflict_do_update(
            index_elements=[fetched_chunks.c.station_id, fetched_chunks.c.chunk_start],
            set_={
                "fetched_at": chunk_row.excluded.fetched_at,
                "row_count": chunk_row.excluded.row_count,
            },
        )
        with write_transaction(self._engine) as connection:
            connection.execute(
                delete(measurements).where(
                    measurements.c.station_id == station_id,
                    measurements.c.ts_utc.between(
                        to_epoch_seconds(chunk.start), to_epoch_seconds(chunk.end)
                    ),
                )
            )
            if rows:
                connection.execute(insert(measurements), rows)
            connection.execute(upsert_chunk_row)

    def read_observations(
        self, station_id: str, start: datetime, end: datetime
    ) -> list[Observation]:
        """Return the stored observations with ``start <= timestamp <= end``, sorted by time.

        Raises:
            ValueError: If ``start`` or ``end`` is naive.
        """
        # Stored timestamps are whole seconds: round the lower bound up and the upper bound down,
        # so that sub-second bounds never let in an observation outside the range.
        lower = _epoch_seconds_rounded_up(start)
        upper = to_epoch_seconds(end)
        query = (
            select(
                measurements.c.ts_utc,
                measurements.c.temperature,
                measurements.c.pressure,
                measurements.c.speed,
            )
            .where(
                measurements.c.station_id == station_id,
                measurements.c.ts_utc.between(lower, upper),
            )
            .order_by(measurements.c.ts_utc)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
        return [
            Observation(
                timestamp=from_epoch_seconds(row.ts_utc),
                temperature=row.temperature,
                pressure=row.pressure,
                speed=row.speed,
            )
            for row in rows
        ]


def _epoch_seconds_rounded_up(moment: datetime) -> int:
    seconds = to_epoch_seconds(moment)
    return seconds if from_epoch_seconds(seconds) == moment else seconds + 1


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed.")
