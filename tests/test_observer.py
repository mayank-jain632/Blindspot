from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

from blindspot.observer.server import make_server
from blindspot.observer.store import Journal, SessionUnavailable, digest


class ObserverTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.state = self.base / "state"
        self.store = Journal(self.state, self.workspace)
        self.session = str(uuid.uuid4())
        self.sequence = 0

    def tearDown(self):
        self.temp.cleanup()

    def event(self, kind, payload=None, clock=0):
        event = {"schema_version": 1, "session_id": self.session, "sequence": self.sequence,
                 "workspace": str(self.workspace), "observed_at": "2026-10-03T10:00:00+00:00",
                 "monotonic_ms": clock, "kind": kind, "payload": payload or {}}
        self.sequence += 1
        return event

    def start(self):
        self.store.append(self.event("session_start", {"mode": "active-editor-reported-ranges"}))

    def snapshot(self, text="a\nb\nc", clock=0):
        self.store.append(self.event("snapshot", {"path": "a.py", "text": text, "content_hash": digest(text), "line_count": len(text.split("\n")), "origin": "document"}, clock))

    def visible(self, text="a\nb\nc", start=0, end=1000, ranges=None):
        return self.event("visibility", {"path": "a.py", "content_hash": digest(text), "ranges": ranges or [[1, 2]], "start_ms": start, "end_ms": end, "duration_ms": end-start, "focused": True, "focus_scope": "window", "editor_focus": "unverified"}, end)

    def test_visibility_cannot_predate_its_source_snapshot(self):
        self.start(); self.snapshot(clock=500)
        with self.assertRaisesRegex(ValueError, "follow its session"):
            self.store.append(self.visible(start=0, end=1000))

    def test_idempotent_retry_and_conflicting_sequence(self):
        event = self.event("session_start", {"mode": "active-editor-reported-ranges"})
        self.assertTrue(self.store.append(event))
        self.assertFalse(self.store.append(copy.deepcopy(event)))
        event["payload"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "different content"):
            self.store.append(event)
        self.assertEqual(len(self.store.events), 1)

    def test_missing_sequence_and_unknown_version_rejected(self):
        self.start()
        event = self.visible()
        with self.assertRaisesRegex(ValueError, "earlier matching snapshot"):
            self.store.append(event)
        event["sequence"] = 3
        with self.assertRaisesRegex(ValueError, "out-of-order"):
            self.store.append(event)

    def test_version_bound_deduplicated_ranges_and_source_free_report(self):
        self.start(); self.snapshot()
        self.store.append(self.visible())
        self.store.append(self.visible(start=1000, end=1500, ranges=[[2, 3]]))
        self.snapshot("new\nb\nc", 1500)
        self.store.append(self.visible("new\nb\nc", start=1500, end=2000))
        report = self.store.report()
        self.assertEqual(len(report["displayed_versions"]), 2)
        self.assertEqual(report["displayed_versions"][0]["ranges"], [[1, 3]])
        self.assertEqual(report["displayed_versions"][0]["display_ms"], 1500)
        self.assertTrue(all("text" not in e["payload"] for e in report["events"]))

    def test_paused_and_overlapping_intervals_rejected(self):
        self.start(); self.snapshot(); self.store.append(self.visible())
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.store.append(self.visible(start=500, end=1500))
        self.sequence -= 1
        self.store.append(self.event("state", {"status": "paused"}, 1500))
        with self.assertRaisesRegex(ValueError, "recording session"):
            self.store.append(self.visible(start=1500, end=2000))

    def test_out_of_bounds_unfocused_and_long_duration_rejected(self):
        for mode in ["bounds", "focus", "duration"]:
            with self.subTest(mode=mode):
                journal = Journal(self.base / mode, self.workspace)
                journal.append({**self.event("session_start", {"mode": "active-editor-reported-ranges"}), "sequence": 0})
                self.sequence = 1
                old = self.store; self.store = journal; self.snapshot()
                event = self.visible()
                if mode == "bounds": event["payload"]["ranges"] = [[1, 4]]
                if mode == "focus": event["payload"]["focused"] = False
                if mode == "duration": event["payload"].update(end_ms=10000, duration_ms=10000); event["monotonic_ms"] = 10000
                with self.assertRaises(ValueError): journal.append(event)
                self.store = old

    def test_snapshot_hash_and_traversal_rejected(self):
        self.start()
        for name in ["../outside.py", "/tmp/outside.py", ".git/config", "a/../b.py"]:
            event = self.event("snapshot", {"path": name, "text": "a", "content_hash": digest("a"), "line_count": 1, "origin": "disk"})
            with self.assertRaises(ValueError): self.store.append(event)
            self.sequence -= 1
        event["payload"]["path"] = "a.py"; event["payload"]["content_hash"] = "wrong"
        with self.assertRaisesRegex(ValueError, "hash"): self.store.append(event)

    def test_state_outside_workspace_and_restart_is_a_gap(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            Journal(self.workspace / ".blindspot", self.workspace)
        self.assertFalse((self.workspace / ".blindspot").exists())
        self.start(); self.snapshot(); self.store.append(self.visible())
        restarted = Journal(self.state, self.workspace)
        self.assertEqual(len(restarted.report()["displayed_versions"]), 1)
        with self.assertRaisesRegex(ValueError, "restarted"):
            restarted.append(self.event("marker", {"label": "after restart"}, 1000))
        self.assertFalse(restarted.report()["sessions"][0]["receiver_connected"])

    def test_incomplete_journal_preserved_and_rejected(self):
        self.start()
        with self.store.path.open("ab") as target: target.write(b'{"partial":')
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            Journal(self.state, self.workspace)
        self.assertEqual(before, self.store.path.read_bytes())

    def test_batch_validation_is_atomic_and_retry_has_one_disk_flush(self):
        start = self.event("session_start", {"mode": "active-editor-reported-ranges"})
        source = self.event("snapshot", {"path": "a.py", "text": "a\nb\nc", "content_hash": digest("a\nb\nc"), "line_count": 3, "origin": "document"})
        invalid = self.visible(ranges=[[1, 4]])
        with self.assertRaises(ValueError):
            self.store.append_many([start, source, invalid])
        self.assertEqual(self.store.events, [])
        self.assertEqual(self.store.sessions, {})
        self.assertEqual(self.store.versions, {})
        self.assertFalse(self.store.path.exists())
        invalid["payload"]["ranges"] = [[1, 2]]
        batch = [start, source, invalid]
        self.assertEqual(self.store.append_many(batch), {"appended": 3, "duplicates": 0})
        self.assertEqual(self.store.append_many(copy.deepcopy(batch)), {"appended": 0, "duplicates": 3})
        end = self.event("session_end", {}, 1000)
        self.assertEqual(self.store.append_many([invalid, end]), {"appended": 1, "duplicates": 1})
        self.assertEqual(self.store.metrics, {"batches": 3, "fsyncs": 2, "appended_events": 4, "duplicate_events": 4})
        self.assertEqual(Journal(self.state, self.workspace).events, [*batch, end])

    def test_heartbeat_expires_without_new_events_and_recovery_marks_gap(self):
        clock = [0]
        self.store = Journal(self.state, self.workspace, clock=lambda: clock[0])
        self.store.append(self.event("session_start", {"mode": "active-editor-reported-ranges", "heartbeat_interval_ms": 2000}))
        self.store.append(self.event("state", {"status": "paused"}))
        before = self.store.path.read_bytes()
        clock[0] = 6; self.store.touch(self.session)
        self.assertEqual(self.store.path.read_bytes(), before)
        clock[0] = 12
        self.assertEqual(self.store.report()["sessions"][0]["connection_state"], "connected")
        clock[0] = 14
        self.assertEqual(self.store.report()["sessions"][0]["connection_state"], "stale")
        with self.assertRaises(SessionUnavailable): self.store.touch(self.session)
        with self.assertRaises(SessionUnavailable): self.store.append(self.event("marker", {"label": "late"}))
        old = self.session; self.session = str(uuid.uuid4()); self.sequence = 0
        self.store.append_many([
            self.event("session_start", {"mode": "active-editor-reported-ranges", "heartbeat_interval_ms": 2000}),
            self.event("recording_gap", {"previous_session_id": old, "reason": "session_unavailable", "detected_at": "2026-10-03T10:00:00+00:00", "recovered_at": "2026-10-03T10:00:14+00:00", "last_acknowledged_at": None, "unacknowledged_events": 1, "duration_uncertain": True}),
            self.event("state", {"status": "paused"}),
        ])
        report = self.store.report()
        self.assertEqual([s["connection_state"] for s in report["sessions"]], ["interrupted", "connected"])
        self.assertEqual(report["sessions"][1]["status"], "paused")
        self.assertEqual(len(report["recording_gaps"]), 1)
        self.assertEqual(report["displayed_versions"], [])

    def test_disk_failure_stops_further_ingestion(self):
        self.start()
        with patch("blindspot.observer.store.os.fsync", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError): self.store.append(self.event("marker", {"label": "uncertain"}))
        self.assertTrue(self.store.write_failed)
        self.assertEqual(len(self.store.events), 1)
        with self.assertRaises(OSError): self.store.touch(self.session)
        with self.assertRaises(OSError): self.store.append(self.event("marker", {"label": "blocked"}))

    def test_http_loopback_auth_origin_and_payload_limits(self):
        token = "secret" * 8
        server = make_server(self.store, token, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        def call(path="/api/report", headers=None, data=None):
            return urlopen(Request(endpoint + path, headers=headers or {}, data=data), timeout=3)
        try:
            with self.assertRaises(HTTPError) as error: call()
            self.assertEqual(error.exception.code, 401)
            with call("/") as page:
                self.assertIn("HttpOnly", page.headers["Set-Cookie"])
                cookie = page.headers["Set-Cookie"].split(";", 1)[0]
                self.assertIn(b"Local visibility prototype", page.read())
            with call(headers={"Cookie": cookie}) as response:
                self.assertEqual(json.load(response)["event_counts"], {})
            for headers in [{"Host": "evil.example"}, {"Origin": "https://evil.example"}]:
                headers["Authorization"] = "Bearer " + token
                with self.assertRaises(HTTPError) as error: call(headers=headers)
                self.assertEqual(error.exception.code, 403)
            event = self.event("session_start", {"mode": "active-editor-reported-ranges"})
            event["payload"]["heartbeat_interval_ms"] = 2000
            headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
            with call("/api/health", headers) as response:
                health = json.load(response)
                self.assertTrue(health["capabilities"]["batch_events"])
                headers["X-Blindspot-Receiver"] = health["receiver_id"]
            with call("/api/events", headers, json.dumps(event).encode()) as response:
                self.assertTrue(json.load(response)["accepted"])
            with call("/api/events", headers, json.dumps(event).encode()) as response:
                self.assertTrue(json.load(response)["duplicate"])
            batch = {"schema_version": 1, "events": [self.event("marker", {"label": "batched"})]}
            with call("/api/events/batch", headers, json.dumps(batch).encode()) as response:
                self.assertEqual(json.load(response)["appended"], 1)
            before = self.store.path.read_bytes()
            with call("/api/events/batch", headers, json.dumps(batch).encode()) as response:
                self.assertEqual(json.load(response)["duplicates"], 1)
            heartbeat = {"schema_version": 1, "workspace": str(self.workspace), "session_id": self.session}
            with call("/api/heartbeat", headers, json.dumps(heartbeat).encode()) as response:
                self.assertTrue(json.load(response)["accepted"])
            self.assertEqual(self.store.path.read_bytes(), before)
            wrong_epoch = {**headers, "X-Blindspot-Receiver": "previous-receiver"}
            with self.assertRaises(HTTPError) as error: call("/api/events/batch", wrong_epoch, json.dumps(batch).encode())
            self.assertEqual(error.exception.code, 409)
            self.assertEqual(json.load(error.exception)["code"], "receiver_changed")
            self.assertEqual(self.store.path.read_bytes(), before)
            headers["Content-Length"] = str(3 * 1024 * 1024)
            with self.assertRaises(HTTPError) as error: call("/api/events", headers, b"{}")
            self.assertEqual(error.exception.code, 413)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
