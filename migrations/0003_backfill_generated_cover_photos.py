version = "0003_backfill_generated_cover_photos"
description = (
    "File auto-generated collage cover photos into their own album's "
    "photos array (they were only set as cover_photo, so they showed up "
    "as unclassified on /photo/list instead of belonging to the album "
    "they were generated from)"
)


def upgrade(db, logger, session):
    generated_ids = {
        p['_id'] for p in db.photos.find(
            {'courtesy': 'Generated cover'}, {'_id': 1}, session=session
        )
    }
    logger.info("Found generated cover photos", count=len(generated_ids))

    albums = db.albums.find(
        {'cover_photo': {'$in': list(generated_ids)}},
        {'path': 1, 'cover_photo': 1},
        session=session
    )

    updated = 0
    for album in albums:
        result = db.albums.update_one(
            {'_id': album['_id']},
            {'$addToSet': {'photos': album['cover_photo']}},
            session=session
        )
        if result.modified_count:
            updated += 1

    logger.info("Backfilled generated covers into their album", updated=updated)


def downgrade(db, logger, session):
    raise NotImplementedError("Irreversible migration")
