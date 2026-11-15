"""Logging setup: text or JSON lines, each one tagged with the ID of the request being served.

The request ID lives in a ``ContextVar``. The request middleware sets it, and every log record
picks it up, including records written by synchronous endpoints: they run in worker threads that
receive a copy of the request's context.
"""

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Final, Literal, TextIO

LogFormat = Literal["text", "json"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

NO_REQUEST: Final = "-"
"""Request ID of records written outside a request (startup, shutdown)."""

_request_id: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST)

_HANDLER_NAME: Final = "app"
"""Name of the handler installed here, so that configuring again replaces it."""

_SAFE_REQUEST_ID: Final = re.compile(r"[A-Za-z0-9._-]{1,128}")

# Attributes every LogRecord has; anything else on a record came from ``extra=`` and is output,
# except uvicorn's ``color_message`` (a copy of the message with terminal colour codes).
_NOT_EXTRAS: Final = frozenset(
    logging.LogRecord("", logging.INFO, "", 0, "", (), None).__dict__
) | {"message", "asctime", "request_id", "color_message"}


def resolve_request_id(incoming: str | None) -> str:
    """Reuse the caller's request ID when it is safe to write in logs; otherwise create one.

    Accepting any value would let a client inject line breaks or fake entries into the logs.
    """
    if incoming is not None and _SAFE_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def bind_request_id(request_id: str) -> None:
    """Tag the records written from now on, in this context, with ``request_id``."""
    _request_id.set(request_id)


def configure_logging(level: LogLevel, log_format: LogFormat, stream: TextIO | None = None) -> None:
    """Send every log record to ``stream`` (standard error by default) in the chosen format.

    Calling it again replaces the previous configuration instead of adding a second handler.
    """
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())

    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn's own messages go through the same handler, so that everything shares one format.
    # Its access log is replaced by the one written by the request middleware.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    # One line per HTTP call to AEMET is noise; failures are reported by the client itself.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


class TextFormatter(logging.Formatter):
    """``2026-11-15T12:00:00.123Z INFO 3f2a... app.services.measurements: message``."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(request_id)s %(name)s: %(message)s")

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return _utc_timestamp(record)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, easy to search and to ship to a log platform."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": _utc_timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", NO_REQUEST),
        }
        entry.update(
            (key, value) for key, value in record.__dict__.items() if key not in _NOT_EXTRAS
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        # Values that JSON cannot represent are written as text rather than failing.
        return json.dumps(entry, default=str, ensure_ascii=False)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def _utc_timestamp(record: logging.LogRecord) -> str:
    """ISO 8601 in UTC with milliseconds and ``Z``: unambiguous, even when clocks change."""
    moment = datetime.fromtimestamp(record.created, UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
