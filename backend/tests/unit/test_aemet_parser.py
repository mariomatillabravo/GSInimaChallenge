"""Contract tests for the AEMET parser: real recorded responses plus small synthetic cases."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.clients.aemet_parser import (
    decode_body,
    load_records,
    parse_envelope,
    parse_observations,
)
from app.core.exceptions import UpstreamError
from app.domain.measurements import Observation

FIXTURES = Path(__file__).parents[1] / "fixtures" / "aemet"


def load(name: str) -> str:
    return decode_body((FIXTURES / name).read_bytes(), "ISO-8859-15")


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def record(fhora: str | None = "2026-01-15T00:00:00Z", **values: object) -> dict[str, object]:
    return {"fhora": fhora, "temp": 1.0, "pres": 980.0, "vel": 5.0, "qdato": 0.0, **values}


def values(observation: Observation) -> tuple[float | None, float | None, float | None]:
    return observation.temperature, observation.pressure, observation.speed


class TestEnvelopes:
    def test_success_envelope_points_to_the_data(self) -> None:
        envelope = parse_envelope(load("envelope_success.json"))

        assert envelope.status == 200
        assert envelope.data_url is not None
        assert envelope.data_url.startswith("https://opendata.aemet.es/opendata/sh/")

    def test_no_data_is_reported_in_the_body(self) -> None:
        envelope = parse_envelope(load("envelope_no_data.json"))

        assert envelope.status == 404
        assert envelope.data_url is None
        assert "No hay datos" in envelope.description

    def test_range_too_large_is_reported_in_the_body(self) -> None:
        assert parse_envelope(load("envelope_range_too_large.json")).status == 400

    @pytest.mark.parametrize("text", ["not json", "[]", '{"descripcion": "exito"}'])
    def test_malformed_envelopes_are_upstream_errors(self, text: str) -> None:
        with pytest.raises(UpstreamError):
            parse_envelope(text)


class TestRecordedData:
    def test_typical_day_of_juan_carlos_i(self) -> None:
        parsed = parse_observations(load("data_89064_2026-01-15_2026-01-16.json"))

        assert len(parsed.observations) == 145  # inclusive range: 144 + 1
        assert parsed.discarded == 0
        assert parsed.observations[0].timestamp == utc("2026-01-15T00:00:00")
        assert parsed.observations[-1].timestamp == utc("2026-01-16T00:00:00")

    def test_nan_strings_become_missing_values(self) -> None:
        parsed = parse_observations(load("data_89064_2026-01-15_2026-01-16.json"))
        partial = next(o for o in parsed.observations if o.timestamp == utc("2026-01-15T16:00:00"))

        assert values(partial) == (None, None, 2.5)

    def test_station_with_a_different_set_of_fields(self) -> None:
        parsed = parse_observations(load("data_89070_2026-01-15_2026-01-16.json"))
        first = parsed.observations[0]

        assert len(parsed.observations) == 145
        assert values(first) == (2.2, 983.3, 3.8)

    def test_unsorted_response_is_returned_sorted(self) -> None:
        parsed = parse_observations(load("data_89064_2023-03-25_2023-03-27.json"))
        timestamps = [o.timestamp for o in parsed.observations]

        assert len(timestamps) == 289
        assert timestamps == sorted(timestamps)
        assert timestamps[0] == utc("2023-03-25T00:00:00")
        assert timestamps[-1] == utc("2023-03-27T00:00:00")

    def test_timestamps_are_timezone_aware_utc(self) -> None:
        parsed = parse_observations(load("data_89070_2026-01-15_2026-01-16.json"))

        assert all(o.timestamp.tzinfo is UTC for o in parsed.observations)


class TestCleaningRule:
    def test_bad_quality_record_is_discarded(self) -> None:
        records = [record(qdato=1.0), record(fhora="2026-01-15T00:10:00Z")]
        parsed = parse_observations(json.dumps(records))

        assert [o.timestamp for o in parsed.observations] == [utc("2026-01-15T00:10:00")]
        assert (parsed.discarded, parsed.received) == (1, 2)

    def test_record_without_any_value_is_discarded(self) -> None:
        parsed = parse_observations(json.dumps([record(temp="NaN", pres="NaN", vel="NaN")]))

        assert parsed.observations == []
        assert parsed.discarded == 1

    def test_absent_fields_are_missing_values(self) -> None:
        raw = {"fhora": "2026-01-15T00:00:00Z", "vel": 4.0}
        observation = parse_observations(json.dumps([raw])).observations[0]

        assert values(observation) == (None, None, 4.0)

    @pytest.mark.parametrize("fhora", [None, "", "yesterday", "2026-01-15T00:00:00"])
    def test_records_without_a_valid_utc_timestamp_are_discarded(self, fhora: str | None) -> None:
        parsed = parse_observations(json.dumps([record(fhora=fhora)]))

        assert parsed.observations == []
        assert parsed.discarded == 1

    def test_repeated_timestamp_keeps_the_last_record(self) -> None:
        parsed = parse_observations(json.dumps([record(temp=1.0), record(temp=2.0)]))

        assert [o.temperature for o in parsed.observations] == [2.0]


class TestDecoding:
    def test_declared_latin_charset_is_honoured(self) -> None:
        text = "Grupo Antártico"

        assert decode_body(text.encode("iso-8859-15"), "ISO-8859-15") == text

    def test_undecodable_body_is_an_upstream_error(self) -> None:
        with pytest.raises(UpstreamError):
            decode_body(b"\xff\xfe", "utf-8")

    def test_data_that_is_not_a_list_is_an_upstream_error(self) -> None:
        with pytest.raises(UpstreamError):
            parse_observations('{"estado": 200}')


class TestRawRecords:
    def test_records_are_returned_as_served(self) -> None:
        records = load_records(load("data_89064_2026-01-15_2026-01-16.json"))

        assert len(records) == 145
        assert records[0]["identificacion"] == "89064"

    def test_entries_that_are_not_records_are_skipped(self) -> None:
        assert load_records('[{"fhora": "x"}, 3, "text"]') == [{"fhora": "x"}]
