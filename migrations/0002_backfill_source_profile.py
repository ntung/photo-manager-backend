version = "0002_backfill_source_profile"
description = "Backfill source_profile on photos that have a Facebook courtesy URL"

from html import unescape as html_unescape
from urllib.parse import urlparse, parse_qs

_FB_RESERVED = {
    'photo', 'photos', 'groups', 'pages', 'events', 'media',
    'reel', 'reels', 'watch', 'marketplace', 'stories', 'profile',
    'permalink', 'share',
}


def _extract_facebook_profile(url):
    if not url or 'facebook.com' not in url:
        return None
    parsed = urlparse(html_unescape(url))
    params = parse_qs(parsed.query)
    if 'id' in params:
        return params['id'][0]
    if 'set' in params:
        set_val = params['set'][0]
        parts = set_val.split('.')
        if len(parts) >= 2:
            return parts[1]
        return set_val
    path_parts = [p for p in parsed.path.split('/') if p]
    if path_parts and path_parts[0] not in _FB_RESERVED:
        return path_parts[0]
    return None


def upgrade(db, logger, session):
    photos = list(db.photos.find(
        {'source_profile': {'$exists': False}, 'courtesy': {'$regex': 'facebook.com'}},
        {'_id': 1, 'courtesy': 1},
        session=session
    ))
    logger.info("Found photos to backfill", count=len(photos))
    updated = 0
    for photo in photos:
        profile = _extract_facebook_profile(photo.get('courtesy', ''))
        if profile:
            db.photos.update_one(
                {'_id': photo['_id']},
                {'$set': {'source_profile': profile}},
                session=session
            )
            updated += 1
    logger.info("Backfilled source_profile", updated=updated)


def downgrade(db, logger, session):
    raise NotImplementedError("Irreversible migration")
