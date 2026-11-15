"""Exploratory probe of the AEMET OpenData Antarctica endpoint.

This is a research tool, not application code. It checks the API details the design depends on
(station identifiers, date format, two-step responses, encoding, field names and units, range
limits and data availability) and saves the raw responses so they can be reviewed and reused as
test fixtures and demo data.

Usage (from the ``backend`` directory):

    uv run --env-file .env python scripts/explore_aemet.py [--group initial|demo-availability]

The API key is read from the ``AEMET_API_KEY`` environment variable and is never printed: any
occurrence of it in printed or saved text is redacted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://opendata.aemet.es/opendata"
ENDPOINT = "/api/antartida/datos/fechaini/{start}/fechafin/{end}/estacion/{station}"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SUTC"  # format expected by AEMET in the URL (verified)
STATIONS = ("89064", "89070")  # 89064 = Juan Carlos I, 89070 = Gabriel de Castilla (verified)
PAUSE_SECONDS = 2.0  # pause between calls to be polite with a free public API
TIMEOUT_SECONDS = 60.0
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "raw"


@dataclass(frozen=True)
class Probe:
    """One question we want AEMET to answer."""

    label: str
    station: str
    start: datetime
    end: datetime
    save: bool = True


def utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


INITIAL_PROBES: list[Probe] = [
    # 1. Does the key work? Which name belongs to each identifier? What does a record look like?
    *(Probe("summer-day", s, utc(2026, 1, 15), utc(2026, 1, 16)) for s in STATIONS),
    # 2. Is there data around the Madrid DST transitions (29 Mar and 25 Oct 2026)?
    *(Probe("dst-spring", s, utc(2026, 3, 28), utc(2026, 3, 30)) for s in STATIONS),
    *(Probe("dst-autumn", s, utc(2026, 10, 24), utc(2026, 10, 26)) for s in STATIONS),
    # 3. What is the maximum range accepted in a single request?
    Probe("range-1-month", STATIONS[0], utc(2026, 1, 1), utc(2026, 2, 1)),
    Probe("range-3-months", STATIONS[0], utc(2025, 12, 1), utc(2026, 3, 1), save=False),
    Probe("range-1-year", STATIONS[0], utc(2025, 1, 1), utc(2026, 1, 1), save=False),
    # 4. Since when is there data? (affects the choice of the station time zone)
    *(
        Probe(f"history-{year}", STATIONS[0], utc(year, 1, 15), utc(year, 1, 16), save=False)
        for year in (2010, 2015, 2018)
    ),
]

DEMO_AVAILABILITY_PROBES: list[Probe] = [
    # 5. Until when is there data in 2026? (the 2026 DST windows returned no data)
    Probe("avail-2026-02", STATIONS[0], utc(2026, 2, 1), utc(2026, 3, 1), save=False),
    Probe("avail-2026-03", STATIONS[0], utc(2026, 3, 1), utc(2026, 3, 27), save=False),
    # 6. Is there data around the spring DST transition of previous years? (for the demo)
    Probe("dst-spring-2025", STATIONS[0], utc(2025, 3, 29), utc(2025, 3, 31)),  # DST on 30 Mar
    Probe("dst-spring-2024", STATIONS[0], utc(2024, 3, 30), utc(2024, 4, 1)),  # DST on 31 Mar
    Probe("dst-spring-2023", STATIONS[0], utc(2023, 3, 25), utc(2023, 3, 27)),  # DST on 26 Mar
]

PROBE_GROUPS: dict[str, list[Probe]] = {
    "initial": INITIAL_PROBES,
    "demo-availability": DEMO_AVAILABILITY_PROBES,
}


class RateLimitedError(Exception):
    """AEMET answered 429: stop immediately instead of insisting."""


def redact(text: str, secret: str) -> str:
    return text.replace(secret, "***REDACTED***") if secret else text


def decode(content: bytes, declared_charset: str | None) -> tuple[str, str]:
    """Decode a response body, reporting which encoding actually worked."""
    for encoding in (declared_charset, "utf-8", "iso-8859-15"):
        if not encoding:
            continue
        try:
            return content.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("latin-1"), "latin-1 (fallback)"


def get(client: httpx.Client, url: str) -> httpx.Response:
    time.sleep(PAUSE_SECONDS)
    response = client.get(url)
    if response.status_code == 429:
        raise RateLimitedError(url)
    return response


def describe_records(records: list[dict[str, Any]]) -> None:
    """Print the facts we need about the measurement records."""
    print(f"    records: {len(records)}")
    if not records:
        return
    print(f"    fields: {sorted(records[0])}")
    print(f"    first record: {json.dumps(records[0], ensure_ascii=False)}")
    print(f"    last record:  {json.dumps(records[-1], ensure_ascii=False)}")
    for field in ("temp", "pres", "vel"):
        # AEMET encodes missing measurements as the string "NaN", not as null.
        missing = sum(1 for record in records if record.get(field) in (None, "", "NaN"))
        print(f"    '{field}' missing in {missing}/{len(records)} records")
    timestamps = [str(record.get("fhora")) for record in records]
    print(f"    first fhora values (time step check): {timestamps[:4]}")
    print(f"    records sorted by fhora: {timestamps == sorted(timestamps)}")
    print(f"    earliest fhora: {min(timestamps)} | latest fhora: {max(timestamps)}")
    quality_flags = sorted({str(record.get("qdato")) for record in records})
    print(f"    qdato values (1 = bad, 0 = good): {quality_flags}")


def run_probe(client: httpx.Client, probe: Probe, api_key: str, fetch_metadata: bool) -> None:
    start = probe.start.strftime(DATE_FORMAT)
    end = probe.end.strftime(DATE_FORMAT)
    url = BASE_URL + ENDPOINT.format(start=start, end=end, station=probe.station)
    print(f"\n=== {probe.label} | station {probe.station} | {start} -> {end}")

    # Step 1: the envelope, which points to the actual data.
    envelope_response = get(client, url)
    envelope_text, _ = decode(envelope_response.content, envelope_response.charset_encoding)
    print(
        f"  envelope HTTP {envelope_response.status_code} "
        f"| content-type: {envelope_response.headers.get('content-type')}"
    )
    print(f"  envelope body: {redact(envelope_text, api_key)[:400]}")
    try:
        envelope = json.loads(envelope_text)
    except json.JSONDecodeError:
        print("  envelope is not JSON; skipping")
        return

    data_url = envelope.get("datos")
    if not data_url:
        return
    print(f"  'datos' URL contains the API key: {api_key in data_url}")

    # Step 2: the actual data.
    data_response = get(client, data_url)
    data_text, used_encoding = decode(data_response.content, data_response.charset_encoding)
    print(
        f"  data HTTP {data_response.status_code} "
        f"| content-type: {data_response.headers.get('content-type')} "
        f"| decoded as: {used_encoding} | {len(data_response.content)} bytes"
    )
    try:
        records = json.loads(data_text)
    except json.JSONDecodeError:
        print(f"  data is not JSON: {redact(data_text, api_key)[:400]}")
        return
    if isinstance(records, list):
        describe_records(records)

    if probe.save:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = f"{probe.label}_{probe.station}"
        (OUTPUT_DIR / f"{stem}.envelope.json").write_text(
            redact(envelope_text, api_key), encoding="utf-8"
        )
        (OUTPUT_DIR / f"{stem}.data.json").write_bytes(data_response.content)
        print(f"  saved raw responses as {stem}.*.json")

    # Field descriptions and units, fetched once.
    metadata_url = envelope.get("metadatos")
    if fetch_metadata and metadata_url:
        metadata_response = get(client, metadata_url)
        metadata_text, _ = decode(metadata_response.content, metadata_response.charset_encoding)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "metadata.json").write_text(redact(metadata_text, api_key), encoding="utf-8")
        print(f"  metadata saved as metadata.json:\n{redact(metadata_text, api_key)[:1500]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--group", choices=sorted(PROBE_GROUPS), default="initial")
    args = parser.parse_args()

    api_key = os.environ.get("AEMET_API_KEY", "").strip()
    if not api_key:
        print("AEMET_API_KEY is not set. Run with: uv run --env-file .env python scripts/...")
        return 1

    probes = PROBE_GROUPS[args.group]
    headers = {"api_key": api_key, "Accept": "application/json"}  # header auth (verified)
    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS) as client:
        try:
            for index, probe in enumerate(probes):
                fetch_metadata = args.group == "initial" and index == 0
                run_probe(client, probe, api_key, fetch_metadata=fetch_metadata)
        except RateLimitedError:
            print("\nAEMET answered 429 (rate limit). Stopping without retrying.")
            return 2
        except httpx.HTTPError as error:
            print(f"\nNetwork error: {redact(str(error), api_key)}")
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
