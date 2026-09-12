"""
Shared fixtures for template unit tests.

These tests render individual Jinja templates directly (`render_template`)
with hand-built context, rather than going through a route — so, unlike the
functional tests, they don't need a live MongoDB: `app.py`'s MongoClient
connects lazily (see app/app.py), and nothing at import time issues a query,
so app.app can be imported and its templates rendered with only a reachable
filesystem for UPLOAD_FOLDER.
"""
import os
import tempfile

import pytest


@pytest.fixture(scope="session")
def flask_app():
    # Must be set before `import app.app`: it reads these at module import
    # time (and raises RuntimeError if unset), but the client it builds
    # never connects for template-only rendering, so any host/port is fine.
    os.environ["DB_HOST"] = os.environ.get("DB_HOST", "localhost")
    os.environ["DB_PORT"] = os.environ.get("DB_PORT", "27017")
    os.environ["DB_NAME"] = os.environ.get("DB_NAME", "photodb_templatetest")
    os.environ["UPLOAD_FOLDER"] = tempfile.mkdtemp(prefix="photo-manager-unittest-")

    from app.app import app as _flask_app

    _flask_app.config.update(TESTING=True)
    yield _flask_app


@pytest.fixture
def app_context(flask_app):
    # A request context (not just an app context) so templates that call
    # url_for(...) — e.g. _album_view_photo_rows.html's "Show" link — can
    # build URLs without needing SERVER_NAME configured.
    with flask_app.test_request_context():
        yield flask_app


def make_photo(index, **overrides):
    """A plain dict shaped like the photo documents templates render —
    enough fields for every _album_view_*.html partial, no MongoDB needed."""
    from datetime import datetime, timedelta

    photo = {
        "_id": f"photo-id-{index}",
        "title": f"Photo {index}",
        "description": f"Description {index}",
        "courtesy": "Some Person",
        "folder": "aaaa",
        "filename": f"photo-{index}.jpg",
        "date_uploaded": datetime(2026, 1, 1) + timedelta(minutes=index),
        "date_modified": datetime(2026, 1, 1) + timedelta(minutes=index),
        "other_albums": [],
    }
    photo.update(overrides)
    return photo
