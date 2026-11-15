"""Property-based tests: Hypothesis generates hundreds of instants looking for counterexamples."""

from datetime import UTC, datetime, timedelta

from hypothesis import given, reject
from hypothesis import strategies as st

from app.core.exceptions import AmbiguousLocalTimeError, NonExistentLocalTimeError
from app.domain.timezones import MADRID, format_output_datetime, localize_strict

# Bounds must be naive for Hypothesis; the generated values get the time zone from `timezones`.
EARLIEST = datetime.fromisoformat("2000-01-01T00:00:00")
LATEST = datetime.fromisoformat("2099-12-31T23:59:59")

utc_instants = st.datetimes(min_value=EARLIEST, max_value=LATEST, timezones=st.just(UTC)).map(
    lambda instant: instant.replace(microsecond=0)
)
local_times = st.datetimes(min_value=EARLIEST, max_value=LATEST).map(
    lambda local: local.replace(microsecond=0)
)


@given(utc_instants)
def test_output_datetimes_parse_back_to_the_same_instant(instant: datetime) -> None:
    parsed = datetime.fromisoformat(format_output_datetime(instant))

    assert parsed == instant
    assert parsed.utcoffset() in {timedelta(hours=1), timedelta(hours=2)}


@given(local_times)
def test_valid_madrid_local_times_round_trip(local: datetime) -> None:
    try:
        instant = localize_strict(local, MADRID, parameter="start", raw=local.isoformat())
    except (NonExistentLocalTimeError, AmbiguousLocalTimeError):
        reject()  # DST edge cases are covered by the explicit DST test suite

    assert instant.astimezone(MADRID).replace(tzinfo=None) == local
