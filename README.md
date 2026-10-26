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

HTTP access logs include the status code and server-side response duration in
milliseconds, for example:

```text
INFO:app.access:127.0.0.1:54321 - "GET /history?date=2026-10-23 HTTP/1.1" 200 duration_ms=12.4
```

Timing runs from request entry through sending the final response body (including
streamed responses). It excludes background tasks after the response; browser
download times may differ. Failed requests are timed until failure. Uvicorn's default access
entry is disabled at startup to avoid duplicate request logs; its error logging
remains enabled.

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
and `p90` (the bounds of the central 80% prediction interval). Points are
occupancy estimates at 5-minute steps, bounded to 0–100% and rounded to one
decimal place. The first point repeats the latest recorded reading, so the
forecast continues the observed line without a seam; the last point repeats the
final estimate at 23:59:59, so no prediction timestamp falls on tomorrow.

The model reads up to eight local weeks of history in 5-minute cells, with both
input intervals and refresh boundaries shifted one minute past each five-minute
mark (`:01`, `:06`, `:11`, …). For example, the last input cell at 15:06 covers
15:01–15:06 and includes readings timestamped 15:05, provided they have been saved
before inference reads the database. The cutoff is exclusive: readings at 15:06
belong to the next cell. Timestral forecasts at the context's sampling rate and
supports 32,768 context steps (eight weeks at 5-minute cells is 16,128), so the
response serves the model's 5-minute estimates directly, one per cell, between
the latest reading and 23:59:59.

Each collection (every five minutes) enqueues a background refresh. The worker
recomputes the model when a cell boundary has passed; the endpoint always serves
the cached forecast, so inference never runs on the request path.

Newer locations use all available history within that window, starting at their
first observed cell. Internal gaps remain missing. Inference runs on CPU outside
the async request loop, in a background worker started at boot. The model stays
loaded and requests share the cached computation. A cache older than 25 minutes,
or one from the previous local day, is not served; the endpoint returns 503 and
nudges the worker so a retry gets a fresh forecast. The final forecast interval
is clipped at 23:59:59; API points never extend into tomorrow. This
current-time forecast differs from the notebook's fixed 08:00 evaluation cutoff
and unshifted bins.

Locations with no valid reading in a completed 5-minute cell, or no valid reading
within 30 minutes of the context cutoff, have `status: "unavailable"`, an
explanation, and no points. There is no minimum number of weeks for app forecasts;
the notebook retains its eight-week eligibility rule for the benchmark.
Model-loading/inference failures return 503 without affecting recorded history,
and a failed refresh keeps the last good cache. The History tab refreshes every
minute and shows predictions only for today, as dashed continuations in the gym's
color. Recorded lines stay solid; a “Now” marker aligns with the latest selected
forecastable gym sample. The dashed prediction starts at the latest sample, so
the recorded and predicted lines meet without a connector. Gaps longer
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

## Native Apple app

The SwiftUI app, watch companion, and configurable WidgetKit widgets live in
[`apple/`](apple/README.md). Open [`apple/Boulderbat.xcodeproj`](apple/Boulderbat.xcodeproj)
to run on Mac, iPhone, iPad, Apple Watch, or Apple Vision Pro. Live cards and widgets
combine current occupancy with recorded history, today’s forecast, and its 80% range.
