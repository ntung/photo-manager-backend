# migration_framework/registry.py
import os
import importlib


class MigrationRegistry:
    def __init__(self, migrations_dir="migrations"):
        self.migrations_dir = migrations_dir

    def discover(self):
        files = sorted(
            f[:-3] for f in os.listdir(self.migrations_dir)
            if f.endswith(".py") and not f.startswith("__")
        )
        migrations = []
        for name in files:
            module = importlib.import_module(f"{self.migrations_dir}.{name}")
            self._validate(module)
            migrations.append(module)
        return migrations

    def _validate(self, module):
        required = ["version", "description", "upgrade", "downgrade"]
        for attr in required:
            if not hasattr(module, attr):
                raise ValueError(f"Migration {module} missing {attr}")
