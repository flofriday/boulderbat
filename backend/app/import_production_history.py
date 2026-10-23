"""Import the public Boulderbat history API into the local development database.

Run from ``backend`` with ``uv run python -m app.import_production_history``.
"""

import argparse
import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.db import import_history_readings, init_db, upsert_locations

PRODUCTION_API_URL = "https://boulderbat.flofriday.dev"
VIENNA_TIMEZONE = ZoneInfo("Europe/Vienna")


def parse_date(value: str) -> date:
    """Accept a calendar date, without a time or timezone."""
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            raise ValueError("Non-canonical date")
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Use a date in YYYY-MM-DD format: {value}") from error
    return day


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default=PRODUCTION_API_URL,
        help=f"Production API base URL (default: {PRODUCTION_API_URL})",
    )
    parser.add_argument(
        "--start",
        type=parse_date,
        required=True,
        help="First Europe/Vienna date to import (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--end",
        type=parse_date,
        default=None,
        help="Final Europe/Vienna date (YYYY-MM-DD, exclusive; default: tomorrow)",
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
    end = args.end or datetime.now(VIENNA_TIMEZONE).date() + timedelta(days=1)
    if args.start >= end:
        raise ValueError("--start must be before --end")

    api_url = args.api_url.rstrip("/")
    async with httpx.AsyncClient(base_url=api_url, timeout=60) as client:
        locations = await get_json(client, "/live")
        if not isinstance(locations, list):
            raise ValueError("Production API returned an unexpected response")
        if not args.dry_run:
            await init_db()
            await upsert_locations(locations)

        downloaded = inserted = 0
        day = args.start
        while day < end:
            readings = await get_json(client, "/history", date=day.isoformat())
            if not isinstance(readings, list):
                raise ValueError("Production API returned an unexpected response")
            downloaded += len(readings)
            if not args.dry_run:
                inserted += await import_history_readings(readings)
            day += timedelta(days=1)

    print(f"Downloaded {downloaded:,} readings from {api_url}, one day at a time.")
    if args.dry_run:
        print("Dry run: local database was not changed.")
    else:
        print(f"Imported {inserted:,} new readings; {downloaded - inserted:,} were already present.")


def main() -> None:
    args = parse_args()
    asyncio.run(import_production_history(args))


if __name__ == "__main__":
    main()
