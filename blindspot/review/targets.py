from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from ..scan.repo import DEFAULT_EXCLUSIONS, Repository, git, matches
from . import ReviewError

MAX_LINES = 300
MAX_BYTES = 16 * 1024


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def text_at(repo: Repository, revision: str, path: str) -> str:
    if not isinstance(path, str) or not path or "\0" in path:
        raise ReviewError("A target/context path must be a relative Git path.")
    parts = PurePosixPath(path)
    if parts.is_absolute() or ".." in parts.parts or str(parts) != path:
        raise ReviewError("Target/context paths must be normalized and stay inside the checkout.")
    if any(matches(path, pattern) for pattern in DEFAULT_EXCLUSIONS):
        raise ReviewError("This target/context matches a default source exclusion.")
    for entry in git(repo.root, "ls-tree", "-r", "-z", revision).split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        if os.fsdecode(raw_path) != path:
            continue
        mode, kind, sha = meta.split()
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise ReviewError("Target/context must be a regular committed text file.")
        blob = git(repo.root, "cat-file", "blob", sha.decode())
        try:
            if b"\0" in blob:
                raise UnicodeError()
            return blob.decode("utf-8")
        except UnicodeError:
            raise ReviewError("Target/context must contain UTF-8 text.") from None
    raise ReviewError("Target/context path is absent at this revision.")


def block(repo: Repository, revision: str, path: str, start: int | None = None,
          end: int | None = None, *, target: bool = False) -> dict:
    text = text_at(repo, revision, path)
    lines = text.splitlines(keepends=True)
    start = 1 if start is None else start
    end = len(lines) if end is None else end
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ReviewError("Line range must be an inclusive range inside the committed file.")
    code = "".join(lines[start - 1:end])
    if target and end - start + 1 < 10:
        raise ReviewError("Review targets must contain at least 10 lines.")
    if end - start + 1 > MAX_LINES or len(code.encode()) > MAX_BYTES:
        raise ReviewError("Select a smaller explicit range: exported blocks are limited to 300 lines / 16 KiB.")
    return {"path": path, "start_line": start, "end_line": end,
            "file_hash": hashlib.sha256(text.encode()).hexdigest(),
            "content_hash": hashlib.sha256(code.encode()).hexdigest(), "code": code}


def relative_file(repo: Repository, file: Path) -> str:
    # Resolve the containing directory, never follow the final file's symlink.
    file = file.expanduser().absolute()
    selected = file.parent.resolve() / file.name
    try:
        return selected.relative_to(repo.root).as_posix()
    except ValueError:
        raise ReviewError("Target/context must be inside the selected checkout.") from None


def export_target(file: Path, start: int | None = None, end: int | None = None,
                  name: str | None = None, contexts: list[tuple[Path, int | None, int | None]] | None = None) -> dict:
    file = file.expanduser().absolute()
    ancestor = file.parent
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    repo = Repository(ancestor)
    if (start is None) != (end is None):
        raise ReviewError("Supply both --start and --end for an explicit target range.")
    path = relative_file(repo, file)
    target = block(repo, repo.head, path, start, end, target=True)
    target["key"] = name or ("whole-file" if start is None else f"lines:{start}-{end}")
    if not isinstance(target["key"], str) or not target["key"].strip() or len(target["key"]) > 200:
        raise ReviewError("Target name must be a nonempty string of at most 200 characters.")
    context = [block(repo, repo.head, relative_file(repo, f), a, b) for f, a, b in contexts or []]
    context.sort(key=lambda c: (c["path"], c["start_line"], c["end_line"]))
    if len(context) > 8 or len({(c["path"], c["start_line"], c["end_line"]) for c in context}) != len(context):
        raise ReviewError("Supply at most eight distinct context blocks.")
    if repo.current_head() != repo.head:
        raise ReviewError("HEAD moved during target export; retry against one revision.")
    return {"schema_version": 1, "checkout": str(repo.root), "repository_key": repo.key,
            "source_revision": repo.head, "target": target, "context": context}


def binding(manifest: dict) -> str:
    def source(c):
        return {k: c[k] for k in ("path", "start_line", "end_line", "file_hash", "content_hash")}
    return digest({"checkout": manifest["checkout"], "repository_key": manifest["repository_key"],
                   "target": source(manifest["target"]),
                   "context": sorted((source(c) for c in manifest["context"]),
                                     key=lambda c: (c["path"], c["start_line"], c["end_line"]))})


def reachable(repo: Repository, revision: str) -> bool:
    return subprocess.run(["git", "-C", str(repo.root), "merge-base", "--is-ancestor", revision, repo.head],
        capture_output=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).returncode == 0


def currentness(repo: Repository, manifest: dict) -> str:
    if manifest["checkout"] != str(repo.root) or manifest["repository_key"] != repo.key:
        raise ReviewError("Checkout identity changed; reconcile review records explicitly.")
    if not reachable(repo, manifest["source_revision"]):
        return "orphaned"
    try:
        for source in [manifest["target"], *manifest["context"]]:
            fresh = block(repo, repo.head, source["path"], source["start_line"], source["end_line"])
            if any(fresh[k] != source[k] for k in ("file_hash", "content_hash")):
                return "stale"
    except ReviewError:
        return "stale"
    if repo.current_head() != repo.head:
        raise ReviewError("HEAD moved during review validation; retry against one revision.")
    return "current"


def validate_manifest(value: object) -> tuple[Repository, dict]:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ReviewError("Quiz requires an exported schema_version 1 manifest.")
    for key in ("checkout", "repository_key", "source_revision"):
        if not isinstance(value.get(key), str):
            raise ReviewError(f"Manifest requires {key}.")
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value["source_revision"]):
        raise ReviewError("Manifest source_revision must be a full commit SHA.")
    repo = Repository(Path(value["checkout"]))
    if value["checkout"] != str(repo.root) or value["repository_key"] != repo.key:
        raise ReviewError("Manifest does not match this checkout identity.")
    if not reachable(repo, value["source_revision"]):
        raise ReviewError("Source revision is orphaned from current HEAD history.")
    target = value.get("target")
    context = value.get("context")
    if not isinstance(target, dict) or not isinstance(context, list) or len(context) > 8:
        raise ReviewError("Manifest requires a target and up to eight context blocks.")
    normalized = []
    for index, source in enumerate([target, *context]):
        if not isinstance(source, dict) or not all(k in source for k in ("path", "start_line", "end_line", "file_hash", "content_hash")):
            raise ReviewError("Incomplete target/context binding.")
        if type(source["start_line"]) is not int or type(source["end_line"]) is not int:
            raise ReviewError("Manifest line bounds must be integers.")
        fresh = block(repo, value["source_revision"], source["path"], source["start_line"], source["end_line"], target=index == 0)
        if any(source[k] != fresh[k] for k in ("file_hash", "content_hash")) or ("code" in source and source["code"] != fresh["code"]):
            raise ReviewError("Target/context hashes or exported code do not match the source revision.")
        normalized.append({k: v for k, v in fresh.items() if k != "code"})
    key = target.get("key")
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ReviewError("Manifest requires a target key of at most 200 characters.")
    normalized[0]["key"] = key
    normalized[1:] = sorted(normalized[1:], key=lambda c: (c["path"], c["start_line"], c["end_line"]))
    if len({(c["path"], c["start_line"], c["end_line"]) for c in normalized[1:]}) != len(context):
        raise ReviewError("Context blocks must be distinct.")
    manifest = {"schema_version": 1, "checkout": str(repo.root), "repository_key": repo.key,
                "source_revision": value["source_revision"], "target": normalized[0], "context": normalized[1:]}
    if currentness(repo, manifest) != "current":
        raise ReviewError("Target or context changed since export; export a fresh target.")
    return repo, manifest
