"""
Unit tests for restoring the album view style (list/gallery/columns) across
a page refresh, in album-view.html.

Before this fix, the view style lived only in an in-memory JS variable
(currentView) and the view-changer icon's CSS class — nothing persisted
it, so every refresh silently reset back to list view regardless of what
the user had switched to. Fixed the same way the description-format
toggle already persists its own preference: localStorage, read back on
load and (if it names a non-default view) applied via
callServerToChangeView — which re-fetches page 1 in that view, so the
existing pagination/race-guard machinery handles the rest.

These tests can't exercise actual localStorage/click behaviour (no
browser here), so they assert the fix's structural shape: the same
storage key is used to write (on every switch) and read (on load), the
view-changer's next-view/icon table agrees with itself in both
directions, and the click handler no longer hardcodes the cycle via the
icon's current CSS class (a duplicate of the same list/gallery/columns
knowledge now centralised in VIEW_CYCLE).
"""
import re

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


def test_view_style_is_written_to_local_storage_on_every_switch(app_context):
    html = _render_album_view()
    assert "localStorage.setItem(VIEW_STYLE_STORAGE_KEY, viewStyle)" in html
    # Inside callServerToChangeView, the single function every switch (and
    # the restore-on-load path) goes through — not just the click handler,
    # so a restored view is itself re-persisted consistently too.
    fn_start = html.index("function callServerToChangeView(viewStyle)")
    call_pos = html.index("localStorage.setItem(VIEW_STYLE_STORAGE_KEY", fn_start)
    assert call_pos - fn_start < 800


def test_view_style_is_read_back_on_load_with_the_same_key(app_context):
    html = _render_album_view()
    assert "localStorage.getItem(VIEW_STYLE_STORAGE_KEY)" in html
    assert "function restoreViewStyle" in html


def test_restore_applies_saved_view_via_the_normal_switch_path(app_context):
    """The restore branch must reuse callServerToChangeView (which already
    handles pagination, the X-Has-More header, and the render-generation
    guard) rather than duplicating any of that fetch/render logic for a
    'restored' case."""
    html = _render_album_view()
    restore_start = html.index("function restoreViewStyle")
    restore_body = html[restore_start:restore_start + 700]
    assert "setViewChangerIcon(savedView)" in restore_body
    assert "callServerToChangeView(savedView)" in restore_body
    # Falls back to the ordinary viewport check when there's nothing to
    # restore (first-ever visit, or the saved value is list — already what
    # the server rendered), rather than always re-fetching.
    assert "fillViewportIfNeeded();" in restore_body


def test_view_cycle_table_is_internally_consistent(app_context):
    """Each view's `next` must point to a different view whose own `next`
    eventually cycles back — i.e. list -> gallery -> columns -> list, not
    a shorter loop or a dead end — matching the three actual view
    templates the view-changer can switch to."""
    html = _render_album_view()
    table_start = html.index("const VIEW_CYCLE = {")
    table_end = html.index("};", table_start)
    table_src = html[table_start:table_end]

    views = set(re.findall(r"'(_album_view_\w+\.html)':\s*\{", table_src))
    assert views == {
        "_album_view_list.html",
        "_album_view_gallery.html",
        "_album_view_columns.html",
    }

    next_pattern = r"'(_album_view_\w+\.html)':\s*\{[^}]*next:\s*'(_album_view_\w+\.html)'"
    nexts = dict(re.findall(next_pattern, table_src))
    assert set(nexts.values()) == views  # every `next` names a real view
    # Walking `next` three times from any view returns to that view.
    for view in views:
        v = view
        for _ in range(3):
            v = nexts[v]
        assert v == view


def test_click_handler_no_longer_branches_on_icon_css_class(app_context):
    """Regression guard: the view-changer cycle used to be hardcoded via
    three hasClass('fa-...') branches directly in the click handler,
    duplicating the same list/gallery/columns knowledge VIEW_CYCLE now
    holds once. The handler should just look up VIEW_CYCLE[currentView]."""
    html = _render_album_view()
    click_start = html.index('$("#btn-view-changer").on("click"')
    click_end = html.index("});", click_start)
    click_body = html[click_start:click_end]
    assert "hasClass(\"fa-th-list\")" not in click_body
    assert "VIEW_CYCLE[currentView]" in click_body
