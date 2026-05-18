# Boulderbat

Polls [boulderbar.net](https://boulderbar.net) capacity data every 5 minutes and stores it in a local SQLite database. Exposes a REST API and a React frontend to view live and historical capacity.

## Run with Docker

Build the image:

```bash
docker build -t boulderbat .
```

Run the container:

```bash
docker run -p 8000:8000 -v boulderbat-data:/data  boulderbat
```

The frontend is available at `http://localhost:8000`. The named volume `boulderbat-data` persists the database across restarts.


## Run locally

Requires [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/).

**Backend:**

```bash
cd backend
uv sync
uv run fastapi dev main.py
```

(`fastapi dev` enables auto-reload. Use `fastapi run main.py` for the production server.)

**Frontend (dev server with HMR):**

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies `/live` and `/history` to the backend at `http://localhost:8000`.

To build the frontend for production (served by the backend):

```bash
cd frontend && npm run build
```

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
