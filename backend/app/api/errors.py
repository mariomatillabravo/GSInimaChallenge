"""Translation of errors into HTTP responses, all in one place.

Business code raises domain errors (``app.core.exceptions``) and never deals with status codes.
Every error response has the same shape: ``{"error": {"code", "message", "parameter"}}``.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorDetail, ErrorResponse
from app.core.exceptions import (
    AppError,
    InvalidParameterError,
    NotFoundError,
    UpstreamError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)

# Most specific classes first: the first match wins.
_ERROR_MAPPING: tuple[tuple[type[AppError], int, str], ...] = (
    (InvalidParameterError, 422, "invalid_parameter"),
    (NotFoundError, 404, "not_found"),
    (UpstreamUnavailableError, 503, "upstream_unavailable"),
    (UpstreamTimeoutError, 504, "upstream_timeout"),
    (UpstreamError, 502, "upstream_error"),
)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)


def error_response(
    status_code: int, code: str, message: str, parameter: str | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, parameter=parameter))
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def _handle_app_error(request: Request, error: Exception) -> JSONResponse:
    for error_type, status_code, code in _ERROR_MAPPING:
        if isinstance(error, error_type):
            if isinstance(error, InvalidParameterError):
                return error_response(status_code, code, error.message, error.parameter)
            return error_response(status_code, code, str(error))
    return await _handle_unexpected_error(request, error)


async def _handle_request_validation_error(request: Request, error: Exception) -> JSONResponse:
    """Give FastAPI's own validation errors (missing or malformed parameters) the same shape."""
    problems = error.errors() if isinstance(error, RequestValidationError) else []
    first = problems[0] if problems else {}
    location = [str(part) for part in first.get("loc", ()) if part not in ("query", "path")]
    message = "; ".join(f"{'.'.join(map(str, p['loc'][1:]))}: {p['msg']}" for p in problems)
    return error_response(
        422, "invalid_parameter", message or "Invalid request.", ".".join(location) or None
    )


async def _handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    # The details stay in the server logs; clients never see stack traces or internals.
    logger.exception("Unexpected error while handling %s %s", request.method, request.url.path)
    return error_response(500, "internal_error", "An unexpected error occurred.")
