import logging

from bson import ObjectId
from pymongo import MongoClient, UpdateOne

# --- CONFIGURATION ---
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "photodb"
COLLECTION_NAME = "albums"
FIELD_NAME = "photos"  # The field containing the array of IDs
DRY_RUN = False        # Set to False to actually apply changes

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def run_migration():
    """
    Convert valid 24-character hex string to object ids on photos collection
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    logger.info(f"Starting migration on {DB_NAME}.{COLLECTION_NAME}...")
    if DRY_RUN:
        logger.info("!!! DRY RUN ENABLED - No changes will be saved !!!")

    updates = []
    total_scanned = 0
    total_to_update = 0

    # 1. Fetch only documents where the field exists
    cursor = collection.find({
        FIELD_NAME: {"$exists": True}
    }, {
        FIELD_NAME: 1
    })

    for doc in cursor:
        total_scanned += 1
        doc_id = doc["_id"]
        original_list = doc.get(FIELD_NAME, [])

        if not isinstance(original_list, list):
            continue

        new_list = []
        needs_update = False

        for item in original_list:
            # Check if item is a valid 24-char hex string
            if isinstance(item, str) and ObjectId.is_valid(item):
                new_list.append(ObjectId(item))
                needs_update = True
            else:
                # Keep original (could be already an ObjectId or a non-ID string)
                new_list.append(item)

        if needs_update:
            total_to_update += 1
            updates.append(
                UpdateOne(
                    {"_id": doc_id},
                    {"$set": {FIELD_NAME: new_list}}
                )
            )

    # 2. Execution Phase
    if not updates:
        logger.info("No documents required migration. Everything is already "
                    "ObjectId.")
        return

    logger.info(f"Scanned {total_scanned} documents. Found {total_to_update} "
                f"documents needing update.")

    if not DRY_RUN:
        try:
            result = collection.bulk_write(updates, ordered=False)
            logger.info(f"Migration Complete: {result.modified_count} "
                        f"documents updated.")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
    else:
        logger.info(f"Dry run complete. Would have updated {len(updates)} "
                    f"documents.")

if __name__ == "__main__":
    run_migration()
