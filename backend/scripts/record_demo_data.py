"""Record the demo data: one calendar month of real AEMET data for every station.

The records are fetched through the application's own AEMET client (same protocol, retries and
error handling as live requests) and trimmed to the fields the application uses. Values are not
modified: cleaning still happens when the demo source parses the files.

Usage (from the ``backend`` directory):

    uv run --env-file .env python -m scripts.record_demo_data --month 2025-03

The API key is read from the ``AEMET_API_KEY`` environment variable and is never printed.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
from pydantic import SecretStr

from app.clients.aemet import AemetAntarcticaClient
from app.domain.chunks import month_chunks
from app.domain.stations import STATIONS

KEPT_FIELDS: Final = (
    "identificacion",
    "nombre",
    "fhora",
    "temp",
    "pres",
    "vel",
    "qdato",
    "velx",  # maximum wind speed within the 10 minutes, for the extended wind metrics
    "tmn",  # minimum temperature within the 10 minutes
    "tmx",  # maximum temperature within the 10 minutes
)
OUTPUT_DIR: Final = Path(__file__).resolve().parent.parent / "sample_data" / "demo"


def trim(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in KEPT_FIELDS if field in record}


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    """One record per line: compact, yet readable and diff-friendly."""
    lines = ",\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    path.write_text(f"[\n{lines}\n]\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one month of AEMET data for the demo.")
    parser.add_argument("--month", required=True, help="Calendar month in UTC, e.g. 2025-03")
    args = parser.parse_args()

    api_key = os.environ.get("AEMET_API_KEY", "").strip()
    if not api_key:
        print("AEMET_API_KEY is not set. Run with: uv run --env-file .env python -m ...")
        return 1

    month_start = datetime.strptime(args.month, "%Y-%m").replace(tzinfo=UTC)
    [chunk] = month_chunks(month_start, month_start)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0) as http:
        client = AemetAntarcticaClient(http, api_key=SecretStr(api_key))
        for station in STATIONS.values():
            records = [
                trim(record) for record in client.fetch_raw_records(station, chunk.start, chunk.end)
            ]
            path = OUTPUT_DIR / f"{station.aemet_id}_{chunk.key}.json"
            write_records(path, records)
            timestamps = sorted(str(record.get("fhora")) for record in records)
            span = f"{timestamps[0]} to {timestamps[-1]}" if timestamps else "no data"
            print(f"{station.name}: {len(records)} records ({span}) -> {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
