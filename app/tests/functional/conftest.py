"""
Shared fixtures for functional tests.

The app has no dependency-injection seam for its MongoDB connection — `db`
is a module-level global bound at import time (see app/app.py) — so these
fixtures point it at a disposable, uniquely-named database instead of the
real `photodb` before importing the app module, and drop it afterwards.
Requires a reachable MongoDB (same one `./start.sh` / `flask run` use).
"""
import os
import tempfile
import uuid

import pytest

TEST_DB_NAME = f"photodb_functest_{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session")
def flask_app():
    # Must be set before `import app.app`: it reads these at module import
    # time, and load_dotenv() only fills in vars that aren't already set, so
    # this safely overrides whatever .env points at.
    os.environ["DB_HOST"] = os.environ.get("DB_HOST", "localhost")
    os.environ["DB_PORT"] = os.environ.get("DB_PORT", "27017")
    os.environ["DB_NAME"] = TEST_DB_NAME
    os.environ["UPLOAD_FOLDER"] = tempfile.mkdtemp(prefix="photo-manager-functest-")

    from app.app import app as _flask_app, client as _mongo_client

    _flask_app.config.update(TESTING=True)
    yield _flask_app

    _mongo_client.drop_database(TEST_DB_NAME)


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture(autouse=True)
def _clean_collections(flask_app):
    """Empties the collections used by each test, before and after it runs."""
    from app.app import db

    db.photos.delete_many({})
    db.albums.delete_many({})
    yield
    db.photos.delete_many({})
    db.albums.delete_many({})
