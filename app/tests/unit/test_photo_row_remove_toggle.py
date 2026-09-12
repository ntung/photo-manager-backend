"""
Unit tests for the per-photo remove-toggle switch in
_album_view_photo_rows.html (the list view's per-row column also holding
the "Set cover" / "Cover" label).

Two things fixed in this session:

  - Bootstrap's default .form-check padding-left (24px, meant to make room
    for a real checkbox to the left of its label) insets this *custom*
    slider switch 24px to the right of its own wrapper box. The wrapper
    itself was correctly centered in its column (matching Set cover below
    it and the Remove button above it in the action bar), but the visible
    switch inside it was not — a real, measurable 12px offset. Fixed with
    ps-0 to zero that padding so the switch's own box hugs the column,
    same as Set cover's plain, unpadded <a>.
  - The toggle had no title at all. Since .switch input is styled
    width:0;height:0;opacity:0 (same as the description-format toggle
    fixed earlier), a title must live on the <label> — the actual visible,
    hoverable element — not on the input, which can never trigger a
    tooltip.
"""
from flask import render_template

from app.tests.unit.conftest import make_photo


def _render_rows():
    return render_template(
        "_album_view_photo_rows.html",
        photos=[make_photo(0)], album_path="flowers", status="FOUND",
        cover_photo_id="",
    )


def test_form_check_wrapper_zeroes_the_bootstrap_inset(app_context):
    html = _render_rows()
    wrapper_start = html.index('<div class="form-check')
    wrapper_tag_end = html.index(">", wrapper_start)
    assert "ps-0" in html[wrapper_start:wrapper_tag_end]


def test_toggle_title_lives_on_the_label_not_the_invisible_input(app_context):
    html = _render_rows()
    label_start = html.index('<label class="form-check-label switch"')
    label_tag_end = html.index(">", label_start)
    label_tag = html[label_start:label_tag_end]
    assert 'title="' in label_tag
    assert "remove" in label_tag.lower()
    assert "album" in label_tag.lower()  # names the album, not "delete"/permanent removal

    input_start = html.index('id="chk-remove-')
    input_tag_end = html.index(">", input_start)
    assert 'title="' not in html[input_start:input_tag_end]
