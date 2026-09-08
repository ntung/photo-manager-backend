#!/usr/bin/env python3
"""
Generate a landscape collage cover photo for an album from photos already
in that album, and set it as the album's cover_photo.

The collage-building logic lives in app/utils/cover_generator.py, shared
with the on-demand '/api/v1/album/<path>/generate-cover' route in app.py.
See that module's docstring for how it works.

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
import os
import sys

import pymongo
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from utils import cover_generator  # noqa: E402

load_dotenv()

DEFAULT_UPLOAD_FOLDER = "/tmp/photo-manager/upload"


def get_db():
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    if not db_host or not db_port:
        raise RuntimeError("DB_HOST and DB_PORT must be set (see .env)")
    db_name = os.environ.get('DB_NAME', 'photodb')
    client = pymongo.MongoClient(db_host, int(db_port), serverSelectionTimeoutMS=5000)
    return client[db_name]


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
            cover_generator.generate_cover(
                db, upload_folder, path, num_photos, target_w, target_h, dry_run
            )
            succeeded.append(path)
        except cover_generator.CoverGenerationError as e:
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
        '--num-photos', type=int, default=cover_generator.DEFAULT_NUM_PHOTOS,
        help="Number of photos to combine (default: 3)"
    )
    parser.add_argument(
        '--width', type=int, default=cover_generator.DEFAULT_WIDTH,
        help="Target collage width in px (default: 1200)"
    )
    parser.add_argument(
        '--height', type=int, default=cover_generator.DEFAULT_HEIGHT,
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
        cover_generator.generate_cover(
            db, upload_folder, args.album_path, args.num_photos,
            args.width, args.height, args.dry_run
        )
    except cover_generator.CoverGenerationError as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    main()
