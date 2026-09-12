"""
Unit tests for the three album view-style templates (list/gallery/columns)
and their item-only partials used for infinite-scroll appends. Renders each
directly with hand-built context — no MongoDB, no route — so these are cheap
smoke tests: they catch a broken {% include %}, a missing/renamed context
variable, or a template that silently starts rendering another view's
markup (the PM-45 bug: view-switch responses need to be visually and
structurally distinct per view).
"""
import pytest
from flask import render_template

from app.tests.unit.conftest import make_photo

FULL_VIEW_TEMPLATES = [
    "_album_view_list.html",
    "_album_view_gallery.html",
    "_album_view_columns.html",
]

ITEM_TEMPLATES = [
    "_album_view_photo_rows.html",
    "_album_view_gallery_items.html",
    "_album_view_columns_items.html",
]

# A markup fragment unique to each full-view template's own item markup,
# used to assert a view doesn't accidentally render another view's content.
DISTINCT_MARKER = {
    "_album_view_list.html": 'class="photo-row-title"',
    "_album_view_gallery.html": "shadow-1-strong",
    "_album_view_columns.html": 'class="photo-item"',
    "_album_view_photo_rows.html": 'class="photo-row-title"',
    "_album_view_gallery_items.html": "shadow-1-strong",
    "_album_view_columns_items.html": 'class="photo-item"',
}


def _photos():
    return [make_photo(i) for i in range(3)]


@pytest.mark.parametrize("template_name", FULL_VIEW_TEMPLATES)
def test_full_view_template_renders(app_context, template_name):
    html = render_template(
        template_name,
        status="FOUND",
        photos=_photos(),
        album_path="flowers",
        album_title="Flowers",
        album_object_id="abc123",
        nb_photos=3,
        has_more=False,
    )
    for photo in _photos():
        assert str(photo["_id"]) in html
    assert DISTINCT_MARKER[template_name] in html


@pytest.mark.parametrize("template_name", FULL_VIEW_TEMPLATES)
def test_full_view_template_does_not_render_another_views_markup(app_context, template_name):
    html = render_template(
        template_name,
        status="FOUND",
        photos=_photos(),
        album_path="flowers",
        album_title="Flowers",
        album_object_id="abc123",
        nb_photos=3,
        has_more=False,
    )
    this_marker = DISTINCT_MARKER[template_name]
    other_markers = {
        marker for t, marker in DISTINCT_MARKER.items()
        if t != template_name and marker != this_marker
    }
    for marker in other_markers:
        assert marker not in html


@pytest.mark.parametrize("template_name", ITEM_TEMPLATES)
def test_item_partial_renders_with_no_script_tags(app_context, template_name):
    """
    Item-only partials are appended repeatedly by infinite scroll
    ($('#photo-gallery').append(...)) — any inline <script> in them would
    re-execute on every page and risk "Identifier already declared" errors
    (the exact failure mode _photo-edit-modal-form.html was pulled out of
    .photo to avoid; see the comment in album-view.html). They must stay
    script-free.
    """
    html = render_template(template_name, photos=_photos(), album_path="flowers")
    for photo in _photos():
        assert str(photo["_id"]) in html
    assert "<script" not in html
    assert DISTINCT_MARKER[template_name] in html


def test_empty_photo_list_renders_without_error(app_context):
    for template_name in FULL_VIEW_TEMPLATES + ITEM_TEMPLATES:
        html = render_template(
            template_name,
            status="FOUND",
            photos=[],
            album_path="flowers",
            album_title="Flowers",
            album_object_id="abc123",
            nb_photos=0,
            has_more=False,
        )
        assert isinstance(html, str)
