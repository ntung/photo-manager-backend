"""
Functional tests for GET /albums/view/unclassified and its infinite-scroll
API endpoint (/api/v1/album/unclassified/photos).

These pin down two things about the rewrite in app.py:
  - Correctness: a photo that belongs to any album must never show up as
    "unclassified" (the old implementation round-tripped albums/photos
    through bson.json_util and then compared a str _id against a list of
    ObjectId, which never matched — every photo silently "leaked" through).
  - Pagination: the unclassified view now loads one page at a time and
    reports `has_more`, the same as a real album, instead of loading every
    unclassified photo into Python in one shot.
"""
from datetime import datetime, timedelta

PAGE_SIZE = 20


def _insert_photo(db, index):
    uploaded_at = datetime(2026, 1, 1) + timedelta(minutes=index)
    return db.photos.insert_one({
        "title": f"Photo {index}",
        "description": "",
        "courtesy": "",
        "folder": "aaaa",
        "filename": f"photo-{index}.jpg",
        "hash_md5": f"hash-{index:03d}",
        "date_uploaded": uploaded_at,
        "date_modified": uploaded_at,
    }).inserted_id


def _seed(db, n_albumed, n_unclassified):
    """
    Inserts n_albumed photos that belong to one album, plus n_unclassified
    photos that belong to no album. Returns (albumed_ids, unclassified_ids).
    """
    albumed_ids = [_insert_photo(db, i) for i in range(n_albumed)]
    unclassified_ids = [
        _insert_photo(db, n_albumed + i) for i in range(n_unclassified)
    ]
    if albumed_ids:
        db.albums.insert_one({
            "path": "holiday",
            "title": "Holiday",
            "description": "An album",
            "photos": albumed_ids,
            "date_created": datetime.now(),
            "date_modified": datetime.now(),
        })
    return albumed_ids, unclassified_ids


def test_first_page_excludes_albumed_photos_and_reports_has_more(client):
    from app.app import db

    albumed_ids, unclassified_ids = _seed(db, n_albumed=5, n_unclassified=25)

    resp = client.get("/albums/view/unclassified")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # The header count is the TOTAL unclassified count, not just this page.
    assert "View Album Unclassified (25)" in html

    # Exactly one page's worth of photos is rendered...
    rendered_ids = [pid for pid in unclassified_ids if str(pid) in html]
    assert len(rendered_ids) == PAGE_SIZE

    # ...and the client is told more is available to scroll to.
    assert "let albumHasMore = true;" in html

    # Photos that belong to the "holiday" album must never appear here. This
    # is the correctness bug the old greedy/JSON-roundtrip membership check
    # had: it never matched, so every photo "leaked" into unclassified.
    for aid in albumed_ids:
        assert str(aid) not in html


def test_second_page_via_infinite_scroll_api_returns_remainder(client):
    from app.app import db

    albumed_ids, unclassified_ids = _seed(db, n_albumed=5, n_unclassified=25)

    first_page_html = client.get("/albums/view/unclassified").get_data(as_text=True)
    page1_ids = {pid for pid in unclassified_ids if str(pid) in first_page_html}
    assert len(page1_ids) == PAGE_SIZE

    resp = client.get("/api/v1/album/unclassified/photos", query_string={"page": 2})
    assert resp.status_code == 200
    body = resp.get_json()

    remaining = len(unclassified_ids) - PAGE_SIZE
    assert body["count"] == remaining
    assert body["has_more"] is False

    page2_ids = {pid for pid in unclassified_ids if str(pid) in body["content"]}
    assert page2_ids == set(unclassified_ids) - page1_ids
    assert page1_ids.isdisjoint(page2_ids)

    for aid in albumed_ids:
        assert str(aid) not in body["content"]


def test_no_more_pages_once_every_unclassified_photo_is_shown(client):
    from app.app import db

    _, unclassified_ids = _seed(db, n_albumed=0, n_unclassified=PAGE_SIZE)

    resp = client.get("/albums/view/unclassified")
    html = resp.get_data(as_text=True)

    assert f"View Album Unclassified ({PAGE_SIZE})" in html
    assert "let albumHasMore = false;" in html
    for pid in unclassified_ids:
        assert str(pid) in html


def test_empty_when_every_photo_belongs_to_an_album(client):
    from app.app import db

    albumed_ids, _ = _seed(db, n_albumed=3, n_unclassified=0)
    assert albumed_ids  # sanity: photos exist, just none are unclassified

    resp = client.get("/albums/view/unclassified")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "No photo" in html
    assert "let albumHasMore = false;" in html
