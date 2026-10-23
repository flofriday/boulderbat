"""Run with: uv run python -m unittest discover -s tests -v"""

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forecast_benchmark import (  # noqa: E402
    BASELINE, METHODS, Config, balanced_mean, baseline_forecasts, finalize_validation,
    paired_intervals, prepare, read_history, run_split, score, validate_predictions,
)


def history(start="2026-05-01", end="2026-09-01"):
    times = pd.date_range(start, end, freq="5min", tz="UTC", inclusive="left")
    local = times.tz_convert("Europe/Vienna")
    frame = pd.DataFrame({"time": times, "location_id": 1,
                          "capacity": local.weekday * 5. + local.hour})
    return frame, pd.DataFrame({"id": [1], "title": ["Test gym"]})


class PreparationTests(unittest.TestCase):
    def test_cutoff_and_seasonal_baseline(self):
        frame, locations = history()
        config = Config(validation_days=1, test_days=1, end_date="2026-08-31")
        cases, _, _, periods = prepare(frame, locations, config, now=pd.Timestamp("2026-09-02", tz="UTC"))
        self.assertEqual(periods["test_start"], "2026-08-30")
        self.assertEqual(len(cases), 2)
        case = cases[-1]
        self.assertEqual(len(case.actual), 64)
        self.assertEqual(len(case.context), 56 * 96)
        self.assertEqual(case.origin.hour, 8)
        np.testing.assert_allclose(case.actual, case.baseline)
        altered = frame.copy()
        altered.loc[altered.time >= case.origin, "capacity"] = 99.
        changed = prepare(altered, locations, config, now=pd.Timestamp("2026-09-02", tz="UTC"))[0][-1]
        np.testing.assert_equal(case.context, changed.context)
        np.testing.assert_equal(case.baseline, changed.baseline)
        self.assertFalse(np.array_equal(case.actual, changed.actual))

    def test_missing_context_and_targets_stay_missing(self):
        frame, locations = history()
        absent = (frame.time >= "2026-08-30T12:00Z") & (frame.time < "2026-08-30T12:15Z")
        context_gap = (frame.time >= "2026-08-29T03:00Z") & (frame.time < "2026-08-29T03:15Z")
        frame = frame[~(absent | context_gap)]
        config = Config(validation_days=1, test_days=1, end_date="2026-08-31")
        case = prepare(frame, locations, config, now=pd.Timestamp("2026-09-02", tz="UTC"))[0][-1]
        self.assertEqual(np.isnan(case.context).sum(), 1)
        self.assertEqual(case.mask.sum(), 63)
        self.assertTrue(np.isnan(case.actual[24]))  # 14:00 local

    def test_new_locations_excluded(self):
        frame, locations = history(start="2026-08-01")
        with self.assertRaisesRegex(ValueError, "No eligible"):
            prepare(frame, locations, Config(end_date="2026-08-31"), now=pd.Timestamp("2026-09-02", tz="UTC"))

    def test_dst_uses_local_eight_am_and_regular_context(self):
        for start, end, expected in [("2026-01-01", "2026-03-30", 5372),
                                     ("2026-08-01", "2026-10-26", 5380)]:
            with self.subTest(end=end):
                frame, locations = history(start, end)
                config = Config(validation_days=1, test_days=1, end_date=end)
                cases = prepare(frame, locations, config, now=pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=2))[0]
                self.assertEqual(cases[-1].origin.hour, 8)
                self.assertEqual(len(cases[-1].context), expected)
                self.assertEqual(len(cases[-1].actual), 64)
                np.testing.assert_allclose(cases[-1].baseline, cases[-1].actual)

    def test_partial_last_day_not_in_test(self):
        frame, locations = history(end="2026-08-31T10:00")
        periods = prepare(frame, locations, Config(validation_days=1, test_days=1),
                          now=pd.Timestamp("2026-09-02", tz="UTC"))[3]
        self.assertEqual(periods["end_exclusive"], "2026-08-31")

    def test_end_date_cannot_open_future_or_partial_day(self):
        frame, locations = history()
        with self.assertRaisesRegex(ValueError, "completed local date"):
            prepare(frame, locations, Config(end_date="2026-09-03"), now=pd.Timestamp("2026-09-02", tz="UTC"))

    def test_read_only_load_deduplicates_and_masks_invalid_values(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.db"
            with sqlite3.connect(path) as connection:
                connection.executescript("""
                    CREATE TABLE locations (id INTEGER, title TEXT);
                    INSERT INTO locations VALUES (1, 'Gym');
                    CREATE TABLE readings (id INTEGER, location_id INTEGER, capacity INTEGER, recorded_at TEXT);
                    INSERT INTO readings VALUES (1, 1, 20, '2026-08-01T08:00:00Z');
                    INSERT INTO readings VALUES (2, 1, 20, '2026-08-01T08:00:00Z');
                    INSERT INTO readings VALUES (3, 1, 200, '2026-08-01T08:05:00Z');
                """)
            before = path.read_bytes()
            frame, _, report = read_history(path)
            self.assertEqual(report, {"duplicate_rows_removed": 1, "invalid_values_masked": 1})
            self.assertEqual(frame.capacity.isna().sum(), 1)
            self.assertEqual(path.read_bytes(), before)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        frame, locations = history()
        self.cases = prepare(frame, locations, Config(validation_days=1, test_days=1, end_date="2026-08-31"),
                             now=pd.Timestamp("2026-09-02", tz="UTC"))[0]

    def test_identical_masks_and_known_error(self):
        baseline, _ = baseline_forecasts(self.cases)
        model = baseline.copy()
        model[:, :, 0] -= 5
        model[:, :, 1] += 2
        model[:, :, 2] += 5
        result = score(self.cases, {BASELINE: baseline, "Timestral-5M": model})
        overall = balanced_mean(result[result.window == "all"], ["method"])
        self.assertEqual(overall.loc["Timestral-5M", "mae_pp"], 2)
        self.assertEqual(overall.loc["Timestral-5M", "bias_pp"], 2)
        self.assertEqual(overall.loc["Timestral-5M", "coverage_80"], 1)
        self.assertEqual(overall.loc["Timestral-5M", "width_80_pp"], 10)
        self.assertEqual(result[result.window == "all"].bins.nunique(), 1)

    def test_model_cannot_hide_errors_by_returning_nan(self):
        prediction, _ = baseline_forecasts(self.cases)
        prediction[0, 0, 1] = np.nan
        with self.assertRaisesRegex(ValueError, "Missing/nonfinite"):
            validate_predictions(self.cases, prediction)

    def test_crossing_quantiles_rejected(self):
        prediction, _ = baseline_forecasts(self.cases)
        prediction[0, 0, 0] = prediction[0, 0, 1] + 1
        with self.assertRaisesRegex(ValueError, "Crossing"):
            validate_predictions(self.cases, prediction)

    def test_equal_gym_and_day_weights(self):
        rows = []
        for gym, errors in [("A", [0., 10.]), ("B", [20.])]:
            for error in errors:
                rows.append({"method": "m", "location": gym, "mae_pp": error,
                             "bias_pp": error, "coverage_80": .8, "width_80_pp": 10})
        self.assertEqual(balanced_mean(pd.DataFrame(rows), ["method"]).loc["m", "mae_pp"], 12.5)

    def test_bootstrap_pairs_dates_and_is_reproducible(self):
        baseline, _ = baseline_forecasts(self.cases)
        scores = score(self.cases, {BASELINE: baseline, "Timestral-5M": baseline + 2})
        first = paired_intervals(scores, samples=100, seed=3)
        pd.testing.assert_frame_equal(first, paired_intervals(scores, samples=100, seed=3))
        self.assertEqual(first.iloc[0].ci_95_low, first.iloc[0].ci_95_high)
        self.assertEqual(abs(first.iloc[0].mae_difference_a_minus_b_pp), 2)

    def test_bootstrap_keeps_gyms_on_the_same_sampled_date(self):
        rows = []
        # Daily cross-gym mean is always ten; independent per-gym date draws
        # would incorrectly introduce uncertainty here.
        for day, gym, error in [("d1", "A", 0.), ("d1", "B", 20.),
                                ("d2", "A", 20.), ("d2", "B", 0.)]:
            for method, value in [("a", error), ("b", 0.)]:
                rows.append({"day": day, "location": gym, "window": "all",
                             "method": method, "mae_pp": value})
        result = paired_intervals(pd.DataFrame(rows), samples=500).iloc[0]
        self.assertEqual(result.ci_95_low, 10.)
        self.assertEqual(result.ci_95_high, 10.)

    def test_test_split_requires_complete_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "validation"):
                run_split(folder, self.cases, "test", {}, Config())
            runtime = pd.DataFrame({"status": ["ok"]}, index=[BASELINE])
            with self.assertRaisesRegex(ValueError, "All five"):
                finalize_validation(folder, runtime)
            (Path(folder) / "manifest.json").write_text("{}")
            runtime = pd.DataFrame({"status": ["ok"] * 5}, index=METHODS)
            finalize_validation(folder, runtime)
            self.assertTrue((Path(folder) / "validation_complete.json").exists())


if __name__ == "__main__":
    unittest.main()
