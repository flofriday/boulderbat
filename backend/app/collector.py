import logging
from datetime import datetime, timezone

import httpx

from app.db import insert_readings, upsert_locations

logger = logging.getLogger(__name__)

CAPACITY_URL = (
    "https://boulderbar.net/wp-json/boulderbar/v1/capacity"
    "?locations=260%2C261%2C262%2C263%2C264%2C265%2C284"
)

# Blockfabrik uses a Boulderado client counter; the token is public (embedded in blockfabrik.at).
# ponytail: token hardcoded, scrape it from the homepage if it ever rotates.
BLOCKFABRIK_ID = 1001
BLOCKFABRIK_URL = (
    "https://backend.boulderado.app/api/gethc"
    "?token=eyJhbGciOiJIUzI1NiIsICJ0eXAiOiJKV1QifQ"
    ".eyJjdXN0b21lciI6IkJsb2NrZmFicmlrV2llbiJ9"
    ".yymz1Eg_-jX28iMdaq1aGVb0iD4-29uWVkuxZd7a_9U&sector="
)
# blockfabrik.at ignores the API's maxcount and divides by 250 — match what visitors see.
BLOCKFABRIK_FULL = 250


async def fetch_boulderbar(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(CAPACITY_URL)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != 1:
        raise ValueError(f"Unexpected API status: {data.get('status')}")
    return data["data"]


async def fetch_blockfabrik(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(BLOCKFABRIK_URL, follow_redirects=True)
    response.raise_for_status()
    counter = int(response.json()["counter"])
    return [{
        "id": BLOCKFABRIK_ID,
        "title": "Blockfabrik",
        "url": "https://www.blockfabrik.at/",
        "capacity": min(100, round(counter / BLOCKFABRIK_FULL * 100)),
    }]


async def collect_capacity() -> None:
    locations: list[dict] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for fetch in (fetch_boulderbar, fetch_blockfabrik):
            try:
                locations += await fetch(client)
            except Exception:
                logger.exception("Failed to collect capacity data via %s", fetch.__name__)

    if not locations:
        return
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    await upsert_locations(locations)
    await insert_readings(locations, recorded_at)
    logger.info("Collected capacity for %d locations at %s", len(locations), recorded_at)
