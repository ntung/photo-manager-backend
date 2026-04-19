# migration_framework/runner.py
import time

from pymongo import MongoClient

from .registry import MigrationRegistry
from .logger import MigrationLogger


class MigrationRunner:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.registry = MigrationRegistry()
        self.logger = MigrationLogger()

    def get_applied_versions(self):
        return {
            m["version"]
            for m in self.db.migration_versions.find({}, {"version": 1})
        }

    def run(self, target=None, dry_run=False):
        migrations = self.registry.discover()
        applied = self.get_applied_versions()

        for module in migrations:
            if module.version in applied:
                continue
            if target and module.version > target:
                break

            self._run_single(module, dry_run)

    def _run_single(self, module, dry_run):
        self.logger.info("Starting migration", version=module.version)

        if dry_run:
            self.logger.info("Dry run: skipping execution")
            return

        start = time.time()

        with self.client.start_session() as session:
            try:
                if self.supports_transactions():
                    with session.start_transaction():
                        module.upgrade(self.db, self.logger, session)
                        self.db.migration_versions.insert_one(
                            {
                                "version": module.version,
                                "applied_at": time.time()},
                            session=session
                        )
                else:
                    module.upgrade(self.db, self.logger, session)
                    self.db.migration_versions.insert_one(
                        {
                            "version": module.version,
                            "applied_at": time.time()},
                        session=session
                    )
            except Exception as e:
                self.logger.error("Migration failed", error=str(e))
                raise

        duration = round((time.time() - start) * 1000)
        self.logger.info("Migration complete",
                         version=module.version, duration_ms=duration)

    def supports_transactions(self):
        info = self.client.admin.command("ismaster")
        return "setName" in info
