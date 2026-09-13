"""
Functional tests for the search box added to the album view (PM-46):
GET /api/v1/album/<path>/photos?q=<text> filters photos by title or
description, case-insensitively, before pagination — so `total` and
`has_more` reflect only the matches, the same as sort/shuffle already do
for the whole album.
"""
from datetime import datetime, timedelta

PAGE_SIZE = 20


def _insert_photo(db, index, title=None, description=""):
    uploaded_at = datetime(2026, 1, 1) + timedelta(minutes=index)
    return db.photos.insert_one({
        "title": title if title is not None else f"Photo {index}",
        "description": description,
        "courtesy": "",
        "folder": "aaaa",
        "filename": f"photo-{index}.jpg",
        "hash_md5": f"hash-{index:03d}",
        "date_uploaded": uploaded_at,
        "date_modified": uploaded_at,
    }).inserted_id


def _seed_album(db, photos, path="flowers"):
    """photos: list of (title, description) tuples. Returns their ids."""
    photo_ids = [
        _insert_photo(db, i, title=title, description=description)
        for i, (title, description) in enumerate(photos)
    ]
    db.albums.insert_one({
        "path": path,
        "title": "Flowers",
        "description": "An album",
        "photos": photo_ids,
        "date_created": datetime.now(),
        "date_modified": datetime.now(),
    })
    return photo_ids


def test_search_matches_title_case_insensitively(client):
    from app.app import db

    ids = _seed_album(db, [
        ("Red Rose", ""), ("Yellow Tulip", ""), ("Pink Rose", ""),
    ])

    resp = client.get("/api/v1/album/flowers/photos", query_string={"q": "rose"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    assert body["count"] == 2
    assert str(ids[0]) in body["content"]
    assert str(ids[2]) in body["content"]
    assert str(ids[1]) not in body["content"]


def test_search_matches_description_too(client):
    from app.app import db

    ids = _seed_album(db, [
        ("Untitled", "A field of sunflowers at dusk"),
        ("Untitled", "A red rose in the garden"),
    ])

    resp = client.get("/api/v1/album/flowers/photos", query_string={"q": "sunflower"})
    body = resp.get_json()
    assert body["total"] == 1
    assert str(ids[0]) in body["content"]
    assert str(ids[1]) not in body["content"]


def test_search_paginates_the_matched_set(client):
    from app.app import db

    # 25 photos titled "Rose N", plus 5 unrelated ones that must never
    # appear in the search results.
    rose_titles = [(f"Rose {i}", "") for i in range(25)]
    other_titles = [(f"Tulip {i}", "") for i in range(5)]
    ids = _seed_album(db, rose_titles + other_titles)
    rose_ids = set(str(i) for i in ids[:25])
    tulip_ids = set(str(i) for i in ids[25:])

    page1 = client.get(
        "/api/v1/album/flowers/photos", query_string={"q": "rose", "page": 1}
    ).get_json()
    assert page1["total"] == 25
    assert page1["has_more"] is True
    assert page1["count"] == PAGE_SIZE
    page1_ids = {i for i in rose_ids if i in page1["content"]}
    assert len(page1_ids) == PAGE_SIZE

    page2 = client.get(
        "/api/v1/album/flowers/photos", query_string={"q": "rose", "page": 2}
    ).get_json()
    assert page2["total"] == 25
    assert page2["has_more"] is False
    assert page2["count"] == 5
    page2_ids = {i for i in rose_ids if i in page2["content"]}

    assert page1_ids | page2_ids == rose_ids
    assert page1_ids.isdisjoint(page2_ids)
    for tid in tulip_ids:
        assert tid not in page1["content"]
        assert tid not in page2["content"]


def test_search_composes_with_sort(client):
    from app.app import db

    ids = _seed_album(db, [("Rose B", ""), ("Rose A", ""), ("Tulip", "")])

    resp = client.get(
        "/api/v1/album/flowers/photos", query_string={"q": "rose", "sort": "title;up"}
    )
    body = resp.get_json()
    assert body["total"] == 2
    # "Rose A" sorts before "Rose B" ascending; check relative order in
    # the rendered HTML rather than assuming exact markup.
    pos_a = body["content"].find(str(ids[1]))
    pos_b = body["content"].find(str(ids[0]))
    assert pos_a != -1 and pos_b != -1
    assert pos_a < pos_b


def test_empty_query_behaves_like_no_search(client):
    from app.app import db

    _seed_album(db, [("Rose", ""), ("Tulip", "")])

    resp = client.get("/api/v1/album/flowers/photos", query_string={"q": ""})
    body = resp.get_json()
    assert body["total"] == 2
    assert body["count"] == 2


def test_no_matches_returns_empty_page_not_an_error(client):
    from app.app import db

    _seed_album(db, [("Rose", ""), ("Tulip", "")])

    resp = client.get("/api/v1/album/flowers/photos", query_string={"q": "nonexistent-xyz"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 0
    assert body["count"] == 0
    assert body["has_more"] is False


def test_search_special_characters_are_treated_literally(client):
    """A search string containing regex metacharacters must be matched
    literally (re.escape), not interpreted as a pattern -- both so a
    photo titled with punctuation is still findable, and so a query can't
    be used to build an expensive/malicious regex."""
    from app.app import db

    ids = _seed_album(db, [("Photo (1)", ""), ("Photo 1", "")])

    resp = client.get("/api/v1/album/flowers/photos", query_string={"q": "(1)"})
    body = resp.get_json()
    assert body["total"] == 1
    assert str(ids[0]) in body["content"]
    assert str(ids[1]) not in body["content"]


def test_search_works_on_the_unclassified_pseudo_album(client):
    from app.app import db

    matching = _insert_photo(db, 0, title="Sunset Rose")
    other = _insert_photo(db, 1, title="Random Tulip")

    resp = client.get("/api/v1/album/unclassified/photos", query_string={"q": "rose"})
    body = resp.get_json()
    assert body["total"] == 1
    assert str(matching) in body["content"]
    assert str(other) not in body["content"]
