# Boulderbat

Find the best time to hang out at the gym.


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

### Import production data for local development

To seed a local database with the public production history, run:

```bash
cd backend
uv run python -m app.import_production_history --start 2026-05-17
```

The importer downloads history from `https://boulderbat.flofriday.dev` one day at a time, adds any missing readings to the local database, and is safe to run again. `--start` is required so it does not issue years of empty daily requests. Both dates use `YYYY-MM-DD` in Europe/Vienna: `--start` is inclusive, and `--end` is exclusive (default: tomorrow, including today's readings so far). Use `--dry-run` to download without writing, or `--start 2026-06-01 --end 2026-06-02` to import just one day. Deploy the date-based history API before using this importer against production.

### Occupancy forecast benchmark

[`notebooks/forecast_benchmark.ipynb`](notebooks/forecast_benchmark.ipynb) evaluates a
forecast made at 08:00 Europe/Vienna for the remainder of the day, in 15-minute
intervals. It compares an eight-week weekday/time average with Timestral 5M, 28M,
123M, and 209M using the same eight weeks of preceding history.

The notebook has an isolated, locked environment; it adds no app dependencies:

```bash
cd notebooks
uv sync --frozen --python 3.12
uv run jupyter lab forecast_benchmark.ipynb
```

Select the Python kernel from `notebooks/.venv` and run the cells in order. The
default database is `backend/data/boulderbat.db`; import history first if needed.
Change `DATABASE` in the notebook to evaluate another snapshot. The first run
downloads approximately 1.46 GB of official model weights and requires network
access. All inference uses CPU, four threads, and one gym/day per call.

For a complete headless run that saves outputs in the notebook:

```bash
cd notebooks
uv run jupyter nbconvert --to notebook --execute --inplace forecast_benchmark.ipynb --ExecutePreprocessor.timeout=3600
```

The last 28 complete local days are held out for testing; the preceding 28 days
validate preparation and settings. Gyms need eight weeks of history before each
forecast. The notebook reports missing data, exclusions, equal-gym/day accuracy,
paired day-bootstrap intervals, runtime, peak process RAM, and model artifact
sizes. All four model sizes remain visible; it does not choose a winner.

Forecasts, CSV tables, figures, logs, and a reproducibility manifest are saved to
ignored `notebooks/results/` directories keyed by data, settings, implementation,
and pinned model/dependency versions. Exact reruns reuse completed model runs;
the runtime JSON files retain the original measurements. Loading and downloads
are timed separately; cache warmth can affect those measurements. Validation must
succeed for every method before testing. Application endpoints and UI are unchanged.

Benchmark correctness checks (including cutoff leakage, missing targets, DST,
equal weighting, and bootstrap pairing):

```bash
cd notebooks
uv run python -m unittest discover -s tests -v
```

## API

Interactive docs are available locally at `http://localhost:8000/docs` and in production at [boulderbat.flofriday.dev/docs](https://boulderbat.flofriday.dev/docs).

### `GET /prediction`

Returns Timestral-5M occupancy predictions for the **remainder of today in
Europe/Vienna**, ending at **23:59:59**. It accepts only an optional `location_id`;
date, start, end, and horizon overrides are rejected with HTTP 422. Without a
location filter, every database location is included. Unknown locations return 404.

```bash
curl "http://localhost:8000/prediction?location_id=262"
```

The response includes `date`, `timezone`, `model`, `generated_at`, `context_end`,
`valid_until`, and `locations`. Each location has `location_id`, `title`, `status`,
`reason`, and `points` containing `recorded_at`, `capacity` (the median), `p10`,
and `p90` (the bounds of the central 80% prediction interval). Points are remaining
15-minute occupancy estimates, bounded to 0–100% and rounded to one decimal place.
The first point is at the response time; the last repeats the final 15-minute
estimate at 23:59:59, so no prediction timestamp falls on tomorrow.

The model reads eight local weeks of history in 15-minute bins ending at the
latest completed quarter-hour. Missing bins remain missing. Inference runs on CPU
outside the async request loop. The model stays loaded and forecasts are cached
until the next quarter-hour; requests share that computation. This current-time
forecast differs from the notebook's fixed 08:00 evaluation cutoff.

Locations with insufficient history or no valid reading within 30 minutes of
the context cutoff have `status: "unavailable"`, an explanation, and no points.
Model-loading/inference failures return 503 without affecting recorded history.
If a request crosses local midnight during inference, it returns 503 so a retry
uses the new day. The History tab refreshes every minute and shows predictions
only for today, as dashed continuations in the gym's color. Recorded lines stay
solid; a “Now” marker aligns with the latest selected forecastable gym sample.
A dashed connector joins each recent sample to its first prediction without
extending the recorded line or changing model uncertainty bounds. Gaps longer
than 15 minutes remain visible. Light bands in each gym's
color show the 80% prediction interval, with exact bounds available in the tooltip.

The code and model revision are pinned. The first prediction request downloads
about 21 MB of model files from the official Mistral Hugging Face repository;
later requests reuse them. `TIMESTRAL_CACHE_DIR` can select the model cache, and
`PREDICTION_THREADS` defaults to 1. Docker uses CPU-only PyTorch and persists the
model cache at `/data/models` alongside the database volume.

Check the API and chart preparation with:

```bash
cd backend
uv run python -m unittest discover -s tests -v
cd ../frontend
npm test
npm run lint
npm run build
```

### `GET /live`

Returns the most recent capacity reading for each of the 8 locations.

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

Returns readings for exactly one calendar day in Europe/Vienna. `date` is required in `YYYY-MM-DD` format; timestamps, `start`/`end` ranges, and other query parameters are rejected with HTTP 422. Add `location_id` to filter to a single location. The range includes local midnight and excludes the following midnight, so daylight-saving days contain 23 or 25 hours. Reading timestamps remain in UTC. Days without readings return an empty list.

```bash
# All locations, one Vienna calendar day
curl "http://localhost:8000/history?date=2026-04-27"

# Single location
curl "http://localhost:8000/history?date=2026-04-27&location_id=260"
```

### `GET /typical-week`

Returns average capacity for each local weekday and hour from 08:00 to midnight, using the latest eight local calendar weeks (including the current week). It also returns the number of weeks represented. `location_id` is required; timestamps are grouped in the `Europe/Vienna` timezone.

```bash
curl "http://localhost:8000/typical-week?location_id=262"
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
| 1001 | Blockfabrik   |
