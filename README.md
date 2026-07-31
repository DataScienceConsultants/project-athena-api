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

`data/catalog.csv` is a normalized Puerto Rico deployment catalog bundled into the image, so a new
instance can serve `/summary` without a network request or a writable filesystem. The API passes
that catalog to Athena's public Observatory builder and never implements analytics itself. Replace
this snapshot during a planned data refresh using Project Athena's public catalog downloader/export
pipeline, validate it, and deploy a new immutable image; the web process deliberately does not make
live USGS calls. `ATHENA_DEFAULT_CATALOG_PATH` can select a mounted, independently refreshed catalog.
The container also installs `config/regions.json` alongside Athena as a compatibility measure for
Athena 0.4.1, whose wheel does not include that package data.

## Configuration

All settings have local defaults and may be overridden independently:

| Variable | Default |
| --- | --- |
| `ATHENA_API_NAME` | `Project Athena API` |
| `ATHENA_API_VERSION` | `0.1.0` |
| `ATHENA_VERSION` | pinned commit shown above |
| `ATHENA_DEFAULT_REGION_KEY` | `puerto_rico` |
| `ATHENA_DEFAULT_CATALOG_PATH` | `data/catalog.csv` |
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

Deployment smoke tests (each should return HTTP 200):

```bash
BASE_URL=http://127.0.0.1:8000
curl --fail --show-error "$BASE_URL/health"
curl --fail --show-error "$BASE_URL/version"
curl --fail --show-error "$BASE_URL/summary"
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
