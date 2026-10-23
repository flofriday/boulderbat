import logging
from contextlib import asynccontextmanager
from datetime import date as CalendarDate
from pathlib import Path
import re
from typing import Annotated, Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.collector import collect_capacity
from app.db import get_history, get_live, get_typical_week, init_db
from app.prediction import prediction_service
from app.request_logging import RequestLoggingMiddleware, configure_access_logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_access_logging()
    await init_db()
    await collect_capacity()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(collect_capacity, "interval", minutes=5, id="collect")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Boulderbat Capacity API", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)


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


class HistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: CalendarDate = Field(
        gt=CalendarDate.min, lt=CalendarDate.max,
        description="Single calendar date in Europe/Vienna (YYYY-MM-DD)",
    )
    location_id: int | None = Field(None, description="Filter to a single location ID")

    @field_validator("date", mode="before")
    @classmethod
    def require_date_only(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Use a calendar date in YYYY-MM-DD format, without a time")
        return value


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
    params: Annotated[HistoryQuery, Query()],
):
    """Readings for one Europe/Vienna day, from midnight up to the next midnight.

    Only a date is accepted; timestamps and range parameters are rejected.
    Returned reading timestamps remain in UTC.
    """
    return await get_history(params.date, params.location_id)


@app.get("/typical-week", response_model=TypicalWeekResponse)
async def typical_week(
    location_id: int = Query(..., description="Location ID to summarize"),
):
    """Average occupancy for each weekday and hour in Europe/Vienna time."""
    return await get_typical_week(location_id)


@app.get("/prediction", response_model=PredictionResponse)
async def prediction(params: Annotated[PredictionQuery, Query()]):
    """Predict only the remainder of today, ending at 23:59:59 Europe/Vienna.

    Uses Timestral-5M with up to eight weeks of 15-minute history. No date or horizon
    override is accepted. Input bins and refresh boundaries are one minute past
    each quarter-hour (:01, :16, :31, :46), allowing fresh quarter-hour readings.
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
