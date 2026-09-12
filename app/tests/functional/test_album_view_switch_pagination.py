"""
Functional tests for POST /albums/view/<path> (the view-changer button) and
its interaction with the infinite-scroll API (/api/v1/album/<path>/photos).

These pin down the fix for: switching view style used to load every photo in
the album via an N+1 find_one loop and render them all in one unpaginated
response — fine for a handful of photos, but an album with thousands of them
could crash the app. The view switch is now paginated exactly like the
default album load, and infinite scroll keeps working (in the newly-active
view style) to fetch the rest.
"""
from datetime import datetime, timedelta

PAGE_SIZE = 20

VIEW_LIST = "_album_view_list.html"
VIEW_GALLERY = "_album_view_gallery.html"
VIEW_COLUMNS = "_album_view_columns.html"

# A markup fragment unique to each view's item partial, used to tell which
# template a response actually rendered.
VIEW_MARKERS = {
    VIEW_LIST: 'class="photo-row-title"',
    VIEW_GALLERY: "shadow-1-strong",
    VIEW_COLUMNS: 'class="photo-item"',
}


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


def _seed_album(db, n_photos, path="flowers"):
    """Inserts n_photos photos and puts every one of them in a single album."""
    photo_ids = [_insert_photo(db, i) for i in range(n_photos)]
    db.albums.insert_one({
        "path": path,
        "title": "Flowers",
        "description": "An album",
        "photos": photo_ids,
        "date_created": datetime.now(),
        "date_modified": datetime.now(),
    })
    return photo_ids


def _ids_present(html, photo_ids):
    return {pid for pid in photo_ids if str(pid) in html}


def test_view_switch_renders_only_one_page_and_reports_has_more(client):
    from app.app import db

    photo_ids = _seed_album(db, n_photos=25)

    resp = client.post(
        "/albums/view/flowers", json={"view": VIEW_LIST}
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # The count header is the TOTAL album count, not just this page's size —
    # the client uses it to keep the page's <h1> in sync.
    assert resp.headers["X-Nb-Photos"] == "25"
    assert resp.headers["X-Has-More"] == "true"

    rendered = _ids_present(html, photo_ids)
    assert len(rendered) == PAGE_SIZE


def test_view_switch_on_small_album_loads_everything_in_one_page(client):
    from app.app import db

    photo_ids = _seed_album(db, n_photos=5)

    resp = client.post("/albums/view/flowers", json={"view": VIEW_GALLERY})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert resp.headers["X-Nb-Photos"] == "5"
    assert resp.headers["X-Has-More"] == "false"
    assert _ids_present(html, photo_ids) == set(photo_ids)


def test_each_view_style_renders_its_own_markup(client):
    from app.app import db

    _seed_album(db, n_photos=3)

    for view, marker in VIEW_MARKERS.items():
        resp = client.post("/albums/view/flowers", json={"view": view})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert marker in html, f"{view} response missing its marker markup"
        # And not another view's markup.
        for other_view, other_marker in VIEW_MARKERS.items():
            if other_view != view:
                assert other_marker not in html


def test_invalid_view_value_is_rejected(client):
    from app.app import db

    _seed_album(db, n_photos=3)

    resp = client.post("/albums/view/flowers", json={"view": "../etc/passwd"})
    assert resp.status_code == 400

    resp = client.post("/albums/view/flowers", json={})
    assert resp.status_code == 400


def test_infinite_scroll_after_switch_continues_in_the_new_view(client):
    """
    Regression test for the crash: switching to gallery view used to load
    every photo at once. Now the switch loads page 1, and scrolling further
    (the /api/v1 endpoint, with view=<style>) must return the remaining
    photos rendered as gallery markup, not list-row markup.
    """
    from app.app import db

    photo_ids = _seed_album(db, n_photos=25)

    switch_resp = client.post("/albums/view/flowers", json={"view": VIEW_GALLERY})
    assert switch_resp.headers["X-Has-More"] == "true"
    page1_ids = _ids_present(switch_resp.get_data(as_text=True), photo_ids)
    assert len(page1_ids) == PAGE_SIZE

    scroll_resp = client.get(
        "/api/v1/album/flowers/photos",
        query_string={"page": 2, "view": VIEW_GALLERY},
    )
    assert scroll_resp.status_code == 200
    body = scroll_resp.get_json()
    assert body["has_more"] is False
    assert body["count"] == len(photo_ids) - PAGE_SIZE

    # The appended fragment is gallery markup, not list rows.
    assert VIEW_MARKERS[VIEW_GALLERY] in body["content"]
    assert VIEW_MARKERS[VIEW_LIST] not in body["content"]

    page2_ids = _ids_present(body["content"], photo_ids)
    assert page1_ids.isdisjoint(page2_ids)
    assert page1_ids | page2_ids == set(photo_ids)


def test_infinite_scroll_defaults_to_list_markup_when_view_param_is_absent(client):
    """The infinite-scroll endpoint pre-dates the `view` param; omitting it
    (e.g. an old cached page) must keep behaving exactly as before — list-row
    markup."""
    from app.app import db

    _seed_album(db, n_photos=25)

    resp = client.get("/api/v1/album/flowers/photos", query_string={"page": 2})
    assert resp.status_code == 200
    body = resp.get_json()
    assert VIEW_MARKERS[VIEW_LIST] in body["content"]
