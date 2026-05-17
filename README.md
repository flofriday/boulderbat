# Boulderbat

Polls [boulderbar.net](https://boulderbar.net) capacity data every 5 minutes and stores it in a local SQLite database. Exposes a small REST API to query live and historical capacity.

## Run with Docker

```bash
docker build -t boulderbat .
docker run -p 8000:8000 -v boulderbat-data:/data boulderbat
```

The `/data` volume persists the database across restarts.

## Run locally

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn app.main:app --reload
```

The server starts at `http://localhost:8000`. On startup it immediately fetches current capacity and then polls every 5 minutes.

By default the database is written to `data/boulderbat.db`. Override with the `DB_PATH` environment variable.

## API

Interactive docs are available at `http://localhost:8000/docs`.

### `GET /live`

Returns the most recent capacity reading for each of the 7 locations.

```bash
curl http://localhost:8000/live
```

```json
[
  {
    "id": 260,
    "title": "Linz",
    "url": "https://boulderbar.net/standorte/linz/",
    "capacity": 25,
    "recorded_at": "2026-04-28T12:00:00Z"
  },
  ...
]
```

### `GET /history`

Returns all readings within a time range. Both `start` and `end` are required ISO 8601 timestamps. Add `location_id` to filter to a single location.

```bash
# All locations, last 24 hours
curl "http://localhost:8000/history?start=2026-04-27T00:00:00Z&end=2026-04-28T00:00:00Z"

# Single location
curl "http://localhost:8000/history?start=2026-04-27T00:00:00Z&end=2026-04-28T00:00:00Z&location_id=260"
```

```json
[
  {
    "location_id": 260,
    "title": "Linz",
    "capacity": 42,
    "recorded_at": "2026-04-27T08:00:00Z"
  },
  ...
]
```

## Location IDs

| ID  | Location       |
|-----|----------------|
| 260 | Linz           |
| 261 | Salzburg       |
| 262 | Hannovergasse  |
| 263 | Hauptbahnhof   |
| 264 | Seestadt       |
| 265 | Wienerberg     |
| 284 | St. Pölten     |
