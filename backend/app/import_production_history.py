"""Import the public Boulderbat history API into the local development database.

Run from ``backend`` with ``uv run python -m app.import_production_history``.
"""

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.db import import_history_readings, init_db, upsert_locations

PRODUCTION_API_URL = "https://boulderbat.flofriday.dev"
EARLIEST_POSSIBLE_READING = "2000-01-01T00:00:00Z"


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp and normalize it to UTC."""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid ISO 8601 timestamp: {value}") from error

    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError("Timestamp must include a timezone, for example ending in Z")
    return timestamp.astimezone(timezone.utc)


def format_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default=PRODUCTION_API_URL,
        help=f"Production API base URL (default: {PRODUCTION_API_URL})",
    )
    parser.add_argument(
        "--start",
        type=parse_timestamp,
        default=parse_timestamp(EARLIEST_POSSIBLE_READING),
        help=f"First reading to import (default: {EARLIEST_POSSIBLE_READING})",
    )
    parser.add_argument(
        "--end",
        type=parse_timestamp,
        default=None,
        help="Exclusive final timestamp to import (default: now)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and report the readings without writing to the database",
    )
    return parser.parse_args()


async def get_json(client: httpx.AsyncClient, path: str, **params: str) -> Any:
    response = await client.get(path, params=params)
    response.raise_for_status()
    return response.json()


async def import_production_history(args: argparse.Namespace) -> None:
    end = args.end or datetime.now(timezone.utc)
    if args.start >= end:
        raise ValueError("--start must be before --end")

    api_url = args.api_url.rstrip("/")
    async with httpx.AsyncClient(base_url=api_url, timeout=60) as client:
        locations = await get_json(client, "/live")
        readings = await get_json(
            client,
            "/history",
            start=format_timestamp(args.start),
            end=format_timestamp(end),
        )

    if not isinstance(locations, list) or not isinstance(readings, list):
        raise ValueError("Production API returned an unexpected response")

    print(f"Downloaded {len(readings):,} readings from {api_url}.")
    if args.dry_run:
        print("Dry run: local database was not changed.")
        return

    await init_db()
    await upsert_locations(locations)
    inserted = await import_history_readings(readings)
    print(f"Imported {inserted:,} new readings; {len(readings) - inserted:,} were already present.")


def main() -> None:
    args = parse_args()
    asyncio.run(import_production_history(args))


if __name__ == "__main__":
    main()
