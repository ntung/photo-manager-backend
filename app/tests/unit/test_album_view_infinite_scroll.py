"""
Unit tests pinning down the fillViewportIfNeeded() fix in album-view.html.

Infinite scroll (loadMoreAlbumPhotos) only fires from the browser's
`scroll` event. Columns view packs thumbnails far more densely per screen
than list/gallery, so a single page of photos often doesn't overflow the
viewport at all on any reasonably tall window -- no scrollbar ever
appears, `scroll` never fires, and pagination silently stalls even though
more photos exist. Confirmed live against the real /albums/view/flowers
album: at viewport heights >=1200px, columns view had zero scrollable
area with just the first page loaded, and a screenshot from the reporting
user showed exactly this -- stuck at 40 of 241 photos with visible empty
space below the grid.

fillViewportIfNeeded() proactively loads another page whenever the
current content doesn't yet overflow the viewport, called after the
initial load and after every append/switch/sort/shuffle. These tests
can't drive an actual browser layout (no MongoDB-free way to do that
here), so they assert the fix's structural shape in the rendered
template: the function exists and every place that changes what's
rendered calls it.
"""
from flask import render_template

from app.tests.unit.conftest import make_photo


def _render_album_view():
    photos = [make_photo(i) for i in range(3)]
    return render_template(
        "album-view.html",
        status="FOUND", album={}, album_object_id="abc123",
        photos=photos, album_title="Flowers", albums=[], album_path="flowers",
        nb_photos=3, is_empty_album=False, other_albums=None, has_more=True,
        api_svr=None, dict_album_values={}, cover_photo_url=None,
        cover_photo_id="", cover_needs_regen=False,
    )


def test_fill_viewport_helper_is_defined(app_context):
    html = _render_album_view()
    assert "function fillViewportIfNeeded()" in html


def test_fill_viewport_is_called_on_initial_load(app_context):
    """Must run on page load — either directly (no saved view style to
    restore) or via callServerToChangeView when a saved style IS restored,
    which itself calls it once the switch completes — otherwise an album
    whose very first page doesn't overflow the viewport (most likely in
    columns view) never gets a second page until the user manages to
    generate a scroll event, which they can't if there's nothing to
    scroll. See test_restore_view_style.py for the restore path itself."""
    html = _render_album_view()
    assert "fillViewportIfNeeded();" in html
    assert "restoreViewStyle" in html


def test_fill_viewport_is_called_after_every_content_replacing_action(app_context):
    """Called after: the initial page load, appending a scrolled-in page,
    switching view, and (via the shared applyFullPageReplace helper — see
    test_apply_full_page_replace_is_shared_by_sort_shuffle_and_search)
    sorting, shuffling, and searching — any of the places that can leave
    the grid short of a scrollbar."""
    html = _render_album_view()

    def chunk_after(marker, size):
        # A fixed-size window rather than searching for the next landmark:
        # these handlers nest an anonymous `function (response) {...}` for
        # the AJAX callback, which would falsely match a "next function"
        # landmark before ever reaching the body we actually want to check.
        start = html.index(marker)
        return html[start:start + size]

    # Inside loadMoreAlbumPhotos' success handler (infinite-scroll append).
    assert "fillViewportIfNeeded();" in chunk_after("function loadMoreAlbumPhotos()", 1300)

    # Inside callServerToChangeView's success handler (view switch).
    change_view_marker = "function callServerToChangeView(viewStyle)"
    assert "fillViewportIfNeeded();" in chunk_after(change_view_marker, 2500)

    # Inside the shared helper sort/shuffle/search all delegate to.
    assert "fillViewportIfNeeded();" in chunk_after("function applyFullPageReplace(response)", 500)


def test_apply_full_page_replace_is_shared_by_sort_shuffle_and_search(app_context):
    """Regression guard: sort, shuffle, and search each fully replace
    #photo-gallery with a fresh page 1 and must go through the one shared
    applyFullPageReplace helper (fillViewportIfNeeded + the total-count
    update + the sortable-disable) rather than each re-implementing it —
    duplicating that logic three ways is exactly how the viewport-fill
    call could silently go missing from one of them again."""
    html = _render_album_view()

    def chunk_after(marker, size):
        start = html.index(marker)
        return html[start:start + size]

    marker = "applyFullPageReplace(response);"
    assert marker in chunk_after('$("#btn-shuffle-photo").on("click"', 900)
    assert marker in chunk_after("function callServerToSortPhotos()", 700)
    assert marker in chunk_after("function callServerToSearchPhotos()", 700)
