import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from app.collector import collect_capacity
from app.db import get_history, get_live, get_typical_week, init_db
from app.prediction import prediction_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await collect_capacity()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(collect_capacity, "interval", minutes=5, id="collect")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Boulderbat Capacity API", lifespan=lifespan)


class LiveReading(BaseModel):
    id: int
    title: str
    url: str
    capacity: int
    recorded_at: str


class HistoryReading(BaseModel):
    location_id: int
    title: str
    capacity: int
    recorded_at: str


class TypicalWeekReading(BaseModel):
    weekday: int
    hour: int
    average_capacity: float
    sample_count: int


class TypicalWeekResponse(BaseModel):
    cells: list[TypicalWeekReading]
    week_count: int


class PredictionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int | None = None


class PredictionPoint(BaseModel):
    capacity: float = Field(ge=0, le=100)
    p10: float = Field(ge=0, le=100, description="Lower bound of the central 80% prediction interval")
    p90: float = Field(ge=0, le=100, description="Upper bound of the central 80% prediction interval")
    recorded_at: str


class LocationPrediction(BaseModel):
    location_id: int
    title: str
    status: Literal["ok", "unavailable"]
    reason: str | None
    points: list[PredictionPoint]


class PredictionResponse(BaseModel):
    date: str
    timezone: str
    model: str
    generated_at: str
    context_end: str
    valid_until: str
    locations: list[LocationPrediction]


@app.get("/live", response_model=list[LiveReading])
async def live():
    """Latest capacity reading for every location."""
    rows = await get_live()
    if not rows:
        raise HTTPException(503, "No data collected yet")
    return rows


@app.get("/history", response_model=list[HistoryReading])
async def history(
    start: datetime = Query(..., description="Range start (ISO 8601, e.g. 2026-04-28T00:00:00Z)"),
    end: datetime = Query(..., description="Range end (ISO 8601)"),
    location_id: int | None = Query(None, description="Filter to a single location ID"),
):
    """All readings within a time range, optionally filtered by location."""

    def to_utc(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return await get_history(to_utc(start), to_utc(end), location_id)


@app.get("/typical-week", response_model=TypicalWeekResponse)
async def typical_week(
    location_id: int = Query(..., description="Location ID to summarize"),
):
    """Average occupancy for each weekday and hour in Europe/Vienna time."""
    return await get_typical_week(location_id)


@app.get("/prediction", response_model=PredictionResponse)
async def prediction(params: Annotated[PredictionQuery, Query()]):
    """Predict only the remainder of today, ending at 23:59:59 Europe/Vienna.

    Uses Timestral-5M with eight weeks of 15-minute history. No date or horizon
    override is accepted. Model results refresh with each completed 15-minute bin.
    """
    try:
        return await prediction_service.predict(params.location_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except Exception as error:
        logger.exception("Today's prediction failed")
        raise HTTPException(503, "Today's prediction is temporarily unavailable. Please try again.") from error


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file = STATIC_DIR / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
