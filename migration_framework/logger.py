# migration_framework/logger.py
import json
import logging

logger = logging.getLogger("migration_framework")


class MigrationLogger:
    def info(self, msg, **kwargs):
        logger.info(json.dumps({"msg": msg, **kwargs}))

    def error(self, msg, **kwargs):
        logger.error(json.dumps({"msg": msg, **kwargs}))
