"""Small Phase 1 configuration/inventory store; no transcript payloads."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


class StateError(Exception):
    pass


class State:
    def __init__(self, directory: Path, read_only: bool = False):
        self.read_only = read_only
        self.directory = directory.expanduser().resolve()
        self.path = self.directory / "prototype.json"
        try:
            self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
            if not isinstance(self.data, dict) or self.data.get("version", 1) != 1:
                raise ValueError()
            self.data.setdefault("version", 1)
            for key in ("checkouts", "links", "inventories"):
                self.data.setdefault(key, {})
                if not isinstance(self.data[key], dict):
                    raise ValueError()
        except (ValueError, OSError):
            raise StateError("Could not read prototype state; use a valid state directory.") from None

    def checkout(self, root: str, repository_key: str) -> dict:
        record = self.data["checkouts"].get(root, {})
        if not isinstance(record, dict) or not isinstance(record.get("identities", []), list):
            raise StateError("Checkout state is malformed; use a valid state directory.")
        if any(not isinstance(email, str) for email in record.get("identities", [])):
            raise StateError("Identity state is malformed; use a valid state directory.")
        if record.get("repository_key", repository_key) != repository_key:
            raise StateError("Repository identity changed at this checkout; reconcile its state explicitly or use a fresh state directory.")
        return record

    def guard_repository(self, root: Path) -> None:
        if self.directory.is_relative_to(root.resolve()):
            raise StateError("Choose a --state-dir outside the inspected repository; scans never write into it.")

    def save(self) -> None:
        if self.read_only:
            return
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as handle:
                temporary = handle.name
                json.dump(self.data, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        except OSError:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            raise StateError("Could not write application state; select a writable --state-dir.") from None
