import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.collector import collect_capacity
from app.db import get_history, get_live, init_db

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


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file = STATIC_DIR / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
