#!/usr/bin/env python3
"""
Generate a landscape collage cover photo for an album from photos already
in that album, and set it as the album's cover_photo.

How it works:
  1. Load the album and pick N photos evenly spaced through its existing
     `photos` order (so the collage is representative of the whole album,
     not just its first few uploads).
  2. Center-crop + resize each source photo to an equal-width vertical
     slice, then stitch the slices edge-to-edge into one landscape image
     (target aspect ratio ~2.4:1, matching the existing hand-picked covers
     in this app).
  3. Save the collage as a new file under UPLOAD_FOLDER (using the same
     submission-folder rotation as regular uploads), insert a `photos`
     document for it (MD5-deduped like a normal upload), and set it as
     the album's cover_photo.

Usage:
    python scripts/generate_album_cover.py <album-path> [options]
    python scripts/generate_album_cover.py --all-missing [options]

Examples:
    python scripts/generate_album_cover.py cute-breeder --dry-run
    python scripts/generate_album_cover.py cute-breeder
    python scripts/generate_album_cover.py cute-breeder --num-photos 4 --width 1600 --height 667
    python scripts/generate_album_cover.py --all-missing
"""
import argparse
import hashlib
import os
import sys
import uuid
from datetime import datetime

import bson.errors
import pymongo
import pytz
from bson import ObjectId
from dotenv import load_dotenv
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from utils import PhotoManager  # noqa: E402

load_dotenv()

TZ_LONDON = pytz.timezone("Europe/London")
DEFAULT_UPLOAD_FOLDER = "/tmp/photo-manager/upload"


class CoverGenerationError(Exception):
    """Raised for expected per-album failures so batch runs can skip and continue."""


def get_db():
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    if not db_host or not db_port:
        raise RuntimeError("DB_HOST and DB_PORT must be set (see .env)")
    db_name = os.environ.get('DB_NAME', 'photodb')
    client = pymongo.MongoClient(db_host, int(db_port), serverSelectionTimeoutMS=5000)
    return client[db_name]


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


def generate_cover(db, upload_folder, album_path, num_photos, target_w, target_h, dry_run):
    album = db.albums.find_one({'path': album_path})
    if not album:
        raise CoverGenerationError(f"Album not found: {album_path}")

    photo_ids = _normalize_object_ids(album.get('photos', []))
    if not photo_ids:
        raise CoverGenerationError(f"Album '{album_path}' has no photos to build a cover from")

    chosen_ids = pick_evenly_spaced(photo_ids, num_photos)
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
        return

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
        {'$set': {'cover_photo': new_photo_id, 'date_modified': datetime.now(TZ_LONDON)}}
    )
    print(f"Album '{album_path}' cover_photo set to {new_photo_id}")


def run_batch(db, upload_folder, num_photos, target_w, target_h, dry_run):
    albums = list(
        db.albums.find({'cover_photo': {'$exists': False}}, {'path': 1})
        .sort('path', pymongo.ASCENDING)
    )
    print(f"Found {len(albums)} album(s) without a cover_photo\n")

    succeeded = []
    failed = []
    for i, album in enumerate(albums, start=1):
        path = album['path']
        print(f"[{i}/{len(albums)}] {path}")
        try:
            generate_cover(db, upload_folder, path, num_photos, target_w, target_h, dry_run)
            succeeded.append(path)
        except CoverGenerationError as e:
            print(f"  SKIPPED: {e}")
            failed.append((path, str(e)))
        print()

    print("=" * 60)
    print(f"Done. {len(succeeded)} succeeded, {len(failed)} skipped/failed.")
    if failed:
        print("Failures:")
        for path, reason in failed:
            print(f"  - {path}: {reason}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'album_path', nargs='?',
        help="Album 'path' slug, e.g. cute-breeder (omit when using --all-missing)"
    )
    parser.add_argument(
        '--all-missing', action='store_true',
        help="Run for every album that has no cover_photo set yet, instead of one album"
    )
    parser.add_argument(
        '--num-photos', type=int, default=3,
        help="Number of photos to combine (default: 3)"
    )
    parser.add_argument(
        '--width', type=int, default=1200,
        help="Target collage width in px (default: 1200)"
    )
    parser.add_argument(
        '--height', type=int, default=500,
        help="Target collage height in px (default: 500)"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Build the collage but don't write to DB/disk"
    )
    args = parser.parse_args()

    if not args.all_missing and not args.album_path:
        parser.error("album_path is required unless --all-missing is given")
    if args.all_missing and args.album_path:
        parser.error("pass either album_path or --all-missing, not both")

    upload_folder = os.environ.get('UPLOAD_FOLDER', DEFAULT_UPLOAD_FOLDER)
    db = get_db()

    if args.all_missing:
        run_batch(db, upload_folder, args.num_photos, args.width, args.height, args.dry_run)
        return

    try:
        generate_cover(
            db, upload_folder, args.album_path, args.num_photos,
            args.width, args.height, args.dry_run
        )
    except CoverGenerationError as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    main()
