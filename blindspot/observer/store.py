from __future__ import annotations

from collections import ChainMap
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import threading
import time
import uuid

MAX_TEXT = 256 * 1024
KINDS = {"session_start", "session_end", "state", "window_state", "snapshot", "visibility", "interaction", "file_event", "diagnostic", "marker", "recording_gap", "document_state", "workspace_context", "visibility_policy"}
MAX_BATCH = 64
STALE_SECONDS = 7


class SessionUnavailable(ValueError):
    """The client must establish a fresh session without filling the gap."""
    def __init__(self, message, **diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid relative source path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {".", "..", ".git"} for p in value.split("/")):
        raise ValueError("Source path must stay inside the workspace")
    return value


class Journal:
    """Single-process append journal for the pilot; not the Phase 2 database."""

    def __init__(self, directory: Path, workspace: Path, clock=time.monotonic):
        self.directory = directory.expanduser().resolve()
        self.workspace = workspace.expanduser().resolve(strict=True)
        if not self.workspace.is_dir():
            raise ValueError("Workspace must be a directory")
        if self.directory == self.workspace or self.workspace in self.directory.parents:
            raise ValueError("Observer state must be outside the observed workspace")
        self.path = self.directory / "events.jsonl"
        self.lock = threading.RLock()
        self.events: list[dict] = []
        self.keys: dict[tuple[str, int], str] = {}
        self.versions: dict[tuple[str, str], dict] = {}
        self.bindings: dict[tuple[str, str, str], float] = {}
        self.sessions: dict[str, dict] = {}
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            with self.path.open(encoding="utf-8") as source:
                for line in source:
                    if not line.endswith("\n"):
                        raise ValueError("Incomplete observer journal; preserve it and use a new state directory")
                    event = json.loads(line)
                    self._validate(event)
                    self._remember(event)
            if any(e["workspace"] != str(self.workspace) for e in self.events):
                raise ValueError("This observer state belongs to another workspace")
        # A process restart is a gap. A prior session must explicitly start anew.
        self.active_sessions: set[str] = set()
        self.clock = clock
        self.contacts: dict[str, dict] = {}
        self.write_failed = False
        self.metrics = {"batches": 0, "fsyncs": 0, "appended_events": 0, "duplicate_events": 0}

    def _validate(self, event: dict) -> None:
        if not isinstance(event, dict) or set(event) != {"schema_version", "session_id", "sequence", "workspace", "observed_at", "monotonic_ms", "kind", "payload"}:
            raise ValueError("Invalid observation envelope")
        if type(event["schema_version"]) is not int or event["schema_version"] != 1 or event["workspace"] != str(self.workspace):
            raise ValueError("Wrong protocol version or workspace")
        try:
            uuid.UUID(event["session_id"])
            stamp = datetime.fromisoformat(event["observed_at"])
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid session ID or timestamp") from None
        if stamp.tzinfo is None:
            raise ValueError("Timestamp requires a timezone")
        sequence, clock = event["sequence"], event["monotonic_ms"]
        if type(sequence) is not int or sequence < 0 or type(clock) not in {int, float} or not math.isfinite(clock) or clock < 0:
            raise ValueError("Invalid sequence or monotonic clock")
        kind, payload = event["kind"], event["payload"]
        if kind not in KINDS or not isinstance(payload, dict):
            raise ValueError("Unknown event kind or payload")
        if kind == "session_start":
            if sequence != 0 or payload.get("mode") not in {"active-editor-reported-ranges", "visible-editors-reported-ranges"}:
                raise ValueError("Session must start at sequence zero with a declared mode")
        else:
            session = self.sessions.get(event["session_id"])
            if not session or sequence != session["sequence"] + 1 or clock < session["clock"]:
                raise ValueError("Missing/out-of-order event or clock regression")
        if "path" in payload:
            relative_path(payload["path"])
        if kind == "snapshot":
            relative_path(payload.get("path"))
            text = payload.get("text")
            if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT or "\x00" in text:
                raise ValueError("Snapshot must be bounded UTF-8 text")
            if payload.get("content_hash") != digest(text) or payload.get("line_count") != len(text.split("\n")):
                raise ValueError("Snapshot hash/line count mismatch")
            if payload.get("origin") not in {"document", "disk"}:
                raise ValueError("Snapshot origin must be document or disk")
        if kind == "state" and payload.get("status") not in {"recording", "paused"}:
            raise ValueError("Unknown recording state")
        if kind == "document_state":
            relative_path(payload.get("path"))
            if type(payload.get("is_open")) is not bool or type(payload.get("dirty")) is not bool:
                raise ValueError("Invalid document state")
            if type(payload.get("supported", True)) is not bool: raise ValueError("Invalid document support state")
            if payload["is_open"] and payload.get("supported", True) and (event["session_id"], payload["path"], payload.get("content_hash")) not in self.bindings:
                raise ValueError("Open document requires a matching snapshot in its session")
            if payload.get("supported") is False and payload.get("content_hash") is not None:
                raise ValueError("Unsupported documents cannot claim a current hash")
        if kind == "workspace_context":
            if not isinstance(payload.get("open_tabs"), list) or len(payload["open_tabs"]) > 500:
                raise ValueError("Invalid tab inventory")
            for path in payload["open_tabs"]: relative_path(path)
        if kind == "visibility_policy" and type(payload.get("excluded")) is not bool:
            raise ValueError("Invalid visibility exclusion")
        if kind == "recording_gap":
            try:
                uuid.UUID(payload["previous_session_id"])
                for key in ("detected_at", "recovered_at"):
                    if datetime.fromisoformat(payload[key]).tzinfo is None:
                        raise ValueError("Gap times require a timezone")
                if payload.get("last_acknowledged_at") is not None and datetime.fromisoformat(payload["last_acknowledged_at"]).tzinfo is None:
                    raise ValueError("Acknowledgement time requires a timezone")
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ValueError("Invalid recording-gap metadata") from None
            if payload["previous_session_id"] == event["session_id"] or type(payload.get("unacknowledged_events")) is not int or payload["unacknowledged_events"] < 0 or payload.get("duration_uncertain") is not True:
                raise ValueError("Recovery requires a new session and qualified delivery uncertainty")
        if kind == "visibility":
            relative_path(payload.get("path"))
            version = self.versions.get((payload["path"], payload.get("content_hash")))
            if not version:
                raise ValueError("Visibility requires an earlier matching snapshot")
            if self.sessions[event["session_id"]]["status"] != "recording":
                raise ValueError("Visibility requires a recording session")
            duration, start, end = payload.get("duration_ms"), payload.get("start_ms"), payload.get("end_ms")
            if any(type(v) not in {int, float} or not math.isfinite(v) for v in (duration, start, end)) or not 0 < duration <= 2500 or start < 0 or end != clock or abs(end - start - duration) > 0.001:
                raise ValueError("Invalid display interval")
            session = self.sessions[event["session_id"]]
            pane = payload.get("pane_id", "legacy")
            if not isinstance(pane, str) or not 1 <= len(pane) <= 100:
                raise ValueError("Invalid pane identity")
            if "pane_id" in payload and (payload.get("exposure") not in {"reported-visible", "active-fallback"} or type(payload.get("active")) is not bool):
                raise ValueError("Pane evidence requires qualified exposure and activity")
            if start < session.get("visibility_ends", {}).get(pane, 0) or start < session["recording_since"] or payload.get("focused") is not True:
                raise ValueError("Overlapping, paused, or unfocused display interval")
            bound = self.bindings.get((event["session_id"], payload["path"], payload.get("content_hash")))
            if bound is None or start < bound:
                raise ValueError("Display interval must follow its session's source snapshot")
            if payload.get("focus_scope") != "window" or payload.get("editor_focus") != "unverified":
                raise ValueError("Pilot evidence must qualify window focus and unverified editor focus")
            ranges = payload.get("ranges")
            if not isinstance(ranges, list) or not 1 <= len(ranges) <= 100:
                raise ValueError("Invalid reported ranges")
            for pair in ranges:
                if not isinstance(pair, list) or len(pair) != 2 or any(type(v) is not int for v in pair) or not 1 <= pair[0] <= pair[1] <= version["line_count"]:
                    raise ValueError("Reported range lies outside its source version")

    def _remember(self, event: dict) -> None:
        self.events.append(event)
        self.keys[(event["session_id"], event["sequence"])] = digest(json.dumps(event, sort_keys=True))
        payload, kind = event["payload"], event["kind"]
        if kind == "session_start":
            self.sessions[event["session_id"]] = {"sequence": 0, "clock": event["monotonic_ms"], "status": "recording", "visibility_end": 0, "recording_since": event["monotonic_ms"], "heartbeat_enabled": payload.get("heartbeat_interval_ms") == 2000}
        session = self.sessions[event["session_id"]]
        session.update(sequence=event["sequence"], clock=event["monotonic_ms"])
        if kind == "state":
            session["status"] = payload["status"]
            session["recording_since"] = event["monotonic_ms"]
        if kind == "session_end":
            session["status"] = "ended"
        if kind == "snapshot":
            self.versions[(payload["path"], payload["content_hash"])] = payload
            self.bindings.setdefault((event["session_id"], payload["path"], payload["content_hash"]), event["monotonic_ms"])
        if kind == "visibility":
            session["visibility_end"] = payload["end_ms"]
            session["visibility_ends"] = {**session.get("visibility_ends", {}), payload.get("pane_id", "legacy"): payload["end_ms"]}

    def append(self, event: dict) -> bool:
        return self.append_many([event])["appended"] == 1

    def _check_live(self, session_id: str) -> None:
        if self.write_failed:
            raise OSError("Observer persistence failed; restart after resolving storage error")
        if session_id not in self.active_sessions:
            raise SessionUnavailable("Receiver restarted/session ended; start a new recording session", reason="session_not_active")
        contact = self.contacts.get(session_id)
        if self.sessions[session_id].get("heartbeat_enabled") and (not contact or self.clock() - contact["clock"] > STALE_SECONDS):
            raise SessionUnavailable("Session heartbeat expired; start a new recording session", reason="heartbeat_expired", contact_age_ms=(self.clock()-contact["clock"])*1000 if contact else None, last_contact_at=contact["at"] if contact else None, stale_after_ms=STALE_SECONDS*1000)

    def touch(self, session_id: str) -> None:
        with self.lock:
            self._check_live(session_id)
            self._contact(session_id)

    def _contact(self, session_id: str) -> None:
        self.contacts[session_id] = {"clock": self.clock(), "at": datetime.now(timezone.utc).isoformat()}

    def append_many(self, events: list[dict]) -> dict:
        """Validate the whole batch before one append/fsync; retain JSONL replay."""
        with self.lock:
            if self.write_failed:
                raise OSError("Observer persistence previously failed")
            if not isinstance(events, list) or not 1 <= len(events) <= MAX_BATCH or any(not isinstance(e, dict) for e in events):
                raise ValueError("Batch requires 1–64 event objects")
            session_id = events[0].get("session_id")
            if not isinstance(session_id, str) or any(e.get("session_id") != session_id for e in events):
                raise ValueError("Batch must belong to one session")
            staged = object.__new__(Journal)
            staged.workspace = self.workspace
            staged.events = []
            staged.sessions = {session_id: dict(self.sessions[session_id])} if session_id in self.sessions else {}
            staged.keys = ChainMap({}, self.keys)
            staged.versions = ChainMap({}, self.versions)
            staged.bindings = ChainMap({}, self.bindings)
            active = session_id in self.active_sessions
            duplicates = 0
            for event in events:
                sequence = event.get("sequence")
                if type(sequence) is not int or sequence < 0:
                    raise ValueError("Invalid sequence")
                key = (session_id, sequence)
                previous = staged.keys.get(key)
                if previous:
                    if previous != digest(json.dumps(event, sort_keys=True)):
                        raise ValueError("Sequence reused with different content")
                    duplicates += 1
                    continue
                staged._validate(event)
                if event["kind"] == "session_start":
                    if session_id in self.sessions:
                        raise ValueError("Session ID already used")
                    active = True
                elif not active:
                    raise SessionUnavailable("Receiver restarted/session ended; start a new recording session")
                elif session_id in self.sessions:
                    self._check_live(session_id)
                staged._remember(event)
                if event["kind"] == "session_end":
                    active = False
            fresh = staged.events
            if fresh:
                body = "".join(json.dumps(e, ensure_ascii=True, separators=(",", ":")) + "\n" for e in fresh)
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as target:
                        target.write(body)
                        target.flush()
                        os.fsync(target.fileno())
                except OSError:
                    self.write_failed = True
                    raise
                for event in fresh:
                    self._remember(event)
                    if event["kind"] == "recording_gap":
                        self.active_sessions.discard(event["payload"]["previous_session_id"])
                if active:
                    self.active_sessions.add(session_id)
                    self._contact(session_id)
                else:
                    self.active_sessions.discard(session_id)
            elif active:
                self._check_live(session_id)
                self._contact(session_id)
            self.metrics["batches"] += 1
            self.metrics["fsyncs"] += bool(fresh)
            self.metrics["appended_events"] += len(fresh)
            self.metrics["duplicate_events"] += duplicates
            return {"appended": len(fresh), "duplicates": duplicates}

    def report(self) -> dict:
        with self.lock:
            counts: dict[str, int] = {}
            files: dict[tuple[str, str], dict] = {}
            intervals = {}
            for event in self.events:
                kind, payload = event["kind"], event["payload"]
                counts[kind] = counts.get(kind, 0) + 1
                if kind == "visibility":
                    key = (payload["path"], payload["content_hash"])
                    item = files.setdefault(key, {"path": key[0], "content_hash": key[1], "display_ms": 0, "ranges": []})
                    intervals.setdefault((key, event["session_id"]), []).append((payload["start_ms"], payload["end_ms"]))
                    item["ranges"].extend(payload["ranges"])
            for (key, _), spans in intervals.items():
                last = None
                for start, end in sorted(spans):
                    files[key]["display_ms"] += end-start if last is None or start>last else max(0, end-last)
                    last = end if last is None else max(last, end)
            for item in files.values():
                merged: list[list[int]] = []
                for start, end in sorted(item["ranges"]):
                    if merged and start <= merged[-1][1] + 1:
                        merged[-1][1] = max(merged[-1][1], end)
                    else:
                        merged.append([start, end])
                item["ranges"] = merged
            sessions = []
            for key, value in self.sessions.items():
                contact = self.contacts.get(key)
                connection = "ended" if value["status"] == "ended" else "interrupted" if key not in self.active_sessions else "unmonitored" if not value.get("heartbeat_enabled") else "connected" if contact and self.clock() - contact["clock"] <= STALE_SECONDS else "stale"
                sessions.append({"session_id": key, **value, "connection_state": connection, "receiver_connected": connection == "connected", "last_contact_at": contact["at"] if contact else None})
            return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "workspace": str(self.workspace), "event_counts": counts,
                    "sessions": sessions, "ingestion_metrics": dict(self.metrics),
                    "recording_gaps": [{"session_id": e["session_id"], **e["payload"]} for e in self.events if e["kind"] == "recording_gap"],
                    "displayed_versions": list(files.values()),
                    "events": [{**e, "payload": {k: v for k, v in e["payload"].items() if k != "text"}} for e in self.events],
                    "limits": ["Pilot records active-editor reported line ranges in a focused VS Code window, not proof of reading or exact visible characters.",
                               "Keyboard focus within VS Code is unverified: the terminal/sidebar may be focused while activeTextEditor is retained.",
                               "Folds, horizontal clipping, diff/split/remote editors and agent attribution are not validated.",
                               "No whole-codebase coverage percentage. Unrecorded intervals and earlier history are unknown.",
                               "Version ranges are never carried across different content hashes."]}
