"""Transactional observation storage. JSONL remains an immutable import source."""
from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

from .store import Journal, SessionUnavailable, STALE_SECONDS, MAX_BATCH, digest

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (hash TEXT PRIMARY KEY, text TEXT NOT NULL, line_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, sequence INTEGER NOT NULL,
 kind TEXT NOT NULL, observed_at TEXT NOT NULL, monotonic_ms REAL NOT NULL,
 payload TEXT NOT NULL, fingerprint TEXT NOT NULL, path TEXT, UNIQUE(session_id, sequence));
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, id);
CREATE INDEX IF NOT EXISTS events_path_kind ON events(path, kind);
CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
 session_id TEXT NOT NULL, path TEXT NOT NULL, hash TEXT NOT NULL REFERENCES sources(hash),
 first_ms REAL NOT NULL, metadata TEXT NOT NULL, event_id INTEGER NOT NULL,
 PRIMARY KEY(session_id, path, hash));
CREATE INDEX IF NOT EXISTS snapshots_path ON snapshots(path, event_id);
CREATE TABLE IF NOT EXISTS documents (
 path TEXT NOT NULL, session_id TEXT NOT NULL, state TEXT NOT NULL, event_id INTEGER NOT NULL,
 PRIMARY KEY(path, session_id));
"""


class SQLMap(Mapping):
    def __init__(self, store, kind): self.store, self.kind = store, kind
    def __getitem__(self, key):
        db = self.store.db
        if self.kind == "keys":
            row = db.execute("SELECT fingerprint FROM events WHERE session_id=? AND sequence=?", key).fetchone()
        elif self.kind == "sessions":
            row = db.execute("SELECT state FROM sessions WHERE session_id=?", (key,)).fetchone()
        elif self.kind == "bindings":
            row = db.execute("SELECT first_ms FROM snapshots WHERE session_id=? AND path=? AND hash=?", key).fetchone()
        else:
            row = db.execute("SELECT metadata, sources.text FROM snapshots JOIN sources ON sources.hash=snapshots.hash WHERE path=? AND snapshots.hash=? ORDER BY event_id DESC LIMIT 1", key).fetchone()
        if row is None: raise KeyError(key)
        if self.kind == "versions": return {**json.loads(row[0]), "text": row[1]}
        return json.loads(row[0]) if self.kind == "sessions" else row[0]
    def __iter__(self):
        queries = {"keys": "SELECT session_id,sequence FROM events", "sessions": "SELECT sessions.session_id FROM sessions JOIN events ON events.session_id=sessions.session_id GROUP BY sessions.session_id ORDER BY MIN(events.id)", "bindings": "SELECT session_id,path,hash FROM snapshots", "versions": "SELECT DISTINCT path,hash FROM snapshots"}
        for row in self.store.db.execute(queries[self.kind]):
            yield row[0] if self.kind == "sessions" else tuple(row)
    def __len__(self): return sum(1 for _ in self)


class SQLiteStore:
    _check_live = Journal._check_live
    touch = Journal.touch
    _contact = Journal._contact
    append = Journal.append

    def __init__(self, directory: Path, workspace: Path, clock=time.monotonic, *, read_only=False):
        self.directory = directory.expanduser().resolve()
        self.workspace = workspace.expanduser().resolve(strict=True)
        if not self.workspace.is_dir() or self.directory == self.workspace or self.workspace in self.directory.parents:
            raise ValueError("Observer state must be outside an existing workspace directory")
        self.path = self.directory / "observations.sqlite3"
        self.read_only = read_only
        self.lock = threading.RLock()
        self.clock = clock
        self.active_sessions = set()
        self.contacts = {}
        self.write_failed = False
        self.metrics = {"batches": 0, "transactions": 0, "appended_events": 0, "duplicate_events": 0}
        if not read_only:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600); os.close(fd)
        try:
            self.db = sqlite3.connect(self.path.as_uri() + ("?mode=ro" if read_only else "?mode=rw"), uri=True, check_same_thread=False, isolation_level=None, timeout=5)
        except sqlite3.Error as exc: raise ValueError("Cannot open observation database: " + str(exc)) from exc
        try:
            if not read_only:
                self.db.execute("PRAGMA foreign_keys=ON")
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.execute("PRAGMA synchronous=FULL")
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1}: raise ValueError("Unsupported observation database version")
                self.db.executescript(SCHEMA)
                self.db.execute("PRAGMA user_version=1")
                self.db.execute("INSERT OR IGNORE INTO meta VALUES ('workspace', ?)", (str(self.workspace),))
            if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Unsupported observation database version")
            row = self.db.execute("SELECT value FROM meta WHERE key='workspace'").fetchone()
            if not row or row[0] != str(self.workspace): raise ValueError("This observer state belongs to another workspace")
            self.keys = SQLMap(self, "keys"); self.sessions = SQLMap(self, "sessions")
            self.versions = SQLMap(self, "versions"); self.bindings = SQLMap(self, "bindings")
            if not read_only: self.import_legacy()
        except sqlite3.Error as exc:
            self.db.close()
            raise ValueError("Invalid or unavailable observation database: " + str(exc)) from exc
        except Exception:
            self.db.close(); raise

    def close(self): self.db.close()

    @property
    def events(self): return self.read_events(source=True)

    def read_events(self, *, source=False, limit=None):
        with self.lock:
            if limit is None:
                rows = self.db.execute("SELECT session_id,sequence,kind,observed_at,monotonic_ms,payload FROM events ORDER BY id")
            else:
                rows = self.db.execute("SELECT session_id,sequence,kind,observed_at,monotonic_ms,payload FROM (SELECT * FROM events ORDER BY id DESC LIMIT ?) ORDER BY id", (limit,))
            result = []
            for sid, seq, kind, at, mono, payload in rows:
                payload = json.loads(payload)
                if source and kind == "snapshot": payload["text"] = self.db.execute("SELECT text FROM sources WHERE hash=?", (payload["content_hash"],)).fetchone()[0]
                result.append({"schema_version": 1, "session_id": sid, "sequence": seq, "workspace": str(self.workspace), "kind": kind, "observed_at": at, "monotonic_ms": mono, "payload": payload})
            return result

    def validator(self, session_id=None):
        staged = object.__new__(Journal)
        staged.workspace = self.workspace; staged.events = []
        staged.sessions = {session_id: self.sessions[session_id]} if session_id in self.sessions else {}
        staged.keys = ChainMap({}, self.keys); staged.versions = ChainMap({}, self.versions); staged.bindings = ChainMap({}, self.bindings)
        return staged

    def _write_event(self, event, state):
        payload = dict(event["payload"])
        if event["kind"] == "snapshot":
            text = payload.pop("text")
            self.db.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?)", (payload["content_hash"], text, payload["line_count"]))
        cursor = self.db.execute("INSERT INTO events(session_id,sequence,kind,observed_at,monotonic_ms,payload,fingerprint,path) VALUES (?,?,?,?,?,?,?,?)", (event["session_id"], event["sequence"], event["kind"], event["observed_at"], event["monotonic_ms"], json.dumps(payload, ensure_ascii=True), digest(json.dumps(event, sort_keys=True)), payload.get("path")))
        if event["kind"] == "snapshot":
            self.db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?) ON CONFLICT(session_id,path,hash) DO UPDATE SET metadata=excluded.metadata,event_id=excluded.event_id", (event["session_id"], payload["path"], payload["content_hash"], event["monotonic_ms"], json.dumps(payload), cursor.lastrowid))
        if event["kind"] == "document_state":
            self.db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?)", (payload["path"], event["session_id"], json.dumps(payload), cursor.lastrowid))
        self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?)", (event["session_id"], json.dumps(state)))

    def _commit(self): self.db.execute("COMMIT")

    def append_many(self, events):
        with self.lock:
            if self.read_only: raise ValueError("Observation database is read-only")
            if self.write_failed: raise OSError("Observer persistence previously failed")
            if not isinstance(events, list) or not 1 <= len(events) <= MAX_BATCH or any(not isinstance(e, dict) for e in events): raise ValueError("Batch requires 1–64 event objects")
            sid = events[0].get("session_id")
            if not isinstance(sid, str) or any(e.get("session_id") != sid for e in events): raise ValueError("Batch must belong to one session")
            staged = self.validator(sid); active = sid in self.active_sessions; duplicates = 0
            for event in events:
                seq = event.get("sequence")
                if type(seq) is not int or seq < 0: raise ValueError("Invalid sequence")
                old = staged.keys.get((sid, seq))
                if old:
                    if old != digest(json.dumps(event, sort_keys=True)): raise ValueError("Sequence reused with different content")
                    duplicates += 1; continue
                staged._validate(event)
                if event["kind"] == "session_start":
                    if sid in self.sessions: raise ValueError("Session ID already used")
                    active = True
                elif not active: raise SessionUnavailable("Receiver restarted/session ended; start a new recording session")
                elif sid in self.sessions: self._check_live(sid)
                staged._remember(event)
                if event["kind"] == "session_end": active = False
            if staged.events:
                try:
                    self.db.execute("BEGIN IMMEDIATE")
                    for event in staged.events: self._write_event(event, staged.sessions[sid])
                    self._commit()
                except (sqlite3.Error, OSError) as exc:
                    if self.db.in_transaction: self.db.execute("ROLLBACK")
                    self.write_failed = True
                    raise OSError("Observation transaction failed") from exc
                for event in staged.events:
                    if event["kind"] == "recording_gap": self.active_sessions.discard(event["payload"]["previous_session_id"])
                if active: self.active_sessions.add(sid); self._contact(sid)
                else: self.active_sessions.discard(sid)
                self.metrics["transactions"] += 1
            elif active: self._check_live(sid); self._contact(sid)
            self.metrics["batches"] += 1; self.metrics["appended_events"] += len(staged.events); self.metrics["duplicate_events"] += duplicates
            return {"appended": len(staged.events), "duplicates": duplicates}

    def import_legacy(self):
        legacy = self.directory / "events.jsonl"
        if not legacy.is_file(): return
        checksum = hashlib.sha256()
        with legacy.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""): checksum.update(chunk)
        fingerprint = checksum.hexdigest()
        old = self.db.execute("SELECT value FROM meta WHERE key='jsonl_sha256'").fetchone()
        if old:
            if old[0] != fingerprint: raise ValueError("Legacy journal changed after import; preserve both stores for inspection")
            return
        if self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]: raise ValueError("Cannot import a legacy journal into an existing observation database")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            with legacy.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.endswith("\n"): raise ValueError("Incomplete legacy observer journal; preserve it")
                    event = json.loads(line); sid = event.get("session_id")
                    old = self.keys.get((sid, event.get("sequence")))
                    if old:
                        if old != digest(json.dumps(event, sort_keys=True)): raise ValueError("Conflicting legacy event")
                        continue
                    validator = self.validator(sid); validator._validate(event); validator._remember(event)
                    self._write_event(event, validator.sessions[sid])
            with legacy.open("rb") as stream:
                verified = hashlib.file_digest(stream, "sha256").hexdigest()
            if verified != fingerprint: raise ValueError("Legacy journal changed during import")
            self.db.execute("INSERT INTO meta VALUES ('jsonl_sha256',?)", (fingerprint,))
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction: self.db.execute("ROLLBACK")
            raise

    def report(self, *, limit=None):
        with self.lock:
            # Legacy summary algorithm consumes SQL-backed events without retaining
            # source-bearing history on the writer. A normal UI uses overview().
            view = object.__new__(Journal)
            view.lock = self.lock
            view.events = self.read_events(source=False, limit=limit)
            view.sessions = dict(self.sessions); view.contacts = self.contacts; view.active_sessions = self.active_sessions
            view.clock = self.clock; view.workspace = self.workspace; view.metrics = self.metrics
            report = view.report()
            report["limits"] = ["Raw ranges remain bound to exact source hashes; current-version derivation is a separate overview.", "All reported visible eligible plain-text panes can contribute in collector 0.3; older active-editor records retain their original scope.", "Window focus and API ranges do not prove reading, physical occlusion, authorship or understanding.", "Duplicate pane intervals are unioned within each version/session; raw display_ms does not measure every line equally.", "Source text is excluded from metadata export. Paths, hashes and diagnostic metadata remain local and may be sensitive."]
            report["event_counts"] = dict(self.db.execute("SELECT kind,COUNT(*) FROM events GROUP BY kind"))
            report["storage"] = {"kind": "sqlite", "schema_version": 1, "events": self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], "imported_jsonl_sha256": (self.db.execute("SELECT value FROM meta WHERE key='jsonl_sha256'").fetchone() or [None])[0]}
            return report

    def overview(self, dwell_ms=1000):
        from .visibility import overview
        return overview(self, dwell_ms)
