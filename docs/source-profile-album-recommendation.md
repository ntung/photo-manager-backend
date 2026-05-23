# Source Profile & Album Recommendation System

## Overview

Photos saved from Facebook carry a `source_profile` field in the `photos` collection. This field
enables the album recommendation system — when a new photo is saved from a Facebook source, the
system suggests albums that already contain photos from the same source.

---

## How `source_profile` Is Extracted

The helper `extract_facebook_profile(url)` in `app/app.py` parses a Facebook URL and returns a
stable identifier using the following priority:

1. **`id` query param** — e.g. `profile.php?id=100015224503587` → `100015224503587`
2. **`set` query param** — e.g. `set=pb.100015224503587.-2207520000` → `parts[1]` → `100015224503587`
   - Formats seen: `a.<album_id>`, `pb.<profile_id>.<ts>`, `pcb.<profile_id>.<ts>`
   - The meaningful identifier is always the second segment
3. **URL path slug** — e.g. `facebook.com/username/photos` → `username` (if not a reserved word)

HTML-encoded URLs (e.g. `&amp;` instead of `&`) are unescaped before parsing.

Returns `None` if no identifier can be extracted (e.g. clean URLs like `?fbid=xxx` with no other params).

---

## Upload Paths

### Upload Form (`/photo/upload`)

- User pastes a Facebook URL into the **Courtesy** field.
- On `focusout`, the frontend calls `GET /api/v1/extension/recommend-albums` and auto-selects
  suggested albums in the Select2 dropdown.
- On upload, `do_upload_photo` extracts `source_profile` from the courtesy URL and stores it on
  the photo document if non-null.

### Browser Extension (`POST /api/v1/extension/save`)

**Request body:**

| Field | Required | Description |
|---|---|---|
| `raw_url` | yes (or `clean_url`) | Original URL with auth params, used for download |
| `clean_url` | yes (or `raw_url`) | Stripped URL (fallback download source) |
| `page_url` | no | Photo page URL, stored as courtesy |
| `profile_url` | no | Profile/page URL (`profile.php?id=NNNN`), preferred for profile detection |
| `page_title` | no | Page title, stored as photo title |
| `albums` | no | Array of `{ path, title }` objects — photo is added to each on save |

Two workflows are supported:

**Workflow A — Manual (with review):**

1. When the user opens the extension popup on a Facebook photo page, the extension calls
   `GET /api/v1/extension/recommend-albums` with the current `profile_url` or `page_url`.
2. The recommended albums are displayed in the popup and **pre-selected** so the user does not
   need to pick them manually. The user can deselect any album before saving.
3. The user clicks **Save**. The extension POSTs to `/api/v1/extension/save` with the confirmed
   albums in the `albums` array. The server adds the photo to each album atomically and returns
   `added_albums` confirming what was saved.

**Workflow B — Automatic (no human interaction):**

1. The extension POSTs to `POST /api/v1/extension/auto-save` with the same body as Workflow A
   (no `albums` field needed).
2. The server internally resolves recommended albums from the source profile and saves the photo
   into them in a single round trip — no popup, no user confirmation.
3. If `fallback_required: true` is returned (no recommendations found), the extension falls back
   to Workflow A so the user can assign albums manually.

Workflow B is intended for bulk saves where the source profile is already well-represented in the
database. Accuracy should be evaluated periodically by reviewing `recommended_albums` in the
responses and spot-checking that photos landed in the correct albums.

---

## Auto-Save Endpoint

```
POST /api/v1/extension/auto-save
```

Accepts the same request body as `/api/v1/extension/save` (minus the `albums` field).

**Response (new photo, albums found):**
```json
{
  "message": "<filename> is a new photo.",
  "object_id": "...",
  "filename": "...",
  "submission_folder": "...",
  "title": "...",
  "source_profile": "100015224503587",
  "auto_assigned": true,
  "fallback_required": false,
  "recommended_albums": [
    { "path": "sanduni-amanda", "title": "Sanduni Amanda" }
  ]
}
```

**Response (new photo, no recommendations):**
```json
{
  "auto_assigned": false,
  "fallback_required": true,
  "recommended_albums": []
}
```

**Response (duplicate photo):**
```json
{
  "message": "<filename> exists!",
  "object_id": "...",
  "exist_in_albums": "sanduni-amanda,sexy-cleavage",
  "auto_assigned": false,
  "fallback_required": false,
  "recommended_albums": []
}
```

**Save response (new photo):**
```json
{
  "message": "<filename> is a new photo.",
  "object_id": "...",
  "filename": "...",
  "submission_folder": "...",
  "title": "...",
  "source_profile": "100015224503587",
  "added_albums": [
    { "path": "sanduni-amanda", "title": "Sanduni Amanda" }
  ]
}
```

**Save response (duplicate photo):**
```json
{
  "message": "<filename> exists!",
  "object_id": "...",
  "filename": "...",
  "submission_folder": "...",
  "exist_in_albums": "sanduni-amanda,sexy-cleavage"
}
```

---

## Recommendation Endpoint

```
GET /api/v1/extension/recommend-albums?profile_url=<url>
GET /api/v1/extension/recommend-albums?page_url=<url>
```

1. Extracts `source_profile` from the provided URL.
2. Queries `photos` for all documents with that `source_profile`.
3. Queries `albums` for any album containing those photo IDs.
4. Returns albums ranked by how many matching photos they contain.

**Response:**
```json
{
  "source_profile": "100015224503587",
  "albums": [
    { "path": "sanduni-amanda", "title": "Sanduni Amanda", "photo_count": 445 },
    { "path": "sexy-cleavage",  "title": "Sexy Cleavage",  "photo_count": 18  }
  ]
}
```

---

## Caveats

- **Cold start**: a brand-new source profile returns empty recommendations on the first save.
  Suggestions appear from the second photo onwards, once the first has been added to an album.
- **Unidentifiable URLs**: clean URLs like `https://www.facebook.com/photo/?fbid=xxx` with no
  `set` or `id` param yield `source_profile = null` and no recommendations.
- **`a.*` vs profile-level grouping**: `set=a.<album_id>` stores the album ID as `source_profile`,
  not the owning profile ID. Photos from the same person across different albums will have different
  `source_profile` values and will not cross-recommend.

---

## Planned UI Enhancements

### Recommended albums in the "Add to album" modal (`/photo/list`)

When the user clicks the **+ Add to album** button on a photo card, the modal currently shows a
Select2 dropdown of all albums. The planned improvement:

1. On modal open, call `GET /api/v1/extension/recommend-albums` using the photo's `courtesy` URL.
2. Display the recommended albums **below the existing album list** as a quick-add row of clickable
   chips/badges.
3. Clicking a recommended album chip immediately adds the photo to that album without going through
   the full Select2 flow — one click, no confirm needed.
4. Chips for albums the photo is already in are shown as disabled/checked.

This shortens the most common workflow (a batch of photos from the same Facebook source all
belonging to the same album) to a single click per photo.

---

## Data Backfill

Migration `0002_backfill_source_profile` (run via `FLASK_APP=app.app flask migrate`) backfills
`source_profile` on existing photos whose courtesy field contains a Facebook URL and were saved
before this feature was introduced.
