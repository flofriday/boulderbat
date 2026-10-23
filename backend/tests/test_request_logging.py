import logging
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.request_logging import RequestLoggingMiddleware, configure_access_logging


def http_scope():
    return {"type": "http", "method": "GET", "path": "/history",
            "raw_path": b"/history", "query_string": b"date=2026-10-23",
            "http_version": "1.1", "client": ("127.0.0.1", 1234)}


class RequestLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_is_timed_to_final_chunk_and_background_work_is_excluded(self):
        send = AsyncMock()
        with patch("app.request_logging.perf_counter", return_value=10.0) as clock, \
             self.assertLogs("app.access", level="INFO") as logs:
            async def streamed(scope, receive, send_response):
                clock.return_value = 10.1
                await send_response({"type": "http.response.start", "status": 200, "headers": []})
                clock.return_value = 10.2
                await send_response({"type": "http.response.body", "body": b"first", "more_body": True})
                self.assertEqual(logs.output, [])
                clock.return_value = 10.45
                await send_response({"type": "http.response.body", "body": b"last"})
                clock.return_value = 15.0  # Background task after response.

            await RequestLoggingMiddleware(streamed)(http_scope(), AsyncMock(), send)
        self.assertEqual(send.await_count, 3)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('127.0.0.1:1234 - "GET /history?date=2026-10-23 HTTP/1.1" 200 duration_ms=450.0', logs.output[0])

    async def test_unhandled_failure_is_logged_and_propagated(self):
        async def failing(scope, receive, send):
            raise RuntimeError("failure")

        with patch("app.request_logging.perf_counter", side_effect=[10.0, 10.125]), \
             self.assertLogs("app.access", level="INFO") as logs, \
             self.assertRaisesRegex(RuntimeError, "failure"):
            await RequestLoggingMiddleware(failing)(http_scope(), AsyncMock(), AsyncMock())
        self.assertEqual(len(logs.output), 1)
        self.assertIn("500 duration_ms=125.0", logs.output[0])

    async def test_lifespan_and_websocket_messages_are_passed_through(self):
        for scope in [{"type": "lifespan"}, {"type": "websocket"}]:
            wrapped = AsyncMock()
            receive, send = AsyncMock(), AsyncMock()
            with patch("app.request_logging.logger.info") as log:
                await RequestLoggingMiddleware(wrapped)(scope, receive, send)
            wrapped.assert_awaited_once_with(scope, receive, send)
            log.assert_not_called()


class AccessLogConfigurationTests(unittest.TestCase):
    def test_native_access_entry_is_disabled_without_disabling_error_logger(self):
        access, errors = logging.getLogger("uvicorn.access"), logging.getLogger("uvicorn.error")
        with patch.object(access, "disabled", False), patch.object(errors, "disabled", False):
            configure_access_logging()
            self.assertTrue(access.disabled)
            self.assertFalse(errors.disabled)

    def test_validation_response_is_logged_once_with_duration(self):
        # No lifespan: no database writes, collector, scheduler, or model load.
        with self.assertLogs("app.access", level="INFO") as logs:
            client = TestClient(app)
            try:
                response = client.get("/history?date=invalid")
            finally:
                client.close()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('"GET /history?date=invalid HTTP/1.1" 422 duration_ms=', logs.output[0])


if __name__ == "__main__":
    unittest.main()
