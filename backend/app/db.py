import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "data/boulderbat.db")
VIENNA_TIMEZONE = ZoneInfo("Europe/Vienna")


async def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id   INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL REFERENCES locations(id),
                capacity    INTEGER NOT NULL,
                recorded_at TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_loc_time
            ON readings(location_id, recorded_at)
        """)
        await db.commit()


async def upsert_locations(locations: list[dict]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO locations(id, title, url) VALUES (?, ?, ?)",
            [(int(loc["id"]), loc["title"], loc["url"]) for loc in locations],
        )
        await db.commit()


async def insert_readings(locations: list[dict], recorded_at: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO readings(location_id, capacity, recorded_at) VALUES (?, ?, ?)",
            [(int(loc["id"]), loc["capacity"], recorded_at) for loc in locations],
        )
        await db.commit()


async def import_history_readings(readings: list[dict]) -> int:
    """Insert production history, skipping readings already present locally."""
    async with aiosqlite.connect(DB_PATH) as db:
        changes_before = db.total_changes
        await db.executemany(
            """
            INSERT INTO readings(location_id, capacity, recorded_at)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM readings WHERE location_id = ? AND recorded_at = ?
            )
            """,
            [
                (
                    int(reading["location_id"]),
                    int(reading["capacity"]),
                    reading["recorded_at"],
                    int(reading["location_id"]),
                    reading["recorded_at"],
                )
                for reading in readings
            ],
        )
        await db.commit()
        return db.total_changes - changes_before


async def get_live() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT l.id, l.title, l.url, r.capacity, r.recorded_at
            FROM locations l
            JOIN readings r ON r.location_id = l.id
            WHERE r.id IN (
                SELECT MAX(id) FROM readings GROUP BY location_id
            )
            ORDER BY l.title
        """)
        return [dict(row) for row in await cursor.fetchall()]


async def get_history(
    start: str,
    end: str,
    location_id: int | None = None,
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if location_id is not None:
            cursor = await db.execute("""
                SELECT l.id AS location_id, l.title, r.capacity, r.recorded_at
                FROM readings r
                JOIN locations l ON l.id = r.location_id
                WHERE r.recorded_at >= ? AND r.recorded_at < ?
                  AND r.location_id = ?
                ORDER BY r.recorded_at
            """, (start, end, location_id))
        else:
            cursor = await db.execute("""
                SELECT l.id AS location_id, l.title, r.capacity, r.recorded_at
                FROM readings r
                JOIN locations l ON l.id = r.location_id
                WHERE r.recorded_at >= ? AND r.recorded_at < ?
                ORDER BY r.recorded_at, l.title
            """, (start, end))
        return [dict(row) for row in await cursor.fetchall()]


async def get_typical_week(location_id: int) -> dict:
    """Average occupancy for each local weekday and hour, from 08:00 onward."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT capacity, recorded_at
            FROM readings
            WHERE location_id = ?
            ORDER BY recorded_at
        """, (location_id,))
        rows = await cursor.fetchall()

    buckets: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    weeks: set[tuple[int, int]] = set()
    for row in rows:
        recorded_at = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
        local_time = recorded_at.astimezone(VIENNA_TIMEZONE)
        if 8 <= local_time.hour < 24:
            buckets[(local_time.weekday(), local_time.hour)].append(row["capacity"])
            iso_year, iso_week, _ = local_time.isocalendar()
            weeks.add((iso_year, iso_week))

    return {
        "cells": [
            {
                "weekday": weekday,
                "hour": hour,
                "average_capacity": round(sum(capacities) / len(capacities), 1),
                "sample_count": len(capacities),
            }
            for (weekday, hour), capacities in sorted(buckets.items())
        ],
        "week_count": len(weeks),
    }
