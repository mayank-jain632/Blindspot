from __future__ import annotations

from collections import defaultdict
import fnmatch
import hashlib
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from ..models import Commit, FileHistory, timestamp

DEFAULT_EXCLUSIONS = ["node_modules/", "vendor/", "dist/", "build/", "*.lock",
                      "*.min.*", "*.generated.*"]


class RepoError(Exception):
    """A safe, user-facing checkout error."""


def git(root: Path, *args: str, allow_failure: bool = False) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode and not allow_failure:
        raise RepoError("Git could not read the requested repository metadata.")
    return result.stdout if not result.returncode else b""


def resolve_root(path: Path) -> Path | None:
    candidate = path if path.is_dir() else path.parent if path.is_file() else None
    if candidate is None:
        return None
    value = git(candidate, "rev-parse", "--show-toplevel", allow_failure=True)
    return Path(os.fsdecode(value.rstrip(b"\n"))).resolve() if value else None


def normalize_remote(value: str, root: Path) -> str:
    if not value:
        return "<no-remote>"
    parsed = urlsplit(value)
    if parsed.scheme and parsed.hostname:
        host = parsed.hostname.lower()
        if parsed.port:
            host += f":{parsed.port}"
        return f"{host}/{parsed.path.lstrip('/').removesuffix('.git')}"
    match = re.fullmatch(r"(?:[^/@:]+@)?([^/:]+):(.+)", value)
    if match:
        return f"{match[1].lower()}/{match[2].removesuffix('.git')}"
    if parsed.scheme == "file":
        return f"local:{Path(parsed.path).resolve()}"
    return f"local:{(root / value).resolve()}"


def matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        directory = pattern.strip("/")
        return directory in path.split("/")[:-1] if "/" not in directory else path.startswith(directory + "/")
    return fnmatch.fnmatchcase(path, pattern)


class Repository:
    def __init__(self, path: Path):
        root = resolve_root(path)
        if root is None:
            raise RepoError("The supplied path is not in a Git repository.")
        self.root = root
        if git(root, "rev-parse", "--is-shallow-repository").strip() == b"true":
            raise RepoError("Shallow history cannot be classified; fetch full history first.")
        self.head = git(root, "rev-parse", "--verify", "HEAD", allow_failure=True).decode().strip()
        if not self.head:
            raise RepoError("This repository has no committed HEAD; create a first commit before scanning.")
        self.roots = sorted(git(root, "rev-list", "--max-parents=0", self.head).decode().split())
        remote = git(root, "config", "--get", "remote.origin.url", allow_failure=True).decode(errors="replace").strip()
        self.remote = normalize_remote(remote, root)
        self.key = hashlib.sha256(("\n".join(self.roots) + "\n" + self.remote).encode()).hexdigest()
        self.email = git(root, "config", "--get", "user.email", allow_failure=True).decode(errors="replace").strip()
        self.name = git(root, "config", "--get", "user.name", allow_failure=True).decode(errors="replace").strip()
        self.email = self.canonical_email(self.email, self.name) if self.email else ""

    def canonical_email(self, email: str, name: str = "") -> str:
        if not email or any(c in email + name for c in "\r\n<>"):
            return email
        mapped = git(self.root, "check-mailmap", f"{name} <{email}>", allow_failure=True).decode(errors="replace").strip()
        match = re.search(r"<([^<>]+)>$", mapped)
        return match[1] if match else email

    def inventory(self, exclusions: list[str], includes: list[str]) -> tuple[dict[str, FileHistory], dict[str, int]]:
        entries = git(self.root, "ls-tree", "-r", "-z", self.head).split(b"\0")
        blobs = []
        excluded: dict[str, int] = defaultdict(int)
        for entry in entries:
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, sha = metadata.split()
            path = os.fsdecode(raw_path)
            if mode not in {b"100644", b"100755"} or kind != b"blob":
                excluded["non_regular"] += 1
            elif any(matches(path, pattern) for pattern in exclusions) and not any(matches(path, pattern) for pattern in includes):
                excluded["configured_pattern"] += 1
            else:
                blobs.append((path, sha))
        files = {}
        process = subprocess.Popen(["git", "-C", str(self.root), "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        assert process.stdin is not None and process.stdout is not None
        try:
            for path, sha in blobs:
                process.stdin.write(sha + b"\n")
                process.stdin.flush()
                header = process.stdout.readline().split()
                if len(header) != 3 or header[1] != b"blob":
                    raise RepoError("A captured Git object could not be read.")
                size = int(header[2])
                data = process.stdout.read(size)
                if len(data) != size or process.stdout.read(1) != b"\n":
                    raise RepoError("A captured Git object was incomplete.")
                try:
                    if b"\0" in data:
                        raise UnicodeError()
                    data.decode("utf-8")
                except UnicodeError:
                    excluded["binary_or_non_utf8"] += 1
                    continue
                files[path] = FileHistory(path, hashlib.sha256(data).hexdigest(),
                    data.count(b"\n") + int(bool(data) and not data.endswith(b"\n")))
        finally:
            process.stdin.close()
            process.stdout.close()
            process.wait()
        return files, dict(sorted(excluded.items()))

    def history(self, files: dict[str, FileHistory]) -> dict[str, str]:
        data = git(self.root, "log", "--format=BS_COMMIT%x00%H%x00%aI%x00%cI%x00%aN%x00%aE%x00",
                   "--name-status", "-z", "--find-renames", "--diff-merges=first-parent", self.head, "--")
        tokens = data.split(b"\0")
        authors: dict[str, str] = {}
        statuses: dict[str, set[str]] = defaultdict(set)
        index = 0
        current = None
        while index < len(tokens):
            token = tokens[index].lstrip(b"\n")
            index += 1
            if not token:
                continue
            if token == b"BS_COMMIT":
                sha, author, committer, name, email = tokens[index:index + 5]
                index += 5
                at, ct = timestamp(author.decode()), timestamp(committer.decode())
                if at is None or ct is None:
                    raise RepoError("Git history contains an unsupported timestamp.")
                current = (sha.decode(), at, ct, name.decode(errors="replace"), email.decode(errors="replace"))
                authors[current[4]] = current[3]
                continue
            status = token.decode("ascii", errors="replace")
            if not re.fullmatch(r"[ACDMRTUXB][0-9]*", status) or current is None:
                raise RepoError("Git history has an unsupported change-record shape.")
            if status.startswith(("R", "C")):
                old, new = (os.fsdecode(v) for v in tokens[index:index + 2])
                index += 2
                paths = [old, new]
                for path in paths:
                    if path in files:
                        files[path].lineage_ambiguous = True
            else:
                paths = [os.fsdecode(tokens[index])]
                index += 1
            for path in paths:
                if path in files:
                    statuses[path].add(status[0])
                    if not any(c.sha == current[0] for c in files[path].commits):
                        files[path].commits.append(Commit(*current, status))
        for path, history in files.items():
            if "A" in statuses[path] and "D" in statuses[path]:
                history.lineage_ambiguous = True
            history.commits.sort(key=lambda c: (c.author_time, c.sha), reverse=True)
        return dict(sorted(authors.items()))

    def current_head(self) -> str:
        return git(self.root, "rev-parse", "HEAD").decode().strip()
