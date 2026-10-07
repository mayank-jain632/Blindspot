from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.store import Journal, digest, SessionUnavailable
from blindspot.observer.visibility import derive, unique_line_mapping, current_source


class SQLiteObserverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.workspace = self.root / "workspace"; self.workspace.mkdir()
        subprocess.run(["git", "init", str(self.workspace)], check=True, capture_output=True)
        self.state = self.root / "state"; self.store = SQLiteStore(self.state, self.workspace)
        self.sid = str(uuid.uuid4()); self.seq = 0
    def tearDown(self): self.store.close(); self.tmp.cleanup()
    def event(self, kind, payload=None, clock=0):
        event = {"schema_version": 1, "workspace": str(self.workspace), "session_id": self.sid, "sequence": self.seq, "observed_at": "2026-10-04T10:00:00+00:00", "monotonic_ms": clock, "kind": kind, "payload": payload or {}}
        self.seq += 1; return event
    def start(self): return self.event("session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000})
    def snapshot(self, text="one\ntwo\nthree", path="a.py"):
        return self.event("snapshot", {"path": path, "text": text, "content_hash": digest(text), "line_count": len(text.split("\n")), "origin": "document"})
    def visible(self, pane="left", start=0, end=1000):
        return self.event("visibility", {"path": "a.py", "content_hash": digest("one\ntwo\nthree"), "ranges": [[1, 2]], "start_ms": start, "end_ms": end, "duration_ms": end-start, "focused": True, "focus_scope": "window", "editor_focus": "unverified", "pane_id": pane, "active": pane=="left", "exposure": "reported-visible"}, end)

    def test_batch_rollback_duplicate_and_content_deduplication(self):
        batch = [self.start(), self.snapshot(), self.visible()]
        bad = copy.deepcopy(batch); bad[-1]["payload"]["ranges"] = [[1, 9]]
        with self.assertRaises(ValueError): self.store.append_many(bad)
        self.assertEqual(self.store.events, [])
        self.assertEqual(self.store.append_many(batch), {"appended": 3, "duplicates": 0})
        self.assertEqual(self.store.append_many(copy.deepcopy(batch)), {"appended": 0, "duplicates": 3})
        self.assertEqual(self.store.metrics["transactions"], 1)
        conflict = copy.deepcopy(batch[0]); conflict["payload"]["extra"] = 1
        with self.assertRaises(ValueError): self.store.append(conflict)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 1)
        self.assertTrue(all("text" not in e["payload"] for e in self.store.report()["events"]))

    def test_commit_failure_rolls_back_and_refuses_further_writes(self):
        with patch.object(self.store, "_commit", side_effect=sqlite3.OperationalError("disk failure")):
            with self.assertRaises(OSError): self.store.append_many([self.start(), self.snapshot()])
        self.assertEqual(self.store.events, []); self.assertFalse(self.store.db.in_transaction)
        self.assertTrue(self.store.write_failed)
        with self.assertRaises(OSError): self.store.append(self.event("marker"))

    def test_reopen_preserves_records_and_requires_fresh_session(self):
        self.store.append_many([self.start(), self.snapshot(), self.visible()]); before = self.store.events
        self.store.close(); self.store = SQLiteStore(self.state, self.workspace)
        self.assertEqual(self.store.events, before)
        self.assertEqual(self.store.report()["sessions"][0]["connection_state"], "interrupted")
        with self.assertRaises(SessionUnavailable): self.store.append(self.event("marker", {}, 1000))

    def test_legacy_import_is_atomic_idempotent_and_preserves_original(self):
        other = self.root / "legacy"
        legacy = Journal(other, self.workspace)
        legacy.append_many([self.start(), self.snapshot(), self.visible()]); before = legacy.path.read_bytes()
        imported = SQLiteStore(other, self.workspace)
        try:
            self.assertEqual(imported.events, legacy.events)
            imported.import_legacy(); self.assertEqual(len(imported.events), 3)
            self.assertEqual(legacy.path.read_bytes(), before)
            self.assertEqual(imported.report()["storage"]["imported_jsonl_sha256"], hashlib.sha256(before).hexdigest())
        finally: imported.close()
        broken = self.root / "broken"; broken.mkdir(); (broken / "events.jsonl").write_bytes(before+b'{"partial":')
        with self.assertRaises(ValueError): SQLiteStore(broken, self.workspace)
        db = sqlite3.connect(broken / "observations.sqlite3")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0); db.close()
        self.assertEqual((broken / "events.jsonl").read_bytes(), before+b'{"partial":')

    def test_multi_pane_overlap_is_allowed_but_same_pane_overlap_rejected(self):
        self.store.append_many([self.start(), self.snapshot(), self.visible("left"), self.visible("right")])
        with self.assertRaises(ValueError): self.store.append(self.visible("left", 500, 1500))

    def test_process_crash_rolls_back_uncommitted_transaction(self):
        self.store.append(self.start())
        script = """import os,sys,json
from pathlib import Path
from blindspot.observer.sqlite_store import SQLiteStore
config=json.loads(sys.stdin.read()); s=SQLiteStore(Path(config['state']),Path(config['workspace']))
s.db.execute('BEGIN IMMEDIATE'); s.db.execute("INSERT INTO sources VALUES ('uncommitted','text',1)"); os._exit(17)
"""
        result = subprocess.run([sys.executable, "-B", "-c", script], input=json.dumps({"state": str(self.state), "workspace": str(self.workspace)}), text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertIsNone(self.store.db.execute("SELECT text FROM sources WHERE hash='uncommitted'").fetchone())

    def test_current_dirty_overlay_then_saved_source_and_stale_uncertainty(self):
        (self.workspace / "a.py").write_text("saved\nsource")
        self.store.append_many([self.start(), self.snapshot(), self.visible(), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "content_hash": digest("one\ntwo\nthree")}, 1000)])
        overview = self.store.overview(); file = overview["files"][0]
        self.assertEqual(file["origin"], "unsaved document"); self.assertEqual(file["dwell_lines"], 2)
        self.store.append(self.event("state", {"status": "paused"}, 1000))
        file = self.store.overview()["files"][0]
        self.assertTrue(file["current_uncertain"]); self.assertEqual(file["reported_lines"], 0)
        self.store.append(self.event("document_state", {"path": "a.py", "is_open": False, "dirty": False}, 1000))
        self.assertEqual(self.store.overview()["files"][0]["origin"], "disk")

    def test_unknown_is_not_never_viewed_and_tab_alone_has_no_credit(self):
        (self.workspace / "a.py").write_text("one\ntwo\nthree")
        self.store.append_many([self.start(), self.event("workspace_context", {"open_tabs": ["a.py"]})])
        file = self.store.overview()["files"][0]
        self.assertTrue(file["open_tab"]); self.assertEqual(file["unknown_lines"], 3); self.assertEqual(file["reported_lines"], 0)

    def test_current_source_hash_guard_and_inventory_exclusions(self):
        (self.workspace / "a.py").write_text("one\ntwo\nthree")
        (self.workspace / ".env").write_text("secret")
        (self.workspace / "link.py").symlink_to(self.workspace / "a.py")
        self.store.append_many([self.start(), self.snapshot(), self.visible()])
        self.assertEqual([f["path"] for f in self.store.overview()["files"]], ["a.py"])
        self.assertEqual(current_source(self.store, "a.py", digest("one\ntwo\nthree"))["text"], "one\ntwo\nthree")
        (self.workspace / "a.py").write_text("changed")
        with self.assertRaises(ValueError): current_source(self.store, "a.py", digest("one\ntwo\nthree"))
        with self.assertRaises(ValueError): current_source(self.store, "../outside.py", digest("changed"))
        (self.workspace / "a.py").unlink()
        self.assertEqual(self.store.overview()["files"], [])

    def test_uncertain_dirty_documents_are_excluded_from_totals(self):
        (self.workspace / "a.py").write_text("saved")
        self.store.append_many([self.start(), self.snapshot(), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "content_hash": digest("one\ntwo\nthree")})])
        self.store.append(self.event("state", {"status": "paused"}))
        summary = self.store.overview()
        self.assertEqual(summary["totals"]["uncertain_files"], 1)
        self.assertEqual(summary["totals"]["line_count"], 0)
        with self.assertRaises(ValueError): current_source(self.store, "a.py", digest("saved"))

    def test_fresh_baseline_supersedes_interrupted_dirty_document(self):
        (self.workspace / "a.py").write_text("saved")
        self.store.append_many([self.start(), self.snapshot(), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "content_hash": digest("one\ntwo\nthree")})])
        self.store.close(); self.store = SQLiteStore(self.state, self.workspace)
        self.assertTrue(self.store.overview()["files"][0]["current_uncertain"])
        self.sid = str(uuid.uuid4()); self.seq = 0
        self.store.append_many([self.start(), self.snapshot("saved"), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": False, "content_hash": digest("saved")})])
        self.assertFalse(self.store.overview()["files"][0]["current_uncertain"])

    def test_unsupported_dirty_buffer_cannot_credit_previous_saved_hash(self):
        (self.workspace / "a.py").write_text("one\ntwo\nthree")
        self.store.append_many([self.start(), self.snapshot(), self.visible(), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "supported": False, "content_hash": None}, 1000)])
        summary = self.store.overview()
        self.assertTrue(summary["files"][0]["current_uncertain"])
        self.assertEqual(summary["totals"]["line_count"], 0)

    def test_document_state_cannot_borrow_a_snapshot_from_another_session(self):
        self.store.append_many([self.start(), self.snapshot()])
        self.sid = str(uuid.uuid4()); self.seq = 0
        self.store.append(self.start())
        with self.assertRaises(ValueError): self.store.append(self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "content_hash": digest("one\ntwo\nthree")}))

    def test_read_only_reporting_and_wrong_workspace(self):
        self.store.append(self.start())
        readonly = SQLiteStore(self.state, self.workspace, read_only=True)
        try:
            self.assertEqual(readonly.report()["storage"]["events"], 1)
            with self.assertRaises(ValueError): readonly.append(self.event("marker"))
        finally: readonly.close()
        other = self.root / "other"; other.mkdir()
        with self.assertRaises(ValueError): SQLiteStore(self.state, other, read_only=True)

    def test_live_conflicting_dirty_buffers_are_uncertain(self):
        (self.workspace / "a.py").write_text("saved")
        self.store.append_many([self.start(), self.snapshot(), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "content_hash": digest("one\ntwo\nthree")})])
        self.sid = str(uuid.uuid4()); self.seq = 0
        self.store.append_many([self.start(), self.snapshot("different"), self.event("document_state", {"path": "a.py", "is_open": True, "dirty": True, "content_hash": digest("different")})])
        self.assertTrue(self.store.overview()["files"][0]["current_uncertain"])


class VisibilityDerivationTest(unittest.TestCase):
    def observation(self, text, ranges, a=0, b=1000):
        return {"session_id": "session", "payload": {"content_hash": digest(text), "ranges": ranges, "start_ms": a, "end_ms": b}}
    def test_final_newline_does_not_leave_a_phantom_gap(self):
        text = "one\ntwo\n"
        stats = derive(text, [self.observation(text, [[1, 3]])], {digest(text): text})
        self.assertEqual((stats["line_count"], stats["reported_lines"], stats["unknown_lines"]), (2, 2, 0))
        self.assertEqual(derive("", [], {})["line_count"], 0)
    def test_mirrored_panes_union_time_instead_of_doubling_dwell(self):
        text = "one\ntwo\nthree"; e = self.observation(text, [[1, 2]], b=600)
        stats = derive(text, [e, copy.deepcopy(e)], {digest(text): text})
        self.assertEqual(stats["brief_lines"], 2); self.assertEqual(stats["dwell_lines"], 0)
    def test_verified_unchanged_blocks_carry_evidence_changed_lines_do_not(self):
        old = "header\noriginal\ntail"; new = "header\nchanged\ntail"
        stats = derive(new, [self.observation(old, [[1, 3]])], {digest(old): old})
        self.assertEqual(stats["reported_ranges"], [[1, 1], [3, 3]])
        self.assertEqual(stats["unknown_lines"], 1)
        self.assertEqual(derive(old, [self.observation(old, [[1, 3]])], {digest(old): old})["reported_lines"], 3)
    def test_repeated_blocks_are_ambiguous_and_large_mapping_is_bounded(self):
        self.assertEqual(unique_line_mapping("repeat\nrepeat", "repeat\nrepeat\nrepeat"), {})
        self.assertEqual(unique_line_mapping("x\n"*5001, "x\n"*5002), {})


if __name__ == "__main__": unittest.main()
