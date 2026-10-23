import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import numpy as np
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.prediction import MODEL, MODEL_REVISION, PredictionService, build_contexts, day_bounds, forecast_contexts, load_forecaster, utc_string

VIENNA = ZoneInfo("Europe/Vienna")


def local(value):
    return datetime.fromisoformat(value).replace(tzinfo=VIENNA).astimezone(timezone.utc)


class PredictionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = local("2026-10-23T14:37:00")
        self.origin, self.start, _, _ = day_bounds(self.now)
        self.locations = [{"id": 262, "title": "Hannovergasse", "first_recorded_at": "2026-05-01T00:00:00Z"}]
        self.readings = [
            {"location_id": 262, "capacity": 10, "recorded_at": utc_string(self.start)},
            {"location_id": 262, "capacity": 20, "recorded_at": utc_string(self.origin - timedelta(minutes=5))},
        ]
        self.service = PredictionService()
        self.clock = patch("app.prediction.current_time", return_value=self.now).start()
        self.history = patch("app.prediction.get_prediction_history", new_callable=AsyncMock,
                             return_value=(self.locations, self.readings)).start()
        self.model = patch("app.prediction.forecast_contexts", side_effect=lambda contexts, horizon:
                           [[{"capacity": float(i), "p10": max(0., i - 2.), "p90": i + 2.}
                             for i in range(horizon)] for _ in contexts]).start()
        self.addCleanup(patch.stopall)

    async def test_only_remaining_today_and_exact_last_second(self):
        result = await self.service.predict()
        self.assertEqual(result["date"], "2026-10-23")
        self.assertEqual(result["model"], "Timestral-5M")
        points = result["locations"][0]["points"]
        self.assertEqual(points[0]["recorded_at"], utc_string(self.now))
        self.assertEqual(points[-1]["recorded_at"], "2026-10-23T21:59:59Z")
        self.assertEqual(points[-1] | {"recorded_at": points[-2]["recorded_at"]}, points[-2])
        for point in points:
            self.assertLessEqual(point["p10"], point["capacity"])
            self.assertGreaterEqual(point["p90"], point["capacity"])
            timestamp = datetime.fromisoformat(point["recorded_at"].replace("Z", "+00:00"))
            self.assertEqual(timestamp.astimezone(VIENNA).date(), self.now.astimezone(VIENNA).date())
            self.assertGreaterEqual(timestamp, self.now)
        self.history.assert_awaited_once_with(utc_string(self.start), utc_string(self.origin))
        self.assertEqual(self.model.call_args.args[1], 38)

    async def test_cache_and_concurrent_requests(self):
        responses = await asyncio.gather(*(self.service.predict(262) for _ in range(4)))
        self.assertEqual(len(responses), 4)
        self.history.assert_awaited_once()
        self.model.assert_called_once()
        self.clock.return_value = self.now + timedelta(minutes=10)
        await self.service.predict()
        self.assertEqual(self.model.call_count, 2)

    async def test_insufficient_or_stale_history_is_explicit(self):
        self.locations += [{"id": 1, "title": "New gym", "first_recorded_at": "2026-10-01T00:00:00Z"},
                           {"id": 2, "title": "Offline gym", "first_recorded_at": "2026-05-01T00:00:00Z"}]
        result = await self.service.predict()
        unavailable = [l for l in result["locations"] if l["status"] == "unavailable"]
        self.assertEqual(len(unavailable), 2)
        self.assertTrue(all(l["points"] == [] and l["reason"] for l in unavailable))
        self.assertEqual(len(self.model.call_args.args[0]), 1)

    async def test_unknown_location_does_not_run_model(self):
        with self.assertRaises(LookupError):
            await self.service.predict(999)
        self.model.assert_not_called()

    async def test_last_second_never_adds_tomorrow(self):
        self.clock.return_value = local("2026-10-23T23:59:59")
        self.readings.append({"location_id": 262, "capacity": 5,
                              "recorded_at": utc_string(local("2026-10-23T23:40:00"))})
        result = await self.service.predict()
        self.assertEqual(result["locations"][0]["points"], [{"recorded_at": result["valid_until"], "capacity": 0., "p10": 0., "p90": 2.}])
        self.assertEqual(self.model.call_args.args[1], 1)

    async def test_midnight_invalidates_cache(self):
        await self.service.predict()
        self.clock.return_value = local("2026-10-24T00:01:00")
        self.readings.append({"location_id": 262, "capacity": 1,
                              "recorded_at": utc_string(local("2026-10-23T23:55:00"))})
        result = await self.service.predict()
        self.assertEqual(result["date"], "2026-10-24")
        self.assertEqual(self.model.call_count, 2)

    async def test_midnight_during_inference_does_not_serve_yesterday(self):
        self.clock.side_effect = [local("2026-10-23T23:59:59"), local("2026-10-24T00:00:01")]
        with self.assertRaisesRegex(RuntimeError, "day changed"):
            await self.service.predict()

    def test_context_missing_bins_and_cutoff(self):
        self.readings += [
            {"location_id": 262, "capacity": 100, "recorded_at": utc_string(self.origin)},
            {"location_id": 262, "capacity": 99, "recorded_at": utc_string(self.origin + timedelta(minutes=5))},
        ]
        contexts, eligible, unavailable = build_contexts(self.locations, self.readings, self.origin, self.start)
        self.assertEqual(len(eligible), 1)
        self.assertFalse(unavailable)
        self.assertEqual(contexts[0][-1], 20)
        self.assertEqual(np.isfinite(contexts[0]).sum(), 2)

    def test_dst_day_and_history_lengths(self):
        for day, history_bins in [("2026-03-29", 5372), ("2026-10-25", 5380)]:
            origin, start, midnight, horizon = day_bounds(local(day + "T08:00:00"))
            self.assertEqual((origin - start).total_seconds() / 900, history_bins)
            self.assertEqual(horizon, 64)
            self.assertEqual(midnight.astimezone(VIENNA).hour, 0)
            self.assertEqual(str((midnight - timedelta(seconds=1)).astimezone(VIENNA).date()), day)


class APITests(unittest.TestCase):
    def setUp(self):
        # No lifespan context: collector/scheduler never run in API unit tests.
        self.client = TestClient(app)

    def test_no_date_or_horizon_override(self):
        with patch("app.main.prediction_service.predict", new_callable=AsyncMock) as predict:
            for query in ("date=2026-10-24", "start=2026-10-24", "end=2026-10-25", "horizon=192"):
                self.assertEqual(self.client.get("/prediction?" + query).status_code, 422)
            predict.assert_not_awaited()

    def test_unknown_location_and_model_failure(self):
        with patch("app.main.prediction_service.predict", new_callable=AsyncMock, side_effect=LookupError("Unknown location")):
            self.assertEqual(self.client.get("/prediction?location_id=999").status_code, 404)
        with patch("app.main.prediction_service.predict", new_callable=AsyncMock, side_effect=RuntimeError("internal error")):
            response = self.client.get("/prediction")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("internal error", response.text)

    def test_successful_location_filter_response(self):
        result = {"date": "2026-10-23", "timezone": "Europe/Vienna", "model": "Timestral-5M",
                  "generated_at": "2026-10-23T12:30:00Z", "context_end": "2026-10-23T12:30:00Z",
                  "valid_until": "2026-10-23T21:59:59Z", "locations": [{"location_id": 262,
                  "title": "Hannovergasse", "status": "ok", "reason": None,
                  "points": [{"recorded_at": "2026-10-23T21:59:59Z", "capacity": 12.3, "p10": 9.3, "p90": 15.3}]}]}
        with patch("app.main.prediction_service.predict", new_callable=AsyncMock, return_value=result) as predict:
            response = self.client.get("/prediction?location_id=262")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), result)
            predict.assert_awaited_once_with(262)


class ModelOutputTests(unittest.TestCase):
    def test_default_model_revision_and_single_inference_thread(self):
        load_forecaster.cache_clear()
        self.addCleanup(load_forecaster.cache_clear)
        with patch.dict(os.environ):
            os.environ.pop("PREDICTION_THREADS", None)
            with patch("torch.set_num_threads") as threads, patch("timestral.TimestralForecaster.from_pretrained") as factory:
                load_forecaster()
                threads.assert_called_once_with(1)
                self.assertEqual(MODEL, "mistralai/Timestral-5M")
                self.assertEqual(MODEL_REVISION, "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f")
                self.assertEqual(factory.call_args.args, (MODEL,))
                self.assertEqual(factory.call_args.kwargs["revision"], MODEL_REVISION)
                self.assertEqual(factory.call_args.kwargs["device"], "cpu")

    def test_physical_bounds_clean_rounding_and_invalid_output(self):
        from unittest.mock import Mock
        model = Mock()
        quantiles = {.1: [-20, 10.2, 110], .5: [-10, 20.4, 120], .9: [5, 30.8, 130]}
        model.forecast.return_value.quantile.side_effect = lambda q: np.array([[quantiles[q]]], dtype=np.float32)
        with patch("app.prediction.load_forecaster", return_value=model):
            self.assertEqual(forecast_contexts([np.ones(8)], 3), [[
                {"capacity": 0., "p10": 0., "p90": 5.},
                {"capacity": 20.4, "p10": 10.2, "p90": 30.8},
                {"capacity": 100., "p10": 100., "p90": 100.},
            ]])
            model.forecast.return_value.quantile.side_effect = lambda q: np.array([[[np.nan]]])
            with self.assertRaisesRegex(ValueError, "invalid predictions"):
                forecast_contexts([np.ones(8)], 1)

    def test_crossing_quantiles_are_rejected(self):
        from unittest.mock import Mock
        model = Mock()
        model.forecast.return_value.quantile.side_effect = lambda q: np.array([[[100 * (1 - q)]]])
        with patch("app.prediction.load_forecaster", return_value=model):
            with self.assertRaisesRegex(ValueError, "crossing quantiles"):
                forecast_contexts([np.ones(8)], 1)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_exclusive_cutoff_and_location_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.db"
            with sqlite3.connect(path) as connection:
                connection.executescript("""
                    CREATE TABLE locations (id INTEGER PRIMARY KEY, title TEXT);
                    INSERT INTO locations VALUES (1, 'Gym');
                    CREATE TABLE readings (location_id INTEGER, capacity INTEGER, recorded_at TEXT);
                    INSERT INTO readings VALUES (1, 10, '2026-05-01T00:00:00Z');
                    INSERT INTO readings VALUES (1, 20, '2026-10-23T12:25:00Z');
                    INSERT INTO readings VALUES (1, 99, '2026-10-23T12:30:00Z');
                """)
            connection.close()
            with patch.object(db, "DB_PATH", str(path)):
                locations, readings = await db.get_prediction_history("2026-08-28T12:30:00Z", "2026-10-23T12:30:00Z")
            self.assertEqual(locations[0]["first_recorded_at"], "2026-05-01T00:00:00Z")
            self.assertEqual([r["capacity"] for r in readings], [20])


if __name__ == "__main__":
    unittest.main()
