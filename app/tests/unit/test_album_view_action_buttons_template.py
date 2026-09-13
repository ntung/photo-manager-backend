"""
Unit tests for _album_view_action_buttons.html — the sticky action bar on
/albums/view/<path> (Reset Order, Slideshow, Shuffle, the description-format
toggle, the view-changer icon, Claim from source, Sort, Remove).

These render the template directly with hand-built context (see
conftest.make_photo / app_context) rather than going through a route, so
they run without a live MongoDB and can't catch backend/query bugs — only
template structure. They pin down two things fixed in this session:

  - The description-format toggle and the view-changer icon sit right after
    Shuffle (ahead of the optional, usually-hidden "Claim from source"
    button), so they land in the same flex row as the always-visible
    buttons instead of wrapping onto their own line underneath.
  - The description-format checkbox has an informative title describing
    what it actually toggles (original line breaks vs. reformatted text),
    not the vague "Toggle to view formatted descriptions" it used to have.
"""
from flask import render_template


def _render(**overrides):
    ctx = {"album_object_id": "abc123", "album_path": "flowers", "album_title": "Flowers"}
    ctx.update(overrides)
    return render_template("_album_view_action_buttons.html", **ctx)


def test_renders_without_error(app_context):
    html = _render()
    assert "Reset Order" in html
    assert "Sort" in html
    assert "Remove" in html


def test_shuffle_button_carries_album_identifiers(app_context):
    html = _render(album_object_id="abc123", album_path="flowers")
    # data-* attributes read by the shuffle click handler in album-view.html
    assert 'id="btn-shuffle-photo"' in html
    assert 'data-album-object-id="abc123"' in html
    assert 'data-album-path="flowers"' in html


def test_description_toggle_and_view_changer_come_before_claim_button(app_context):
    """
    Regression test: these two controls used to sit AFTER "Claim from
    source" in the DOM. Claim from source is a wide button that's only
    shown (via JS) when the album has unclaimed photos, and its presence
    was what pushed the toggle + icon off the end of the flex row onto a
    second line, out of alignment with Reset Order/Slideshow/Shuffle.
    Keeping them ahead of it, next to the always-visible buttons, is what
    keeps them on the same row when Claim from source is showing.
    """
    html = _render()
    shuffle_pos = html.index('id="btn-shuffle-photo"')
    toggle_pos = html.index('id="btn-view-original-description"')
    changer_pos = html.index('id="btn-view-changer"')
    claim_pos = html.index('id="btn-claim-source"')

    assert shuffle_pos < toggle_pos < claim_pos
    assert shuffle_pos < changer_pos < claim_pos


def test_action_bar_row_uses_flex_alignment(app_context):
    """
    Reset Order/Slideshow/Shuffle/toggle/view-changer/Sort/Claim share one
    container; it must be a flex row with vertically-centered items for
    those controls (a <label>/<span> of a different height than the
    buttons) to align on the same line rather than sitting on divergent
    baselines.
    """
    html = _render()
    # The container opening tag carries the alignment classes. It's col-8
    # (PM-46: widened from col-6 to also fit Sort, moved in here from its
    # own column) — the freed middle column is reserved (see
    # test_pm46_reserves_a_middle_column_for_a_future_search_box) and
    # Remove keeps its own col-1 so it lines up above the per-photo toggle
    # column.
    container_start = html.index('<div class="col-8')
    container_tag_end = html.index(">", container_start)
    container_tag = html[container_start:container_tag_end]
    assert "d-flex" in container_tag
    assert "align-items-center" in container_tag


def test_pm46_sort_group_sits_next_to_the_view_changer(app_context):
    """PM-46: Sort (icon + button + dropdown) moved out of its own column
    to sit right after the view-changer, in the same group as the other
    core controls — ahead of the optional, usually-hidden Claim button,
    same reasoning as test_description_toggle_and_view_changer_come_before_claim_button."""
    html = _render()
    changer_pos = html.index('id="btn-view-changer"')
    sort_icon_pos = html.index('id="sort-direction-icon"')
    sort_btn_pos = html.index('id="btn-sort"')
    claim_pos = html.index('id="btn-claim-source"')
    assert changer_pos < sort_icon_pos < sort_btn_pos < claim_pos


def test_pm46_search_input_sits_between_the_group_and_remove(app_context):
    """PM-46: the column freed by widening the button group (col-6->col-8)
    holds the search box, positioned between the group and Remove's own
    col-1 — not absorbed into either neighbour."""
    html = _render()
    group_start = html.index('<div class="col-8')
    remove_col_start = html.rindex('<div class="col', 0, html.index('id="btn-remove-photo"'))
    between = html[group_start:remove_col_start]
    assert 'class="col-3' in between
    assert 'id="album-search-input"' in between[between.index('class="col-3'):]


def test_pm46_search_input_has_type_search_and_a_label(app_context):
    """type=search gets the browser's native clear button; aria-label
    stands in for a <label> since there's no visible one in this compact
    action bar."""
    html = _render()
    input_start = html.index('id="album-search-input"')
    tag_start = html.rindex("<input", 0, input_start)
    tag_end = html.index(">", tag_start)
    input_tag = html[tag_start:tag_end]
    assert 'type="search"' in input_tag
    assert "aria-label=" in input_tag


def test_sort_icon_sits_close_to_the_sort_button(app_context):
    """
    Regression test: the sort-direction icon and the Sort button used to
    live in separate Bootstrap grid columns (col-2 / col-10) inside their
    own nested .row, which left a large gap between them. They should now
    share one flex container instead.
    """
    html = _render()
    icon_pos = html.index('id="sort-direction-icon"')
    sort_btn_pos = html.index('id="btn-sort"')
    assert icon_pos < sort_btn_pos

    # No Bootstrap grid split (col-2/col-10) between them any more.
    between = html[icon_pos:sort_btn_pos]
    assert "col-2" not in between
    assert "col-10" not in between


def test_description_toggle_has_an_informative_title(app_context):
    """
    The title must live on the <label> (the visible, hoverable 60x34
    switch) — .switch input is styled width:0;height:0;opacity:0 (only
    the sibling .slider span is actually rendered), so a title on the
    input alone can never show a tooltip: the cursor can never land on a
    0x0 element.
    """
    html = _render()
    label_start = html.index('<label class="switch')
    tag_end = html.index(">", label_start)
    label_tag = html[label_start:tag_end]
    assert 'title="' in label_tag
    # It must actually describe the behaviour (original line breaks vs.
    # reformatted text), not just gesture at "formatted descriptions".
    assert "original" in label_tag.lower()
    assert "line break" in label_tag.lower() or "reformat" in label_tag.lower()

    # Regression guard: the title must not sit on the invisible input,
    # where it would never actually trigger a tooltip.
    input_start = html.index('id="btn-view-original-description"')
    input_tag_end = html.index(">", input_start)
    assert 'title="' not in html[input_start:input_tag_end]


def test_view_changer_icon_starts_with_a_title_naming_the_next_view(app_context):
    """
    The icon always shows the CURRENTLY active view (list/gallery/columns);
    the page always loads with list active (see _album_view_list.html being
    the default include in album-view.html), so its initial title should
    name the NEXT view a click switches to — gallery — matching what the
    click handler in album-view.html sets for each of the other two states.
    """
    html = _render()
    icon_start = html.index('id="btn-view-changer"')
    tag_end = html.index(">", icon_start)
    icon_tag = html[icon_start:tag_end]
    assert 'title="Switch to gallery view"' in icon_tag


def test_remove_button_column_matches_the_photo_row_toggle_column(app_context):
    """
    Regression test: Remove used to sit in a col-2 while each photo row's
    own remove-checkbox toggle sits in a col-1 — different widths starting
    at different offsets, so Remove never lined up above the column of
    toggles it acts on. It must now be col-1 too (see
    _album_view_photo_rows.html's matching col-1 toggle column), with the
    button centered inside it to match how the toggle switch centers in
    its own column.
    """
    html = _render()
    remove_start = html.index('id="btn-remove-photo"')
    container_start = html.rindex('<div class="col', 0, remove_start)
    container_tag_end = html.index(">", container_start)
    container_tag = html[container_start:container_tag_end]
    assert "col-1" in container_tag
    assert "col-10" not in container_tag  # guard against a "col-1" substring false-positive
    assert "col-2" not in container_tag
    assert "justify-content-center" in container_tag


def test_claim_from_source_button_starts_hidden(app_context):
    """Claim from source is shown by JS only when the album has unclaimed
    photos (see the $.getJSON('/api/v1/album/.../unclaimed-by-source')
    call in album-view.html) — it must render hidden by default."""
    html = _render()
    claim_start = html.index('id="btn-claim-source"')
    tag_end = html.index(">", claim_start)
    claim_tag = html[html.rindex("<button", 0, claim_start):tag_end]
    assert "display:none" in claim_tag or "display: none" in claim_tag
