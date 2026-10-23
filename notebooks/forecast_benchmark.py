"""Data preparation, evaluation and artifacts for forecast_benchmark.ipynb.

No application imports or database writes. All cutoffs are exclusive.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time

import numpy as np
import pandas as pd

TIMEZONE = "Europe/Vienna"
BASELINE = "Weekday average (8 weeks)"
MODELS = {f"Timestral-{size}M": f"mistralai/Timestral-{size}M" for size in (5, 28, 123, 209)}
METHODS = [BASELINE, *MODELS]
WINDOWS = ["08–12", "12–16", "16–20", "20–24"]


@dataclass(frozen=True)
class Config:
    history_weeks: int = 8
    validation_days: int = 28
    test_days: int = 28
    threads: int = 4
    bootstrap_samples: int = 2000
    seed: int = 42
    # Exclusive local date; None derives it from the last observed bin and now.
    end_date: str | None = None


@dataclass
class Case:
    location_id: int
    title: str
    day: str
    split: str
    origin: pd.Timestamp
    times: pd.DatetimeIndex
    context: np.ndarray
    actual: np.ndarray
    baseline: np.ndarray
    counts: np.ndarray

    @property
    def key(self):
        return f"{self.day}_{self.location_id}"

    @property
    def mask(self):
        # Independent of model predictions. Model failures cannot shrink this mask.
        return np.isfinite(self.actual) & np.isfinite(self.baseline)


def read_history(path: Path):
    path = path.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        frame = pd.read_sql_query(
            "SELECT location_id, capacity, recorded_at FROM readings ORDER BY recorded_at, id",
            connection,
        )
        locations = pd.read_sql_query("SELECT id, title FROM locations ORDER BY id", connection)
    if frame.empty:
        raise ValueError("The selected database has no readings.")
    frame["time"] = pd.to_datetime(frame.recorded_at, utc=True, errors="raise")
    frame["capacity"] = pd.to_numeric(frame.capacity, errors="coerce")
    duplicates = frame.duplicated(["location_id", "time"]).sum()
    conflicting = frame.groupby(["location_id", "time"]).capacity.nunique().gt(1).any()
    if conflicting:
        raise ValueError("Conflicting values at the same location/timestamp; resolve before benchmarking.")
    frame = frame.drop_duplicates(["location_id", "time"])
    invalid = (~frame.capacity.between(0, 100)).sum()
    frame.loc[~frame.capacity.between(0, 100), "capacity"] = np.nan
    return frame, locations, {"duplicate_rows_removed": int(duplicates), "invalid_values_masked": int(invalid)}


def prepare(frame, locations, config: Config, now=None):
    """Resample on a regular UTC grid; match the seasonal baseline in local time."""
    if min(config.history_weeks, config.validation_days, config.test_days, config.threads,
           config.bootstrap_samples) <= 0:
        raise ValueError("Configuration counts must be positive.")
    now = pd.Timestamp.now(tz=TIMEZONE) if now is None else pd.Timestamp(now).tz_convert(TIMEZONE)
    observed_through = frame.time.max().ceil("15min").tz_convert(TIMEZONE)
    available_end = min(now, observed_through).normalize()
    end = pd.Timestamp(config.end_date, tz=TIMEZONE) if config.end_date else available_end
    if end != end.normalize() or end > available_end:
        raise ValueError("end_date must be a completed local date boundary supported by the snapshot.")
    test_start = end - pd.DateOffset(days=config.test_days)
    start = test_start - pd.DateOffset(days=config.validation_days)
    days = pd.date_range(start, end, freq="D", inclusive="left")
    cases, quality, exclusions = [], [], []
    for location in locations.itertuples(index=False):
        raw = frame[frame.location_id == location.id].set_index("time").capacity.sort_index()
        if raw.empty or raw.notna().sum() == 0:
            exclusions.append({"location": location.title, "reason": "No valid history"})
            continue
        # A bin timestamp is its left edge; a bin is available only at its right edge.
        bins = raw.resample("15min", label="left", closed="left").agg(["mean", "count"])
        first = raw.dropna().index.min().floor("15min")
        first_eligible = first.tz_convert(TIMEZONE) + pd.DateOffset(weeks=config.history_weeks)
        eligible_days = 0
        for day in days:
            origin = pd.Timestamp(f"{day.date()} 08:00", tz=TIMEZONE)
            history_start = origin - pd.DateOffset(weeks=config.history_weeks)
            if first > history_start.tz_convert("UTC"):
                exclusions.append({"location": location.title, "day": str(day.date()),
                                   "reason": "Less than eight weeks of preceding history"})
                continue
            history_times = pd.date_range(history_start, origin, freq="15min", inclusive="left").tz_convert("UTC")
            context = bins["mean"].reindex(history_times).to_numpy(dtype=np.float32)
            # Keep nights and NaNs in the context; never splice out missing time.
            local = history_times.tz_convert(TIMEZONE)
            seasonal = pd.DataFrame({"value": context, "weekday": local.weekday,
                                     "hour": local.hour, "minute": local.minute})
            means = seasonal.groupby(["weekday", "hour", "minute"]).value.mean()
            times = pd.date_range(origin, day + pd.DateOffset(days=1), freq="15min", inclusive="left")
            assert len(times) == 64
            baseline = np.array([means.get((t.weekday(), t.hour, t.minute), np.nan) for t in times])
            target = bins.reindex(times.tz_convert("UTC"))
            case = Case(int(location.id), location.title, str(day.date()),
                        "test" if day >= test_start else "validation", origin, times,
                        context, target["mean"].to_numpy(), baseline,
                        target["count"].fillna(0).to_numpy())
            if not case.mask.any():
                exclusions.append({"location": location.title, "day": case.day,
                                   "reason": "No observed targets with seasonal baseline support"})
                continue
            cases.append(case)
            eligible_days += 1
        first_morning = pd.Timestamp(f"{first_eligible.date()} 08:00", tz=TIMEZONE)
        if first_morning < first_eligible:
            first_morning += pd.DateOffset(days=1)
        quality.append({
            "location": location.title,
            "first_reading": raw.index.min().tz_convert(TIMEZONE),
            "last_reading": raw.index.max().tz_convert(TIMEZONE),
            "earliest_08_forecast": first_morning,
            "raw_readings": len(raw), "empty_15min_bins": int(bins["count"].eq(0).sum()),
            "partially_observed_bins": int(bins["count"].between(1, 2).sum()),
            "eligible_days": eligible_days,
        })
    if not cases:
        raise ValueError("No eligible gym/days. Import more history or change end_date.")
    periods = {"validation_start": str(start.date()), "test_start": str(test_start.date()),
               "end_exclusive": str(end.date())}
    return cases, pd.DataFrame(quality), pd.DataFrame(exclusions), periods


def case_coverage(cases):
    return pd.DataFrame([{
        "day": c.day, "location": c.title, "split": c.split,
        "context_coverage": float(np.isfinite(c.context).mean()),
        "observed_target_bins": int(np.isfinite(c.actual).sum()),
        "scored_target_bins": int(c.mask.sum()),
        "missing_baseline_bins_with_observations": int((np.isfinite(c.actual) & ~np.isfinite(c.baseline)).sum()),
        "partially_observed_target_bins": int(((c.counts > 0) & (c.counts < 3)).sum()),
    } for c in cases])


def file_hash(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def freeze_experiment(directory, database, config, cases, periods, revisions):
    """Content-addressed results: changed data/settings/code never reuse old forecasts."""
    here = Path(__file__).resolve().parent
    manifest = {
        "config": asdict(config), "periods": periods, "database_sha256": file_hash(database),
        "model_revisions": revisions, "timestral_code_revision": "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff",
        "code_sha256": {name: file_hash(here / name) for name in ("forecast_benchmark.py", "timestral_worker.py", "uv.lock")},
        "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
        "case_keys": [c.key for c in cases],
    }
    encoded = json.dumps(manifest, sort_keys=True, indent=2)
    root = Path(directory) / hashlib.sha256(encoded.encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(encoded + "\n")
    return root


def baseline_forecasts(cases):
    start = time.perf_counter()
    predictions = np.stack([np.stack([c.baseline] * 3, axis=-1) for c in cases])
    elapsed = time.perf_counter() - start
    return predictions, {"status": "ok", "load_seconds": 0., "download_seconds": 0.,
                         "artifact_mb": 0., "median_inference_ms": np.nan,
                         "p95_inference_ms": np.nan, "peak_process_ram_mb": np.nan,
                         "note": f"Seasonal means computed during shared preparation; array assembly {elapsed:.4f}s."}


def run_timestral(root, cases, name, revision, threads):
    """Each size/split runs in a fresh process, batch size one, CPU float32."""
    split = cases[0].split
    folder = Path(root) / split / name
    folder.mkdir(parents=True, exist_ok=True)
    predictions_path, stats_path = folder / "predictions.npy", folder / "runtime.json"
    if predictions_path.exists() and stats_path.exists():
        return np.load(predictions_path), json.loads(stats_path.read_text())
    input_path = folder / "inputs.npz"
    np.savez(input_path, **{f"context_{i}": c.context for i, c in enumerate(cases)})
    command = [sys.executable, str(Path(__file__).with_name("timestral_worker.py")),
               "--inputs", str(input_path), "--output", str(folder), "--model", MODELS[name],
               "--revision", revision, "--threads", str(threads),
               "--cache", str(Path(root).parent / "model_cache")]
    process = subprocess.run(command, text=True, capture_output=True)
    (folder / "worker.log").write_text(process.stdout + "\n" + process.stderr)
    if process.returncode:
        raise RuntimeError(f"{name} failed; see {folder / 'worker.log'}\n{process.stderr[-2000:]}")
    input_path.unlink()
    return np.load(predictions_path), json.loads(stats_path.read_text())


def run_split(root, cases, split, revisions, config):
    if split == "test":
        marker = Path(root) / "validation_complete.json"
        if not marker.exists() or json.loads(marker.read_text()) != {
            "manifest_sha256": file_hash(Path(root) / "manifest.json"), "methods": METHODS
        }:
            raise ValueError("Run and finalize validation for this exact experiment before testing.")
    selected = [c for c in cases if c.split == split]
    if not selected:
        raise ValueError(f"No eligible cases in {split}.")
    predictions, runtime = {}, {}
    for name in METHODS:
        print(f"{split}: {name} ({len(selected)} gym/days)", flush=True)
        try:
            pred, stats = (baseline_forecasts(selected) if name == BASELINE else
                           run_timestral(root, selected, name, revisions[name], config.threads))
            validate_predictions(selected, pred, intervals=name != BASELINE)
            predictions[name], runtime[name] = pred, stats
        except Exception as error:
            runtime[name] = {"status": "failed", "error": str(error)}
            print(f"FAILED: {error}", flush=True)
    return selected, predictions, pd.DataFrame(runtime).T.rename_axis("method")


def finalize_validation(root, runtime):
    if set(runtime.index) != set(METHODS) or not runtime.status.eq("ok").all():
        raise ValueError("All five methods must pass validation before opening the test results.")
    marker = {"manifest_sha256": file_hash(Path(root) / "manifest.json"), "methods": METHODS}
    (Path(root) / "validation_complete.json").write_text(json.dumps(marker, indent=2) + "\n")


def validate_predictions(cases, predictions, intervals=True):
    if predictions.shape != (len(cases), 64, 3):
        raise ValueError(f"Unexpected prediction shape {predictions.shape}.")
    for case, values in zip(cases, predictions):
        if not np.isfinite(values[case.mask]).all():
            raise ValueError(f"Missing/nonfinite predictions on scored targets: {case.key}")
        if intervals and ((values[case.mask, 0] > values[case.mask, 1]).any() or
                          (values[case.mask, 1] > values[case.mask, 2]).any()):
            raise ValueError(f"Crossing quantiles: {case.key}")


def score(cases, predictions):
    rows = []
    for method, array in predictions.items():
        validate_predictions(cases, array, method != BASELINE)
        for case, values in zip(cases, array):
            for window, begin, end in [("all", 8, 24), *zip(WINDOWS, (8, 12, 16, 20), (12, 16, 20, 24))]:
                mask = case.mask & (case.times.hour >= begin) & (case.times.hour < end)
                if not mask.any():
                    continue
                lower, median, upper = values[mask].T
                actual = case.actual[mask]
                rows.append({"method": method, "location": case.title, "day": case.day,
                             "window": window, "bins": int(mask.sum()),
                             "mae_pp": float(np.abs(median - actual).mean()),
                             "bias_pp": float((median - actual).mean()),
                             "coverage_80": float(((lower <= actual) & (actual <= upper)).mean()) if method != BASELINE else np.nan,
                             "width_80_pp": float((upper - lower).mean()) if method != BASELINE else np.nan})
    return pd.DataFrame(rows)


def balanced_mean(frame, by):
    """First weight days equally within each gym, then gyms equally."""
    columns = ["mae_pp", "bias_pp", "coverage_80", "width_80_pp"]
    return frame.groupby([*by, "location"])[columns].mean().groupby(by).mean()


def leaderboard(scores, runtime):
    overall = balanced_mean(scores[scores.window == "all"], ["method"])
    if BASELINE in overall.index:
        baseline = overall.loc[BASELINE, "mae_pp"]
        overall["improvement_vs_baseline_pct"] = (1 - overall.mae_pp / baseline) * 100 if baseline else np.nan
    result = overall.join(runtime, how="outer").reindex(METHODS)
    return result


def paired_intervals(scores, samples=2000, seed=42):
    """Paired date bootstrap: one date draw shared by all gyms and methods.

    Average days within gym then gyms; missing gym/days retain their recorded mask.
    Day-level intervals do not account for dependence between successive days.
    """
    pivot = scores[scores.window == "all"].pivot(index=["day", "location"], columns="method", values="mae_pp")
    days = sorted(pivot.index.get_level_values("day").unique())
    gyms = sorted(pivot.index.get_level_values("location").unique())
    index = pd.MultiIndex.from_product([days, gyms], names=["day", "location"])
    pivot = pivot.reindex(index)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(days), size=(samples, len(days)))
    rows = []
    for left, right in itertools.combinations(pivot.columns, 2):
        difference = (pivot[left] - pivot[right]).to_numpy().reshape(len(days), len(gyms))
        boot = difference[draws]
        counts = np.isfinite(boot).sum(axis=1)
        per_gym = np.divide(np.nansum(boot, axis=1), counts,
                            out=np.full(counts.shape, np.nan), where=counts > 0)
        estimates = np.nanmean(per_gym, axis=1)
        low, high = np.quantile(estimates, [0.025, 0.975])
        rows.append({"method_a": left, "method_b": right,
                     "mae_difference_a_minus_b_pp": float(np.nanmean(np.nanmean(difference, axis=0))),
                     "ci_95_low": low, "ci_95_high": high})
    return pd.DataFrame(rows)


def plot_tradeoff(table):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    for name in MODELS:
        if name in table.index and table.loc[name, "status"] == "ok":
            row = table.loc[name]
            ax.scatter(row.median_inference_ms, row.mae_pp)
            ax.annotate(name, (row.median_inference_ms, row.mae_pp), xytext=(5, 5), textcoords="offset points")
    if BASELINE in table.index:
        ax.axhline(table.loc[BASELINE, "mae_pp"], linestyle="--", color="grey", label="Eight-week baseline")
    ax.set(xlabel="Warm CPU inference per gym/day (ms)", ylabel="MAE (occupancy percentage points)")
    ax.legend()
    fig.tight_layout()
    return fig


def plot_examples(cases, predictions, scores):
    import matplotlib.pyplot as plt
    # Selection is fixed by baseline errors, never by which Timestral looks best.
    ranked = scores[(scores.method == BASELINE) & (scores.window == "all")].sort_values(["mae_pp", "day", "location"])
    if ranked.empty:
        return []
    figures = []
    for label, row in [("Representative (median baseline error)", ranked.iloc[len(ranked) // 2]),
                       ("Worst baseline day", ranked.iloc[-1])]:
        index = next(i for i, c in enumerate(cases) if c.day == row.day and c.title == row.location)
        case = cases[index]
        fig, axes = plt.subplots(2, 2, figsize=(13, 7), sharex=True, sharey=True)
        for ax, method in zip(axes.flat, MODELS):
            ax.plot(case.times, case.actual, color="black", label="Observed", linewidth=1.7)
            ax.plot(case.times, case.baseline, color="grey", linestyle="--", label="Weekday average")
            if method in predictions:
                low, median, high = predictions[method][index].T
                ax.plot(case.times, median, label=method)
                ax.fill_between(case.times, low, high, alpha=.2, label="80% interval")
            else:
                ax.text(.5, .5, "Model failed — see results", transform=ax.transAxes, ha="center")
            import matplotlib.dates as mdates
            from zoneinfo import ZoneInfo
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=ZoneInfo(TIMEZONE)))
            ax.set(title=method, ylabel="Occupancy (%)")
            ax.legend(fontsize=8)
        fig.suptitle(f"{label}: {case.title}, {case.day} (Europe/Vienna)")
        fig.tight_layout()
        figures.append(fig)
    return figures
