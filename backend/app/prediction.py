"""CPU forecasts for the remaining local day, with no caller-controlled horizon."""

import asyncio
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import logging
import math
import os

import numpy as np

from app.db import VIENNA_TIMEZONE, get_live, get_prediction_history

logger = logging.getLogger(__name__)
MODEL = "mistralai/Timestral-5M"
MODEL_REVISION = "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f"
# Timestral forecasts at the context's sampling rate. Its context supports up to
# 32,768 steps (eight weeks at 5-minute cells is 16,128) and horizons up to 1,024
# steps (a full day at 5-minute cells is 288), so the collected 5-minute rate is
# used directly, without coarser bins.
STEP_SECONDS = 5 * 60
BIN_OFFSET_SECONDS = 60


def utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_time() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def day_bounds(now: datetime):
    local = now.astimezone(VIENNA_TIMEZONE)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Shift the entire grid one minute past each five-minute mark, so the final
    # cell straddles midnight and requests before a boundary keep the prior cutoff.
    cutoff = (int(now.timestamp()) - BIN_OFFSET_SECONDS) // STEP_SECONDS * STEP_SECONDS + BIN_OFFSET_SECONDS
    origin = datetime.fromtimestamp(cutoff, timezone.utc)
    history_start = (origin.astimezone(VIENNA_TIMEZONE) - timedelta(weeks=8)).astimezone(timezone.utc)
    # The final shifted cell straddles midnight; include it and pin API points at
    # 23:59:59. Otherwise the final four minutes would reuse the preceding cell.
    horizon = math.ceil((midnight.astimezone(timezone.utc) - origin).total_seconds() / STEP_SECONDS)
    return origin, history_start, midnight.astimezone(timezone.utc), horizon


@lru_cache(maxsize=1)
def load_forecaster():
    # Lazy loading keeps normal history/live requests independent of model startup.
    import torch
    from timestral import TimestralForecaster

    torch.set_num_threads(int(os.getenv("PREDICTION_THREADS", "1")))
    return TimestralForecaster.from_pretrained(
        MODEL, revision=MODEL_REVISION, device="cpu", cache_dir=os.getenv("TIMESTRAL_CACHE_DIR"),
    )


def forecast_contexts(contexts: list[np.ndarray], horizon: int) -> list[list[dict[str, float]]]:
    import torch

    model = load_forecaster()
    results = []
    with torch.inference_mode():
        for context in contexts:
            forecast = model.forecast(context[None, None, :], prediction_length=horizon)
            quantiles = np.stack([np.asarray(forecast.quantile(q))[0, 0] for q in (.1, .5, .9)], axis=-1)
            if quantiles.shape != (horizon, 3) or not np.isfinite(quantiles).all():
                raise ValueError("Timestral returned invalid predictions")
            if (np.diff(quantiles, axis=-1) < 0).any():
                raise ValueError("Timestral returned crossing quantiles")
            results.append([
                dict(zip(("p10", "capacity", "p90"), (round(float(value), 1) for value in row)))
                for row in np.clip(quantiles, 0, 100)
            ])
    return results


def build_contexts(locations, readings, origin, history_start):
    """Use up to eight weeks of 5-minute cells, starting at each gym's first cell."""
    bins = int((origin - history_start).total_seconds()) // STEP_SECONDS
    sums = {location["id"]: np.zeros(bins) for location in locations}
    counts = {location["id"]: np.zeros(bins, dtype=int) for location in locations}
    latest = {}
    for reading in readings:
        location_id = reading["location_id"]
        timestamp = datetime.fromisoformat(reading["recorded_at"].replace("Z", "+00:00"))
        value = reading["capacity"]
        index = int((timestamp - history_start).total_seconds() // STEP_SECONDS)
        if location_id not in sums or not 0 <= index < bins or not math.isfinite(value) or not 0 <= value <= 100:
            continue
        sums[location_id][index] += value
        counts[location_id][index] += 1
        latest[location_id] = max(latest.get(location_id, timestamp), timestamp)
    contexts, eligible, unavailable = [], [], []
    for location in locations:
        reason = None
        if location["id"] not in latest:
            reason = "No completed 5-minute readings are available yet."
        elif origin - latest[location["id"]] > timedelta(minutes=30):
            reason = "Recent readings are unavailable."
        if reason:
            unavailable.append({"location_id": location["id"], "title": location["title"],
                                "status": "unavailable", "reason": reason, "values": []})
            continue
        values = np.divide(sums[location["id"]], counts[location["id"]],
                           out=np.full(bins, np.nan), where=counts[location["id"]] > 0).astype(np.float32)
        # Newer gyms use their shorter history without artificial leading weeks.
        # Keep internal/trailing missing cells so every series still ends at origin.
        first_observed = np.flatnonzero(counts[location["id"]])[0]
        contexts.append(values[first_observed:])
        eligible.append({"location_id": location["id"], "title": location["title"],
                         "status": "ok", "reason": None})
    return contexts, eligible, unavailable


def prediction_points(values, reading, origin, midnight):
    """Continuous forecast: anchored at the latest reading, then one point per
    5-minute cell, with the final cell pinned at the last second of the day."""
    end = midnight - timedelta(seconds=1)
    points = []
    anchor_at = None
    if reading is not None:
        anchor_at = datetime.fromisoformat(reading["recorded_at"].replace("Z", "+00:00"))
        points.append({"recorded_at": utc_string(anchor_at),
                       **{key: float(reading["capacity"]) for key in ("capacity", "p10", "p90")}})
    for i, value in enumerate(values):
        timestamp = origin + timedelta(seconds=i * STEP_SECONDS)
        if anchor_at is not None and timestamp <= anchor_at:
            continue
        points.append({"recorded_at": utc_string(timestamp), **value})
    if points and points[-1]["recorded_at"] != utc_string(end):
        points.append(points[-1] | {"recorded_at": utc_string(end)})
    return points


class PredictionService:
    # Model values refresh every 5-minute cell; allow headroom for missed
    # collections and inference time.
    MAX_CACHE_AGE = timedelta(minutes=25)

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._cache: dict | None = None
        self._cache_key: tuple | None = None
        self._task: asyncio.Task | None = None

    async def start(self):
        # Warm the model so the first refresh is not slowed by loading weights.
        await asyncio.to_thread(load_forecaster)
        self._task = asyncio.create_task(self._worker(), name="prediction-refresh")

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def request_refresh(self):
        # Coalesce: one pending refresh already covers everything newer.
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    async def _worker(self):
        while True:
            await self._queue.get()
            try:
                await self.refresh()
            except Exception:
                logger.exception("Prediction refresh failed; keeping the last good cache")
            finally:
                self._queue.task_done()

    async def refresh(self):
        """Recompute the forecast once a new 5-minute cell has completed."""
        now = current_time()
        origin, history_start, midnight, horizon = day_bounds(now)
        # The collector fires every five minutes; each collection completes a new
        # 5-minute cell. During 00:00–00:01 the cutoff is still yesterday's 23:56;
        # today's end in the key makes the worker pick the day up immediately.
        key = (utc_string(origin), utc_string(midnight))
        if key == self._cache_key:
            return
        locations, readings = await get_prediction_history(utc_string(history_start), utc_string(origin))
        contexts, eligible, unavailable = await asyncio.to_thread(
            build_contexts, locations, readings, origin, history_start,
        )
        values = await asyncio.to_thread(forecast_contexts, contexts, horizon) if contexts else []
        self._cache = {
            "date": str(now.astimezone(VIENNA_TIMEZONE).date()),
            "generated_at": now,
            "origin": origin,
            "midnight": midnight,
            "locations": [dict(location, values=value) for location, value in zip(eligible, values)] + unavailable,
        }
        self._cache_key = key

    async def predict(self, location_id: int | None = None) -> dict:
        """Serve the cached forecast as a continuous series from the latest reading."""
        served_at = current_time()
        cache = self._cache
        if cache is None:
            self.request_refresh()
            raise RuntimeError("The prediction is not ready yet")
        if (served_at - cache["generated_at"] > self.MAX_CACHE_AGE
                or cache["date"] != str(served_at.astimezone(VIENNA_TIMEZONE).date())):
            # Nudge the worker so the next request can serve a fresh forecast.
            self.request_refresh()
            raise RuntimeError("No fresh prediction is available")
        selected = [l for l in cache["locations"] if location_id is None or l["location_id"] == location_id]
        if location_id is not None and not selected:
            raise LookupError("Unknown location")
        latest = {row["id"]: row for row in await get_live()}
        response = []
        for location in selected:
            points = (prediction_points(location["values"], latest.get(location["location_id"]),
                                        cache["origin"], cache["midnight"])
                      if location["values"] else [])
            response.append({k: v for k, v in location.items() if k != "values"} | {"points": points})
        return {"date": cache["date"], "timezone": "Europe/Vienna",
                "model": MODEL.rsplit("/", 1)[-1], "generated_at": utc_string(cache["generated_at"]),
                "context_end": utc_string(cache["origin"]),
                "valid_until": utc_string(cache["midnight"] - timedelta(seconds=1)), "locations": response}


prediction_service = PredictionService()
