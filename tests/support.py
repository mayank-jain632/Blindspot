from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="blindspot-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        config = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        config.start()
        self.addCleanup(config.stop)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture User")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "core.hooksPath", str(self.base / "no-hooks"))
        self.sessions = self.base / "sessions"
        (self.sessions / "project").mkdir(parents=True)
        self.source = self.sessions / "project" / "fixture.jsonl"
        self.state_dir = self.base / "state"

    def git(self, *args, when=None, email=None):
        env = self.env.copy()
        if when:
            env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        if email:
            env.update(GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_NAME="Other User",
                       GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_NAME="Other User")
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, env=env).stdout

    def commit(self, files, when="2026-09-01T00:00:00Z", email=None):
        for name, content in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        self.git("add", "--all")
        self.git("commit", "-m", "Synthetic change", when=when, email=email)

    def transcript(self, rows):
        self.source.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return self.source

    def user(self, when="2026-10-01T10:00:00Z", **fields):
        return {"type": "user", "cwd": str(self.root), "sessionId": "fixture",
                "timestamp": when, **fields}

    def call(self, name="Edit", path="agent.py", tool_id="edit-1", when="2026-10-01T10:01:00Z"):
        key = "notebook_path" if name == "NotebookEdit" else "file_path"
        return {"type": "assistant", "cwd": str(self.root), "timestamp": when,
            "message": {"content": [{"type": "tool_use", "id": tool_id,
                "name": name, "input": {key: path} if name != "Bash" else {}}]}}

    def result(self, tool_id="edit-1", error=False, when="2026-10-01T10:02:00Z"):
        return self.user(when, message={"content": [{"type": "tool_result",
            "tool_use_id": tool_id, "content": "", "is_error": error}]})
