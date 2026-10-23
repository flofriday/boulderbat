"""CPU forecasts for the remaining local day, with no caller-controlled horizon."""

import asyncio
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import logging
import math
import os

import numpy as np

from app.db import VIENNA_TIMEZONE, get_prediction_history

logger = logging.getLogger(__name__)
MODEL = "mistralai/Timestral-5M"
MODEL_REVISION = "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f"
STEP_SECONDS = 15 * 60


def utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_time() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def day_bounds(now: datetime):
    local = now.astimezone(VIENNA_TIMEZONE)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    origin = datetime.fromtimestamp(int(now.timestamp()) // STEP_SECONDS * STEP_SECONDS, timezone.utc)
    history_start = (origin.astimezone(VIENNA_TIMEZONE) - timedelta(weeks=8)).astimezone(timezone.utc)
    horizon = int((midnight.astimezone(timezone.utc) - origin).total_seconds()) // STEP_SECONDS
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
    """15-minute means on the UTC grid; missing bins remain NaN."""
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
        first = location["first_recorded_at"]
        first = datetime.fromisoformat(first.replace("Z", "+00:00")) if first else None
        # Match the notebook's left-edge availability test.
        first_bin = int(first.timestamp()) // STEP_SECONDS * STEP_SECONDS if first else None
        reason = None
        if first_bin is None or first_bin > history_start.timestamp():
            reason = "Eight weeks of history are needed for a prediction."
        elif location["id"] not in latest or origin - latest[location["id"]] > timedelta(minutes=30):
            reason = "Recent readings are unavailable."
        if reason:
            unavailable.append({"location_id": location["id"], "title": location["title"],
                                "status": "unavailable", "reason": reason, "values": []})
            continue
        values = np.divide(sums[location["id"]], counts[location["id"]],
                           out=np.full(bins, np.nan), where=counts[location["id"]] > 0).astype(np.float32)
        contexts.append(values)
        eligible.append({"location_id": location["id"], "title": location["title"],
                         "status": "ok", "reason": None})
    return contexts, eligible, unavailable


class PredictionService:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._cache_key = None
        self._cache = []

    async def predict(self, location_id: int | None = None) -> dict:
        async with self._lock:
            # Read the clock after acquiring the lock, including during midnight rollover.
            now = current_time()
            origin, history_start, midnight, horizon = day_bounds(now)
            key = utc_string(origin)
            if key != self._cache_key:
                locations, readings = await get_prediction_history(utc_string(history_start), utc_string(origin))
                if location_id is not None and not any(l["id"] == location_id for l in locations):
                    raise LookupError("Unknown location")
                contexts, eligible, unavailable = await asyncio.to_thread(
                    build_contexts, locations, readings, origin, history_start,
                )
                values = await asyncio.to_thread(forecast_contexts, contexts, horizon) if contexts else []
                self._cache = [dict(location, values=value) for location, value in zip(eligible, values)] + unavailable
                self._cache_key = key
            # If inference crossed midnight, recompute on a new request rather than expose yesterday's forecast.
            served_at = current_time()
            if served_at.astimezone(VIENNA_TIMEZONE).date() != now.astimezone(VIENNA_TIMEZONE).date():
                raise RuntimeError("The day changed while predicting; retry for today's forecast.")
            selected = [l for l in self._cache if location_id is None or l["location_id"] == location_id]
            if location_id is not None and not selected:
                raise LookupError("Unknown location")
            end = midnight - timedelta(seconds=1)
            response = []
            for location in selected:
                points = []
                for i, value in enumerate(location["values"]):
                    bin_start = origin + timedelta(seconds=i * STEP_SECONDS)
                    bin_end = bin_start + timedelta(seconds=STEP_SECONDS)
                    if bin_end <= served_at:
                        continue
                    points.append({"recorded_at": utc_string(max(bin_start, served_at)), **value})
                if points and points[-1]["recorded_at"] != utc_string(end):
                    points.append(points[-1] | {"recorded_at": utc_string(end)})
                response.append({k: v for k, v in location.items() if k != "values"} | {"points": points})
            return {"date": str(now.astimezone(VIENNA_TIMEZONE).date()), "timezone": "Europe/Vienna",
                    "model": MODEL.rsplit("/", 1)[-1], "generated_at": utc_string(served_at),
                    "context_end": utc_string(origin), "valid_until": utc_string(end), "locations": response}


prediction_service = PredictionService()
