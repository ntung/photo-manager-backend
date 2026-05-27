# migrations/0001_add_indexes.py

version = "0001_add_indexes"
description = "Create indexes on photos collection"


def upgrade(db, logger, session):
    logger.info("Creating index on hash_md5")
    db.photos.create_index("hash_md5", unique=True, session=session)


def downgrade(db, logger, session):
    logger.info("Downgrading from hash_md5 not supported for this version")
    raise NotImplementedError("Irreversible migration")
