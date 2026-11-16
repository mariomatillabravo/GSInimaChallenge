"""Write the OpenAPI document of the API to a file, or check that the file is up to date.

The front-end generates its TypeScript types from this file, so it is committed and has to change
together with the API. Building the document needs no server and no API key: the application is
created in demo mode and asked for its schema.

Usage (from the ``backend`` directory):

    uv run python -m scripts.export_openapi            # write ../frontend/openapi.json
    uv run python -m scripts.export_openapi --check    # exit with status 1 if it is out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def render_openapi() -> str:
    """The OpenAPI document as stable, readable JSON with a final newline."""
    document = create_app(Settings(_env_file=None, demo_mode=True)).openapi()
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="fail if the file differs instead of writing it"
    )
    args = parser.parse_args()
    output: Path = args.output
    expected = render_openapi()

    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else None
        if current != expected:
            print(f"{output} is out of date. Run `make api-types` and commit the result.")
            return 1
        print(f"{output} is up to date.")
        return 0

    # Bytes with "\n" line endings on every OS, as .gitattributes stores them.
    output.write_bytes(expected.encode("utf-8"))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
