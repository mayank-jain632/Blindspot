from datetime import datetime, timezone
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

from blindspot.observer.dashboard import Dashboard
from blindspot.observer.server import make_server
from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.store import digest
from blindspot.review import ReviewError
from blindspot.review.targets import export_target
from .support import SandboxCase

NOW = datetime.now(timezone.utc)
CODE = "LIMIT = 10\n" + "# context\n" * 19


class DashboardTests(SandboxCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.commit({"a.py": CODE, "b.py": "VALUE = 1\n" + "# other\n" * 10})
        self.store = SQLiteStore(self.base / "observer", self.root)
        self.addCleanup(self.store.close)
        self.dashboard = Dashboard(self.store, self.state_dir)
        self.sid = str(uuid.uuid4()); self.sequence = 0

    def event(self, kind, payload=None, ms=0):
        value = {"schema_version": 1, "workspace": str(self.root), "session_id": self.sid,
                 "sequence": self.sequence, "observed_at": NOW.isoformat(), "monotonic_ms": ms,
                 "kind": kind, "payload": payload or {}}
        self.sequence += 1
        return value

    def quiz(self, path="a.py", label="first", contexts=None):
        manifest = export_target(self.root / path, contexts=contexts)
        questions = [{"prompt": f"Question {i}: {label}", "options": ["zero", "one", "two", "three"],
            "correct_index": i, "explanation": "PRIVATE EXPLANATION",
            "rationale": {"path": path, "start_line": 1, "end_line": 10, "reason": "PRIVATE REASON"}} for i in range(3)]
        return self.dashboard.reviews.import_quiz({"schema_version": 1, "generator": "test fixture",
            "manifest": manifest, "questions": questions}, NOW)["set_id"]

    def complete(self, set_id, wrong=False):
        aid = self.dashboard.review_post("start", {"set_id": set_id})["attempt_id"]
        for i in range(3):
            self.dashboard.review_post("answer", {"attempt_id": aid, "question_id": f"q{i+1}",
                "chosen_index": (i+1) % 4 if wrong else i, "confidence": "solid"})
        return self.dashboard.review_post("complete", {"attempt_id": aid})

    def test_empty_reads_do_not_create_review_state_and_explain_no_recording(self):
        data = self.dashboard.overview()
        self.assertFalse(data["has_observations"])
        self.assertEqual(data["totals"]["eligible_files"], 2)
        self.assertEqual(data["review"]["completed_attempts"], 0)
        self.assertFalse(self.state_dir.exists())
        self.assertEqual(data["files"][0]["commits_90d"], 1)
        self.assertTrue(all(e["source"] for f in data["files"] for e in f["evidence"]))

    def test_weekly_activity_counts_each_file_once_across_days_and_events(self):
        self.store.append(self.event("session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        for path, day in [("a.py", "2026-09-07"), ("a.py", "2026-09-08"), ("b.py", "2026-09-08"), ("a.py", "2026-09-21")]:
            event = self.event("interaction", {"path": path, "kind": "selection", "cause": "keyboard-event"})
            event["observed_at"] = day + "T12:00:00+00:00"
            self.store.append(event)
        self.assertEqual(self.dashboard.overview()["weekly"], [
            {"week": "2026-09-07", "files_touched": 2, "event_count": 3},
            {"week": "2026-09-21", "files_touched": 1, "event_count": 1}])

    def test_eligible_sample_pass_lowers_rank_without_altering_display(self):
        set_id = self.quiz()
        before = self.dashboard.overview()
        self.assertEqual(before["queue"], ["a.py", "b.py"])
        result = self.complete(set_id)
        self.assertTrue(result["current_sample_pass"])
        after = self.dashboard.overview()
        self.assertEqual(after["queue"], ["b.py", "a.py"])
        self.assertEqual(before["totals"], after["totals"])
        file = next(f for f in after["files"] if f["path"] == "a.py")
        self.assertTrue(file["review"]["tested"])
        self.assertEqual(file["review"]["passing_samples"], 1)

    def test_solid_wrong_counts_files_not_answers_and_later_pass_resolves(self):
        self.complete(self.quiz(), wrong=True)
        data = self.dashboard.overview()
        self.assertEqual(data["review"]["confidently_wrong_files"], 1)
        self.assertEqual(data["review"]["calibration"]["solid"], {"answers": 3, "correct": 0})
        self.complete(self.quiz(label="fresh"))
        self.assertEqual(self.dashboard.overview()["review"]["confidently_wrong_files"], 0)

    def test_disk_change_removes_sample_credit_and_rejects_stale_source(self):
        set_id = self.quiz(); self.complete(set_id)
        old_hash = digest(CODE)
        (self.root / "a.py").write_text(CODE + "NEW = 2\n")
        file = next(f for f in self.dashboard.overview()["files"] if f["path"] == "a.py")
        self.assertFalse(file["review"]["tested"])
        self.assertEqual(file["review"]["passing_samples"], 0)
        with self.assertRaises(ReviewError): self.dashboard.review_post("start", {"set_id": set_id})
        with self.assertRaises(ValueError): self.dashboard.source("a.py", old_hash)

    def test_external_change_is_visible_even_when_state_stays_partial(self):
        old = "\n".join(f"VALUE_{i} = {i}" for i in range(1, 13)) + "\n"
        self.commit({"a.py": old})
        self.store.append(self.event("session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        def snapshot(text, ms):
            self.store.append(self.event("snapshot", {"path": "a.py", "text": text, "content_hash": digest(text),
                "line_count": len(text.split("\n")), "origin": "disk"}, ms))
        def view(text, ranges, ms):
            self.store.append(self.event("visibility", {"path": "a.py", "content_hash": digest(text), "ranges": ranges,
                "start_ms": ms, "end_ms": ms + 1000, "duration_ms": 1000, "focused": True,
                "focus_scope": "window", "editor_focus": "unverified"}, ms + 1000))
        snapshot(old, 0); view(old, [[1, 4]], 0)
        before = next(f for f in self.dashboard.overview()["files"] if f["path"] == "a.py")
        self.assertEqual(before["state"], "partial")
        self.assertIsNone(before["changed_unseen_lines"])
        new = old.replace("VALUE_3 = 3", "VALUE_3 = 300") + "ADDED = 99\n"
        (self.root / "a.py").write_text(new)  # No agent or editor identity is required.
        after = next(f for f in self.dashboard.overview()["files"] if f["path"] == "a.py")
        self.assertEqual(after["state"], "partial")
        self.assertEqual(after["reported_lines"], 3)
        self.assertEqual(after["changed_unseen_lines"], 2)
        self.assertEqual(after["changed_unseen_ranges"], [[3, 3], [13, 13]])
        self.assertEqual(after["change_baseline_hash"], digest(old))
        snapshot(new, 1100); view(new, [[3, 3], [13, 13]], 1200)
        seen = next(f for f in self.dashboard.overview()["files"] if f["path"] == "a.py")
        self.assertEqual(seen["changed_unseen_lines"], 0)
        self.assertEqual(seen["changed_unseen_ranges"], [])

    def test_dirty_context_invalidates_quiz_before_answers_are_served(self):
        set_id = self.quiz(contexts=[(self.root / "b.py", 1, 5)])
        self.store.append(self.event("session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        text = "dirty context\n" * 15
        self.store.append(self.event("snapshot", {"path": "b.py", "text": text, "content_hash": digest(text), "line_count": 16, "origin": "document"}))
        self.store.append(self.event("document_state", {"path": "b.py", "is_open": True, "dirty": True, "content_hash": digest(text)}))
        with self.assertRaises(ReviewError): self.dashboard.review_post("start", {"set_id": set_id})
        self.assertFalse(next(f for f in self.dashboard.overview()["files"] if f["path"] == "a.py")["review"]["available"])

    def test_current_untested_file_with_old_result_is_hatchet_ready(self):
        self.complete(self.quiz())
        self.commit({"a.py": CODE + "NEW = 2\n"})
        file = next(f for f in self.dashboard.overview()["files"] if f["path"] == "a.py")
        self.assertTrue(file["review"]["stale_results"])
        self.assertFalse(file["review"]["tested"])

    def test_http_origin_validation_and_server_side_review(self):
        set_id = self.quiz()
        server = make_server(self.store, "private collector token", 0, review_directory=self.state_dir)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 3); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        port = server.server_address[1]; endpoint = f"http://127.0.0.1:{port}"
        def request(path, body=None, headers=None, method=None):
            return urlopen(Request(endpoint+path, data=json.dumps(body).encode() if body is not None else None,
                headers={"Content-Type": "application/json", **(headers or {})}, method=method), timeout=5)
        before = self.dashboard.reviews.store.path.read_bytes()
        with request("/api/dashboard") as response:
            self.assertNotIn("correct_index", response.read().decode())
        with self.assertRaises(HTTPError) as error: request("/api/dashboard/review/start")
        self.assertEqual(error.exception.code, 404)
        self.assertEqual(before, self.dashboard.reviews.store.path.read_bytes())
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
            with request("/api/dashboard", headers={"Host": host}): pass
        for method, path in [("GET", "/"), ("GET", "/api/dashboard"), ("PUT", "/")]:
            with self.assertRaises(HTTPError) as error: request(path, headers={"Host": "evil.example"}, method=method)
            self.assertEqual(error.exception.code, 403)
        for headers in ({}, {"Origin": "http://evil.example"}, {"Origin": "null"}):
            with self.assertRaises(HTTPError) as error: request("/api/dashboard/review/start", {"set_id": set_id}, headers)
            self.assertEqual(error.exception.code, 403)
        local = {"Origin": endpoint}
        with request("/api/dashboard/review/start", {"set_id": set_id}, local) as response: aid = json.load(response)["attempt_id"]
        with request(f"/api/dashboard/review/attempt?attempt_id={aid}") as response:
            text = response.read().decode()
            for key in ("correct_index", "PRIVATE", "state", "score"): self.assertNotIn(key, text)
        with self.assertRaises(HTTPError): request("/api/dashboard/review/answer", {"attempt_id": aid, "question_id": "q1", "chosen_index": 0, "confidence": "solid", "correct": True}, local)
        for i in range(3):
            with request("/api/dashboard/review/answer", {"attempt_id": aid, "question_id": f"q{i+1}", "chosen_index": i, "confidence": "solid"}, local): pass
        with request("/api/dashboard/review/complete", {"attempt_id": aid}, local) as response:
            self.assertTrue(json.load(response)["current_sample_pass"])
        with request("/api/dashboard") as response: self.assertEqual(json.load(response)["queue"], ["b.py", "a.py"])
