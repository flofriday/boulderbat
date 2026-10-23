import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import httpx

from app import db
from app import import_production_history as importer
from app.main import app


class HistoryAPITests(unittest.TestCase):
    def setUp(self):
        # Deliberately skip lifespan: no collector, scheduler, or model downloads.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_date_is_required_and_timestamps_and_ranges_are_rejected(self):
        queries = [
            "", "start=2026-01-01&end=2026-12-31", "date=2026-02-30",
            "date=20261023", "date=2026-W43-5", "date=1792713600",
            "date=2026-10-23T00:00:00Z", "date=2026-10-23T12:00:00",
            "date=2026-10-23&start=2026-01-01",
            "date=2026-10-23&end=2026-12-31",
            "date=2026-10-23&days=365", "date=2026-10-23&location_id=nope",
            "date=0001-01-01", "date=9999-12-31",
        ]
        with patch("app.main.get_history", new_callable=AsyncMock) as history:
            for query in queries:
                with self.subTest(query=query):
                    self.assertEqual(self.client.get("/history?" + query).status_code, 422)
            history.assert_not_awaited()

    def test_parsed_date_and_optional_location_are_forwarded(self):
        with patch("app.main.get_history", new_callable=AsyncMock, return_value=[]) as history:
            for suffix, location in [("", None), ("&location_id=262", 262)]:
                response = self.client.get("/history?date=2026-10-23" + suffix)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])
                history.assert_awaited_with(date(2026, 10, 23), location)

    def test_only_one_local_day_including_dst_and_year_boundary(self):
        for day, start, end in [
            ("2026-10-23", "2026-10-22T22:00:00Z", "2026-10-23T22:00:00Z"),
            ("2026-03-29", "2026-03-28T23:00:00Z", "2026-03-29T22:00:00Z"),
            ("2026-10-25", "2026-10-24T22:00:00Z", "2026-10-25T23:00:00Z"),
            ("2026-12-31", "2026-12-30T23:00:00Z", "2026-12-31T23:00:00Z"),
        ]:
            with self.subTest(day=day), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "history.db"
                first = datetime.fromisoformat(start.replace("Z", "+00:00"))
                last = datetime.fromisoformat(end.replace("Z", "+00:00"))
                times = [first - timedelta(seconds=1), first, first + timedelta(hours=12),
                         last - timedelta(seconds=1), last]
                rows = [(260, i, value.isoformat().replace("+00:00", "Z"))
                        for i, value in enumerate(times, 1)]
                with patch.object(db, "DB_PATH", str(path)):
                    asyncio.run(db.init_db())
                    with closing(sqlite3.connect(path)) as connection, connection:
                        connection.executemany("INSERT INTO locations VALUES (?, ?, ?)",
                                               [(260, "A", "https://a.example"), (261, "B", "https://b.example")])
                        connection.executemany(
                            "INSERT INTO readings(location_id, capacity, recorded_at) VALUES (?, ?, ?)",
                            rows + [(261, 10, start)],
                        )
                    response = self.client.get("/history", params={"date": day})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual([row["capacity"] for row in response.json()], [2, 10, 3, 4])
                    response = self.client.get("/history", params={"date": day, "location_id": 260})
                    self.assertEqual([row["capacity"] for row in response.json()], [2, 3, 4])
                    self.assertTrue(all(row["location_id"] == 260 for row in response.json()))
                    self.assertEqual(self.client.get("/history", params={"date": day, "location_id": 999}).json(), [])


class ImporterTests(unittest.IsolatedAsyncioTestCase):
    async def test_downloads_and_saves_each_day_before_requesting_the_next(self):
        requests = []
        locations = [{"id": 260, "title": "A", "url": "https://a.example"}]
        with tempfile.TemporaryDirectory() as folder, patch.object(db, "DB_PATH", str(Path(folder) / "history.db")):
            def respond(request):
                requests.append((request.url.path, dict(request.url.params)))
                if request.url.path == "/live":
                    return httpx.Response(200, json=locations)
                if request.url.params["date"] == "2026-10-25":
                    with closing(sqlite3.connect(db.DB_PATH)) as connection:
                        self.assertEqual(connection.execute(
                            "SELECT count(*) FROM readings WHERE recorded_at = '2026-10-24T10:00:00Z'"
                        ).fetchone()[0], 1)
                reading = {"location_id": 260, "capacity": 10,
                           "recorded_at": request.url.params["date"] + "T10:00:00Z"}
                return httpx.Response(200, json=[reading])

            clients = [httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(respond))
                       for _ in range(2)]
            args = argparse.Namespace(api_url="https://example.test", start=date(2026, 10, 24),
                                      end=date(2026, 10, 26), dry_run=False)
            with patch.object(importer.httpx, "AsyncClient", side_effect=clients), redirect_stdout(io.StringIO()) as output:
                await importer.import_production_history(args)
                await importer.import_production_history(args)
            self.assertEqual(requests, [("/live", {}), ("/history", {"date": "2026-10-24"}),
                                        ("/history", {"date": "2026-10-25"})] * 2)
            self.assertIn("Imported 2 new readings; 0 were already present.", output.getvalue())
            self.assertIn("Imported 0 new readings; 2 were already present.", output.getvalue())

    async def test_dry_run_never_writes_and_default_end_includes_today(self):
        now = datetime(2026, 10, 23, 22, 30, tzinfo=timezone.utc).astimezone(importer.VIENNA_TIMEZONE)
        args = argparse.Namespace(api_url="https://example.test", start=date(2026, 10, 24), end=None, dry_run=True)
        with patch.object(importer, "datetime") as clock, \
             patch.object(importer, "get_json", new_callable=AsyncMock, return_value=[]) as get_json, \
             patch.object(importer, "init_db", new_callable=AsyncMock) as init_db, \
             patch.object(importer, "upsert_locations", new_callable=AsyncMock) as upsert, \
             patch.object(importer, "import_history_readings", new_callable=AsyncMock) as insert, \
             redirect_stdout(io.StringIO()):
            clock.now.return_value = now
            await importer.import_production_history(args)
            self.assertEqual(get_json.await_args_list[-1].kwargs, {"date": "2026-10-24"})
            init_db.assert_not_awaited()
            upsert.assert_not_awaited()
            insert.assert_not_awaited()

    def test_cli_requires_canonical_dates(self):
        for value in ["2026-02-30", "20261023", "2026-10-23T00:00:00Z"]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                importer.parse_date(value)
        self.assertEqual(importer.parse_date("2026-10-23"), date(2026, 10, 23))


if __name__ == "__main__":
    unittest.main()
