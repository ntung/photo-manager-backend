"""
Shared logic for generating a landscape collage cover photo for an album
from photos already in that album.

Used by both scripts/generate_album_cover.py (CLI, batch runs) and the
'/api/v1/album/<path>/generate-cover' route in app.py (on-demand, from the
album view page).

How it works:
  1. Load the album and pick N photos from its existing `photos` order -
     evenly spaced by default (so the collage is representative of the
     whole album, not just its first few uploads), or randomly when
     `randomize=True` (so re-running it on an unchanged album still gives
     a different result, for a manual "Re-generate cover" action).
  2. Center-crop + resize each source photo to an equal-width vertical
     slice, then stitch the slices edge-to-edge into one landscape image
     (target aspect ratio ~2.4:1, matching the existing hand-picked covers
     in this app).
  3. Save the collage as a new file under upload_folder (using the same
     submission-folder rotation as regular uploads), insert a `photos`
     document for it (MD5-deduped like a normal upload), and set it as
     the album's cover_photo.
"""
import hashlib
import os
import random
import uuid
from datetime import datetime

import bson.errors
import pytz
from bson import ObjectId
from PIL import Image

from . import PhotoManager

TZ_LONDON = pytz.timezone("Europe/London")

DEFAULT_NUM_PHOTOS = 3
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 500

# A single photo cropped to the wide album banner via object-fit:cover looks
# fine once it's landscape-oriented; anything squarer/taller than this loses
# too much of the frame to the crop and is a better candidate for a
# generated collage cover instead.
MIN_COVER_ASPECT_RATIO = 1.3


class CoverGenerationError(Exception):
    """Raised for expected per-album failures so batch runs can skip and continue."""


def is_landscape_enough(path, min_ratio=MIN_COVER_ASPECT_RATIO):
    """Return True if the image at `path` is landscape enough to make a
    decent object-fit:cover crop for the wide album banner. Treats a
    missing/unreadable file as not suitable, so it doesn't block a
    generate-cover retry."""
    try:
        with Image.open(path) as im:
            w, h = im.size
    except OSError:
        return False
    return h > 0 and (w / h) >= min_ratio


def _normalize_object_ids(raw_ids):
    """Some album.photos entries are stored as plain strings instead of
    ObjectId (pre-existing data issue) - coerce them so $in lookups match,
    dropping anything that isn't a valid ObjectId at all."""
    normalized = []
    for x in raw_ids:
        if isinstance(x, ObjectId):
            normalized.append(x)
            continue
        try:
            normalized.append(ObjectId(x))
        except (bson.errors.InvalidId, TypeError):
            print(f"  WARNING: skipping malformed photo id in album.photos: {x!r}")
    return normalized


def pick_evenly_spaced(photo_ids, num_photos):
    n = len(photo_ids)
    if n <= num_photos:
        return photo_ids
    if num_photos == 1:
        return [photo_ids[n // 2]]
    indices = sorted({round(i * (n - 1) / (num_photos - 1)) for i in range(num_photos)})
    return [photo_ids[i] for i in indices]


def pick_random(photo_ids, num_photos):
    """Like pick_evenly_spaced, but a random subset instead of a
    deterministic one - so re-running this on an unchanged album gives a
    different collage instead of reproducing (or MD5-deduping back to)
    the same one every time."""
    n = len(photo_ids)
    if n <= num_photos:
        return photo_ids
    indices = sorted(random.sample(range(n), num_photos))
    return [photo_ids[i] for i in indices]


def center_crop_to_aspect(img, target_ratio):
    w, h = img.size
    current_ratio = w / h
    if current_ratio > target_ratio:
        # too wide: crop the sides
        new_w = round(h * target_ratio)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        # too tall: crop top/bottom
        new_h = round(w / target_ratio)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    return img.crop(box)


def build_collage(image_paths, target_w, target_h):
    n = len(image_paths)
    slice_w = target_w // n
    canvas = Image.new('RGB', (slice_w * n, target_h), color=(0, 0, 0))
    slice_ratio = slice_w / target_h
    x = 0
    for path in image_paths:
        with Image.open(path) as im:
            im = im.convert('RGB')
            im = center_crop_to_aspect(im, slice_ratio)
            im = im.resize((slice_w, target_h), Image.LANCZOS)
            canvas.paste(im, (x, 0))
        x += slice_w
    return canvas


def generate_cover(
    db, upload_folder, album_path, num_photos=DEFAULT_NUM_PHOTOS,
    target_w=DEFAULT_WIDTH, target_h=DEFAULT_HEIGHT, dry_run=False, randomize=False
):
    """Build a collage cover for the album at `album_path` and set it as
    cover_photo. Returns the new (or reused, or dry-run None) photo
    ObjectId. Raises CoverGenerationError for expected per-album failures.

    By default photos are picked evenly spaced through the album's order,
    for reproducible batch/CLI runs. Pass randomize=True (used by the
    interactive "Re-generate cover" button) to pick a random subset
    instead, so repeated clicks produce different collages."""
    album = db.albums.find_one({'path': album_path})
    if not album:
        raise CoverGenerationError(f"Album not found: {album_path}")

    photo_ids = _normalize_object_ids(album.get('photos', []))
    if not photo_ids:
        raise CoverGenerationError(f"Album '{album_path}' has no photos to build a cover from")

    picker = pick_random if randomize else pick_evenly_spaced
    chosen_ids = picker(photo_ids, num_photos)
    projection = {'folder': 1, 'filename': 1, 'title': 1}
    chosen_docs = {
        p['_id']: p
        for p in db.photos.find({'_id': {'$in': chosen_ids}}, projection)
    }
    missing = [pid for pid in chosen_ids if pid not in chosen_docs]
    if missing:
        raise CoverGenerationError(f"Photo doc(s) not found for ids: {missing}")

    source_paths = []
    for pid in chosen_ids:
        doc = chosen_docs[pid]
        path = os.path.join(upload_folder, doc['folder'], doc['filename'])
        if not os.path.isfile(path):
            raise CoverGenerationError(f"Source file missing on disk: {path}")
        source_paths.append(path)

    print(f"Album: {album.get('title')!r} ({album_path}), {len(photo_ids)} photos total")
    print(f"Chosen {len(chosen_ids)} source photo(s):")
    for pid, path in zip(chosen_ids, source_paths):
        print(f"  - {pid} -> {path}")

    try:
        collage = build_collage(source_paths, target_w, target_h)
    except OSError as e:
        raise CoverGenerationError(f"Could not read/decode a source image: {e}") from e
    print(f"Collage size: {collage.size[0]}x{collage.size[1]}")

    if dry_run:
        preview_path = os.path.join(
            '/tmp', f"cover-preview-{album_path}.jpg"
        )
        collage.save(preview_path, 'JPEG', quality=90)
        print(f"[dry-run] Not saving to DB. Preview written to {preview_path}")
        return None

    # Save directly under the target submission folder so the later rename
    # (dedup discard or final filename) stays on the same filesystem.
    pm_init = PhotoManager.InitPM(upload_folder, "aaaa")
    submission_folders = pm_init.submission_folder_dict()
    folder = pm_init.infer_current_submission_folder(submission_folders)
    dest_dir = os.path.join(upload_folder, folder)
    os.makedirs(dest_dir, exist_ok=True)
    tmp_path = os.path.join(dest_dir, f".tmp-cover-{uuid.uuid4()}.jpg")
    collage.save(tmp_path, 'JPEG', quality=90)
    with open(tmp_path, 'rb') as f:
        content = f.read()
    hash_md5 = hashlib.md5(content).hexdigest()

    existing = db.photos.find_one({'hash_md5': hash_md5})
    if existing:
        os.remove(tmp_path)
        new_photo_id = existing['_id']
        print(f"Identical cover already exists as photo {new_photo_id}, reusing it")
    else:
        filename = f"{uuid.uuid4()}.jpg"
        dest_path = os.path.join(dest_dir, filename)
        os.replace(tmp_path, dest_path)

        now = datetime.now(TZ_LONDON)
        result = db.photos.insert_one({
            'folder': folder,
            'filename': filename,
            'title': f"{album.get('title', album_path)} - cover",
            'description': (
                'Auto-generated collage cover from: '
                + ', '.join(str(pid) for pid in chosen_ids)
            ),
            'courtesy': 'Generated cover',
            'date_uploaded': now,
            'date_modified': now,
            'hash_md5': hash_md5,
        })
        new_photo_id = result.inserted_id
        print(f"Saved new cover photo {new_photo_id} -> {dest_path}")

    db.albums.update_one(
        {'path': album_path},
        {
            '$set': {'cover_photo': new_photo_id, 'date_modified': datetime.now(TZ_LONDON)},
            # File the generated cover into the album itself too, so it shows
            # up as classified (part of this album) rather than lingering in
            # the unclassified pile on /photo/list. $addToSet keeps this a
            # no-op if it's already there (e.g. an identical cover reused
            # from a previous generation).
            '$addToSet': {'photos': new_photo_id},
        }
    )
    print(f"Album '{album_path}' cover_photo set to {new_photo_id}")
    return new_photo_id
