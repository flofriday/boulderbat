import os
from pathlib import Path

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "data/boulderbat.db")


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
                WHERE r.recorded_at BETWEEN ? AND ?
                  AND r.location_id = ?
                ORDER BY r.recorded_at
            """, (start, end, location_id))
        else:
            cursor = await db.execute("""
                SELECT l.id AS location_id, l.title, r.capacity, r.recorded_at
                FROM readings r
                JOIN locations l ON l.id = r.location_id
                WHERE r.recorded_at BETWEEN ? AND ?
                ORDER BY r.recorded_at, l.title
            """, (start, end))
        return [dict(row) for row in await cursor.fetchall()]
