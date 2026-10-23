"""Log HTTP requests through the final response body, including streaming."""

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.access")


def configure_access_logging() -> None:
    # This middleware replaces Uvicorn's untimed access entry. Keep its error
    # logger enabled so server failures still include their tracebacks.
    logging.getLogger("uvicorn.access").disabled = True


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status = 500
        logged = False

        def log_request() -> None:
            nonlocal logged
            logged = True
            elapsed_ms = (perf_counter() - started) * 1000
            client = scope.get("client")
            address = f"{client[0]}:{client[1]}" if client else "-"
            path = scope.get("raw_path", scope["path"].encode()).decode("ascii", errors="backslashreplace")
            query = scope.get("query_string", b"").decode("ascii", errors="backslashreplace")
            target = f"{path}?{query}" if query else path
            logger.info('%s - "%s %s HTTP/%s" %s duration_ms=%.1f',
                        address, scope["method"], target, scope.get("http_version", "1.1"), status, elapsed_ms)

        async def timed_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.pathsend" or (
                message["type"] == "http.response.body" and not message.get("more_body", False)
            ):
                log_request()

        try:
            await self.app(scope, receive, timed_send)
        finally:
            # Unhandled failures have no final response body inside middleware.
            if not logged:
                log_request()
