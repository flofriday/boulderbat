import logging
from datetime import datetime, timezone

import httpx

from app.db import insert_readings, upsert_locations

logger = logging.getLogger(__name__)

CAPACITY_URL = (
    "https://boulderbar.net/wp-json/boulderbar/v1/capacity"
    "?locations=260%2C261%2C262%2C263%2C264%2C265%2C284"
)


async def collect_capacity() -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(CAPACITY_URL)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != 1:
            raise ValueError(f"Unexpected API status: {data.get('status')}")

        locations = data["data"]
        recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        await upsert_locations(locations)
        await insert_readings(locations, recorded_at)
        logger.info("Collected capacity for %d locations at %s", len(locations), recorded_at)
    except Exception:
        logger.exception("Failed to collect capacity data")
