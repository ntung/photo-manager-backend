# migration_framework/logger.py
import json


class MigrationLogger:
    def info(self, msg, **kwargs):
        print(json.dumps({"level": "INFO", "msg": msg, **kwargs}))

    def error(self, msg, **kwargs):
        print(json.dumps({"level": "ERROR", "msg": msg, **kwargs}))
