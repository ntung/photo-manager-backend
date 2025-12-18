# migrations/0001_add_indexes.py

version = "0001_add_indexes"
description = "Create indexes on users collection"


def upgrade(db, logger, session):
    logger.info("Creating index on email")
    # db.users.create_index("email", unique=True, session=session)


def downgrade(db, logger, session):
    logger.info("Dropping index on email")
    # db.users.drop_index("email_1", session=session)
