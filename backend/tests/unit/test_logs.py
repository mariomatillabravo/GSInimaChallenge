"""Unit tests of the logging setup: formats, request IDs and configuration."""

import contextvars
import io
import json
import logging
import re

import pytest

from app.core.logs import bind_request_id, configure_logging, resolve_request_id

HEX_32 = re.compile(r"[0-9a-f]{32}")


def configured(log_format: str) -> io.StringIO:
    stream = io.StringIO()
    configure_logging("DEBUG", "json" if log_format == "json" else "text", stream=stream)
    return stream


def json_lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.parametrize("incoming", ["abc-123", "3f2a9c.1_X", "a" * 128])
def test_a_safe_incoming_request_id_is_reused(incoming: str) -> None:
    assert resolve_request_id(incoming) == incoming


@pytest.mark.parametrize(
    "incoming",
    [None, "", "a" * 129, "two\nlines", "with spaces", 'quote"s', "ñandú"],
    ids=["missing", "empty", "too long", "line break", "spaces", "quotes", "non-ascii"],
)
def test_an_unsafe_or_missing_request_id_is_replaced(incoming: str | None) -> None:
    assert HEX_32.fullmatch(resolve_request_id(incoming))


def test_json_lines_carry_the_standard_fields_and_the_extras() -> None:
    stream = configured("json")

    logging.getLogger("app.test").info("hello %s", "world", extra={"http": {"status": 200}})

    (entry,) = json_lines(stream)
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["message"] == "hello world"
    assert entry["request_id"] == "-"  # written outside any request
    assert entry["http"] == {"status": 200}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", str(entry["time"]))


def test_json_lines_include_the_traceback_and_survive_unusual_values() -> None:
    stream = configured("json")

    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("app.test").exception("failed", extra={"odd": {1, 2}})

    (entry,) = json_lines(stream)
    assert "ValueError: boom" in str(entry["exception"])
    assert entry["odd"] == "{1, 2}"  # a set is not JSON: written as text


def test_uvicorn_colour_codes_are_left_out() -> None:
    stream = configured("json")

    logging.getLogger("uvicorn.error").info(
        "Started server process [1]", extra={"color_message": "Started [\x1b[36m%d\x1b[0m]"}
    )

    (entry,) = json_lines(stream)
    assert "color_message" not in entry


def test_records_are_tagged_with_the_request_id_of_their_context() -> None:
    stream = configured("json")

    def inside_a_request() -> None:
        bind_request_id("abc-123")
        logging.getLogger("app.test").info("inside")

    contextvars.copy_context().run(inside_a_request)
    logging.getLogger("app.test").info("outside")

    assert [entry["request_id"] for entry in json_lines(stream)] == ["abc-123", "-"]


def test_text_lines_are_readable_in_a_terminal() -> None:
    stream = configured("text")

    logging.getLogger("app.test").warning("careful")

    assert re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z WARNING - app\.test: careful\n", stream.getvalue()
    )


def test_configuring_again_replaces_the_handler_and_quiets_noisy_loggers() -> None:
    configured("text")
    configured("json")

    ours = [handler for handler in logging.getLogger().handlers if handler.get_name() == "app"]
    assert len(ours) == 1
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").disabled
    assert logging.getLogger("uvicorn").propagate
