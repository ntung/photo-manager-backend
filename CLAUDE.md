# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run (development):**
```bash
./start.sh                          # gunicorn with auto-reload
flask run                           # Flask dev server
```

**Lint:**
```bash
flake8 app/ migration_framework/ migrations/
```
Config in `.flake8`: max line length 100, max complexity 12.

**Tests:**
```bash
pytest                              # all tests
pytest app/tests/unit/test_foo.py::test_bar   # single test
```
Test directories exist under `app/tests/{unit,integration,functional}/` but are largely unpopulated.

**Migrations:**
```bash
flask migrate                       # run pending migrations
```

## Architecture

Flask + PyMongo photo management backend. No ORM — direct PyMongo queries throughout.

**Core:** `app/app.py` (1400+ lines) contains Flask app init, all routes, and business logic. CORS and SocketIO are configured here. The file is intentionally monolithic; route extraction into `app/views/` has not happened yet.

**Photo storage:** Photos are stored on the file system in sequentially-named submission folders (`aaaa`, `aaab`, …) under `UPLOAD_FOLDER`. A folder is capped at 400 files; `InitPM` in `app/utils/PhotoManager.py` tracks the active folder and auto-creates the next one when full.

**MongoDB collections:**
- `photos` — title, description, courtesy, hash_md5, folder, filename, dates
- `albums` — path (slug), title, ordered `photos` array of ObjectIds, dates
- `todos` — scratch collection used during development
- `migration_versions` — tracks which migrations have run

**Custom migration framework** (`migration_framework/runner.py`): migrations in `migrations/` are Python files named `NNNN_description.py`. Each must expose `upgrade(db, session)`. The runner records applied versions in `migration_versions` and supports sessions for transactional rollback.

**API surface:**
- `GET/POST /photo/*` — upload, delete, update, show individual photos
- `GET/POST /albums`, `/albums/view/<path>` — album CRUD and view
- `GET /api/v1/photos` — paginated photo list (JSON)
- `GET /api/v1/album/<path>/photos` — paginated album photos (JSON)
- `GET /photo/<path:path>` — serve photo file from `UPLOAD_FOLDER`

**ASGI support:** `asgi_app.py` wraps the WSGI app via `asgiref.WsgiToAsgi` for uvicorn deployments.

## Environment

Key variables (see `.env`, `.env.local`, `.env.production`):

| Variable | Default |
|---|---|
| `MONGODB_URI` | `mongodb://localhost:27017` |
| `DB_NAME` | `photodb` |
| `UPLOAD_FOLDER` | `/tmp/photo-manager/upload` |
| `GUNICORN_BIND` | `0.0.0.0:5500` |

`.flaskenv` sets `FLASK_APP=app` and `FLASK_ENV=development` for the Flask CLI.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs `flake8` on every push and PR. Lint must pass before merging.
