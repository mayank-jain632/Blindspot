"""Atomic review storage, separate from disposable scan inventories."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from . import ReviewError


class ReviewStore:
    def __init__(self, directory: Path, read_only: bool = False):
        self.directory = directory.expanduser().resolve()
        self.path = self.directory / "reviews.json"
        self.read_only = read_only

    def guard(self, root: Path):
        if self.directory.is_relative_to(root.resolve()):
            raise ReviewError("Choose review state outside the inspected checkout.")

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text()) if self.path.exists() else {
                "version": 1, "sequence": 0, "sets": {}, "attempts": {}}
            if not isinstance(data, dict) or data.get("version") != 1 or type(data.get("sequence")) is not int:
                raise ValueError()
            if not isinstance(data.get("sets"), dict) or not isinstance(data.get("attempts"), dict):
                raise ValueError()
            data.setdefault("feedback", [])
            if not isinstance(data["feedback"], list) or any(
                not isinstance(f, dict) or not isinstance(f.get("attempt_id"), str) or
                f["attempt_id"] not in data["attempts"] or
                type(f.get("sequence")) is not int for f in data["feedback"]):
                raise ValueError()
            return data
        except (OSError, ValueError):
            raise ReviewError("Could not read review state; use a valid state directory.") from None

    @contextmanager
    def transaction(self):
        if self.read_only:
            raise ReviewError("--read-only cannot import quizzes, record answers, or change review records.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.directory / "reviews.lock", os.O_CREAT | os.O_RDWR, 0o600)
        temporary = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            data = self.read()
            yield data
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as handle:
                temporary = handle.name
                json.dump(data, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary:
                os.unlink(temporary)
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def sequence(data: dict) -> int:
    data["sequence"] += 1
    return data["sequence"]
