# Project Athena API

Project Athena API 0.1.0 is a thin, deterministic FastAPI service over the existing
[Project Athena](https://github.com/DataScienceConsultants/project-athena) analytics engine. It is
only a service and delivery layer: it neither copies nor recalculates Athena's scientific logic.

## Architecture

HTTP routers depend on a focused `AthenaService`, which invokes Athena's public unified Observatory
intelligence builder once per request. API-owned payloads use Pydantic; the full Observatory report
and its time-series section pass through Athena's `to_dict()` serialization unchanged. There is no
database, authentication, background processing, scheduler, or frontend.

Project Athena is the historical seismic analytics engine. Project Athena API delivers those results
over HTTP. Project Seismic is a separate, broader project and is not implemented by this service.

## Install and run

Python 3.12 is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m app
# For auto-reload during local development instead:
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
```

Athena is installed directly from its GitHub repository at commit
`89166e33128aac5b1eae9c3f2e161441bd9ca744`; the exact immutable pin is recorded in
`pyproject.toml` because no release tag was available when version 0.1.0 was prepared. Athena source
is not vendored here.

> **Integration note:** version 0.1.0 expects Athena to expose
> `src.observatory.build_observatory_intelligence_report`, accepting `region_key` and
> `catalog_path`, and returning an object with `to_dict()`. Any upstream incompatibility must be
> resolved in Athena rather than by copying or reimplementing its internals here.

## Deployment

The repository includes a minimal Python 3.12 container. It installs the immutable Athena pin and
starts Uvicorn directly (without a development reloader), binds every container interface, honors
the platform `PORT`, and trusts forwarded proxy headers:

```bash
docker build -t project-athena-api .
docker run --rm -p 8000:8000 \
  -e ATHENA_ALLOWED_ORIGINS=https://datascienceconsultants.github.io \
  project-athena-api
```

The production start command, whether or not a container is used, is:

```bash
PORT=8000 python -m app
```

### Runtime catalog strategy

No production catalog is checked into or bundled with the image. The old generated sample is only
`tests/fixtures/catalog.csv` and is never a production default. Run the reproducible bootstrap:

```bash
python -m app.bootstrap_catalog
```

It resolves the configured Puerto Rico bounds, downloads through Athena's public catalog API, lets
Athena validate and deduplicate the events, and atomically replaces
`ATHENA_DEFAULT_CATALOG_PATH`. A failed or empty download exits nonzero and preserves an existing
catalog; it never falls back to fixture data. The command logs its requested UTC range and event
count. The default one-year lookback is intended to provide enough history for Observatory analysis.

The container runs this command once before Uvicorn starts. Thus Cloud Run makes no USGS request per
HTTP request, while a failed preparation prevents an instance with misleading data from becoming
available. The container also installs `config/regions.json` alongside Athena as a compatibility
measure for Athena 0.4.1, whose wheel does not include that package data.

For Cloud Run, build and deploy while explicitly configuring the production origin and catalog
policy (the filesystem is writable for the life of an instance):

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPOSITORY/project-athena-api
gcloud run deploy project-athena-api \
  --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/project-athena-api \
  --region REGION \
  --set-env-vars ATHENA_ALLOWED_ORIGINS=https://datascienceconsultants.github.io,ATHENA_BOOTSTRAP_LOOKBACK_DAYS=365,ATHENA_CATALOG_FRESHNESS_HOURS=72
```

Cloud Run refreshes the catalog whenever it starts a new instance. To refresh a running deployment
predictably, deploy a new revision (for example, update `ATHENA_BOOTSTRAP_END_UTC` or use
`gcloud run services update project-athena-api --update-env-vars ATHENA_BOOTSTRAP_END_UTC=...`).
Outside Cloud Run, rerun the bootstrap command before restarting the API. Do not refresh by calling
an analytical endpoint.

## Configuration

All settings have local defaults and may be overridden independently:

| Variable | Default |
| --- | --- |
| `ATHENA_API_NAME` | `Project Athena API` |
| `ATHENA_API_VERSION` | `0.1.0` |
| `ATHENA_VERSION` | pinned commit shown above |
| `ATHENA_DEFAULT_REGION_KEY` | `puerto_rico` |
| `ATHENA_DEFAULT_CATALOG_PATH` | `data/catalog.csv` |
| `ATHENA_BOOTSTRAP_LOOKBACK_DAYS` | `365` |
| `ATHENA_BOOTSTRAP_START_UTC` | unset; overrides lookback when set |
| `ATHENA_BOOTSTRAP_END_UTC` | current UTC time |
| `ATHENA_CATALOG_FRESHNESS_HOURS` | `72` |
| `ATHENA_ENVIRONMENT` | `development` |
| `ATHENA_ALLOWED_ORIGINS` | local origins on ports `3000` and `5173` |
| `PORT` | `8000` |

### CORS

`ATHENA_ALLOWED_ORIGINS` is a comma-separated exact allowlist. Localhost and `127.0.0.1` origins on
ports 3000 and 5173 are allowed only when the variable is unset. Production should explicitly set:

```bash
ATHENA_ALLOWED_ORIGINS=https://datascienceconsultants.github.io
```

Add multiple origins with commas. Do not configure `*`: credentialed CORS requires explicit origins.
An explicitly empty value disables cross-origin access.

## Endpoints

- `GET /health` — lightweight service health; never runs Athena.
- `GET /version` — API, Athena, and Python runtime versions.
- `GET /status` — concise status derived from the unified report.
- `GET /summary` — stable, frontend-ready historical summary for Project Seismic's MVP.
- `GET /observatory` — Athena's complete serialized unified report.
- `GET /timeseries` — only the unified report's serialized `time_series` section.
- `GET /` — service discovery.

Analytical endpoints validate that the catalog exists, has at least one event, and its newest event
is no older than `ATHENA_CATALOG_FRESHNESS_HOURS`. Missing, empty, malformed, or stale catalogs get
the same safe HTTP 503 response; `/health` remains lightweight liveness and does not read a catalog.

Deployment smoke tests (the first three should return HTTP 200):

```bash
BASE_URL=http://127.0.0.1:8000
curl --fail --show-error "$BASE_URL/health"
curl --fail --show-error "$BASE_URL/version"
curl --fail --show-error "$BASE_URL/summary"
curl --fail --show-error "$BASE_URL/observatory"
curl --fail --show-error "$BASE_URL/timeseries"
```

After intentionally pointing `ATHENA_DEFAULT_CATALOG_PATH` at a missing file and restarting, verify
that liveness stays 200 while analytics safely return 503:

```bash
curl --fail --show-error "$BASE_URL/health"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' "$BASE_URL/summary")" = 503
```

Example:

```bash
curl http://127.0.0.1:8000/status
curl http://127.0.0.1:8000/summary
curl http://127.0.0.1:8000/observatory
```

If the configured catalog/report is unavailable, analytical endpoints return HTTP 503 with a stable,
safe JSON error. OpenAPI documentation is available at `/docs`.

## Quality checks

```bash
ruff check .
git diff --check
python -m compileall -q app
pytest -q
```

Tests inject deterministic reports and never access live USGS services or production catalogs.

## Nonpredictive disclaimer

Results describe historical seismic observations and are **nonpredictive**. This service does not
predict earthquakes and does not estimate future earthquake probability. It does not generate
alerts and does not replace official earthquake, tsunami, emergency-management, or public-safety
information. Consult the responsible government authorities for current official information.
