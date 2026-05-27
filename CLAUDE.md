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
Config in `.flake8`: max line length 100, max complexity 12, F401 ignored globally.

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

**Core:** `app/app.py` (1400+ lines) contains Flask app init, all routes, and business logic. CORS and SocketIO are configured here. The file is intentionally monolithic; `app/views/__init__.py` and `app/services/__init__.py` exist as stubs but route/service extraction has not happened.

**Photo storage:** Photos are stored on the file system in sequentially-named submission folders (`aaaa`, `aaab`, …) under `UPLOAD_FOLDER`. A folder is capped at 400 files; `InitPM` in `app/utils/PhotoManager.py` tracks the active folder and auto-creates the next one when full. The upload route accepts an optional `Submission-Folder` request header to override folder auto-detection; without it, `infer_submission_folder()` is called. Upload requires a `metadata` JSON form field (title, description, courtesy, photo-url). MD5 dedup is enforced at upload time — if the hash already exists the new file is deleted and a 200 with `"exists!"` message is returned.

**MongoDB collections:**
- `photos` — title, description, courtesy, hash_md5, folder, filename, dates
- `albums` — path (slug), title, ordered `photos` array of ObjectIds, dates
- `todos` — scratch collection used during development
- `migration_versions` — tracks which migrations have run

**Custom migration framework** (`migration_framework/runner.py`): migrations in `migrations/` are Python files named `NNNN_description.py`. Each must expose `upgrade(db, logger, session)`. The runner records applied versions in `migration_versions` and supports sessions for transactional rollback (transactions only run when connected to a replica set; standalone MongoDB skips them).

**Templates:** Underscore-prefixed templates (`_photo-list.html`, `_album_view_list.html`, `_album_view_photo_rows.html`, etc.) are HTML partials returned by API endpoints for HTMX-style infinite scroll. Full-page templates (`photo-list.html`, `album-view.html`, etc.) use these partials via Jinja includes. Pagination page size is hardcoded at 20 in `_get_pagination_params()`.

**API surface:**
- `GET/POST /photo/upload` — upload a photo (form + `metadata` JSON field)
- `GET /photo/show/<unique_key>` — show photo by ObjectId string or MD5 hash
- `POST /photo/delete`, `GET/POST /photo/delete/<id>` — delete photo and its album references
- `PATCH /api/v1/photo/update` — update photo title
- `POST /photo/update` — update photo title, description, courtesy
- `GET /photo/list`, `GET /photo/view` — paginated photo list (HTML)
- `GET /photo/<path:path>` — serve photo file from `UPLOAD_FOLDER` (cached 24 h)
- `GET/POST /photo/albums` — album CRUD list view (HTML)
- `GET/POST /albums`, `/albums/<path>` — album data (JSON)
- `GET /albums/view/<path>` — album detail page (HTML, 5-min cache)
- `POST /albums/add-photo`, `/album/add`, `/photo/save-photo-to-albums` — add photos to albums
- `POST /albums/remove-photos` — remove photos from an album
- `POST /albums/reorder-photos/` — reorder photos within an album
- `POST /albums/update/`, `/albums/delete` — update/delete an album
- `GET /api/v1/photos` — paginated photo list (JSON + pre-rendered HTML for infinite scroll)
- `GET /api/v1/photos/gallery` — paginated photo gallery (JSON + pre-rendered HTML)
- `GET /api/v1/album/<path>/photos` — paginated album photos (JSON + pre-rendered HTML); supports `sort=<field>;<dir>` and `shuffle=<seed>` query params
- `GET /api/v1/album/<path>/slideshow` — lightweight photo URL + title list for slideshow

**ASGI support:** `asgi_app.py` wraps the WSGI app via `asgiref.WsgiToAsgi` for uvicorn deployments.

## Environment

Key variables (see `.env`, `.env.local`, `.env.production`):

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DB_HOST` | yes | — | App raises `RuntimeError` at startup if unset |
| `DB_PORT` | yes | — | App raises `RuntimeError` at startup if unset |
| `DB_NAME` | no | `photodb` | |
| `MONGODB_URI` | migrations only | — | Used only by `flask migrate` (MigrationRunner), not the app |
| `UPLOAD_FOLDER` | no | `/tmp/photo-manager/upload` | |
| `GUNICORN_BIND` | no | `0.0.0.0:5500` | |
| `API_SERVER` | no | — | Passed to templates as `api_svr`; used for cross-origin API calls |

`.flaskenv` sets `FLASK_APP=app` and `FLASK_ENV=development` for the Flask CLI.

**Gunicorn SSL:** `gunicorn_config.py` expects certs at `certs/localhost+2-key.pem` and `certs/localhost+2-cert.pem` (not the `cert.pem`/`key.pem` files at the repo root).

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs `flake8` on every push and PR. Lint must pass before merging.
