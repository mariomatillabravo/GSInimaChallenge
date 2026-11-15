"""Request middleware: a request ID for every request, and one access log line per request."""

import logging
import time
from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logs import bind_request_id, resolve_request_id

REQUEST_ID_HEADER: Final = "X-Request-ID"

access_logger = logging.getLogger("app.access")


class RequestContextMiddleware:
    """Tags each request with an ID (logs and ``X-Request-ID`` header) and logs its outcome.

    A plain ASGI middleware rather than Starlette's ``BaseHTTPMiddleware``: it does not run the
    application in a separate task, and it does not buffer responses.

    The ID is stored in a ``ContextVar`` and in ``request.state``. It is not reset when the
    request ends: each request runs in its own task with its own copy of the context, and keeping
    it lets the handler of unexpected errors, which runs outside this middleware, log it too.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = resolve_request_id(_header(scope, b"x-request-id"))
        bind_request_id(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500  # what the client gets if the application fails before answering
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            query = scope.get("query_string", b"").decode("latin-1")
            target = f"{scope['path']}?{query}" if query else scope["path"]
            access_logger.info(
                "%s %s %d %.1f ms",
                scope["method"],
                target,
                status,
                duration_ms,
                extra={
                    "http": {
                        "method": scope["method"],
                        "path": scope["path"],
                        "query": query,
                        "status": status,
                        "duration_ms": duration_ms,
                    }
                },
            )


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return bytes(value).decode("latin-1")
    return None
