from contextlib import redirect_stderr, redirect_stdout
import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from blindspot.cli import main
from blindspot.review import ReviewError
from blindspot.review.service import ReviewService
from blindspot.review.targets import export_target
from blindspot.scan.repo import Repository
from .support import SandboxCase

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
CODE = "LIMIT = 10\n\n" + "\n".join(f"# source line {i}" for i in range(1, 24)) + "\n"


class ReviewTests(SandboxCase):
    def setUp(self):
        super().setUp()
        self.commit({"sample.py": CODE, "context.py": "SETTING = 1\n" + "# context\n" * 12})
        self.service = ReviewService(self.state_dir)
        self.manifest = export_target(self.root / "sample.py")

    def value(self, label="original", manifest=None):
        manifest = manifest or self.manifest
        return {"schema_version": 1, "id": "untrusted-import-id", "generator": "manual-fixture",
            "manifest": manifest, "questions": [
                {"id": f"external-{i}", "prompt": f"Reasoning question {i}: {label}",
                 "options": ["option zero", "option one", "option two", "option three"],
                 "correct_index": i, "explanation": f"PRIVATE_KEY_EXPLANATION_{i}",
                 "rationale": {"path": "sample.py", "start_line": 1, "end_line": 10,
                               "reason": "PRIVATE_KEY_RATIONALE"}} for i in range(3)]}

    def imported(self, label="original", manifest=None):
        result = self.service.import_quiz(self.value(label, manifest), NOW)
        self.assertEqual(result["status"], "validated")
        return result["set_id"]

    def finish(self, set_id, wrong=False, confidence="solid", practice=False):
        attempt = self.service.start(set_id, NOW, practice)["attempt_id"]
        for i in range(3):
            self.service.answer(attempt, f"q{i + 1}", (i + 1) % 4 if wrong and i == 0 else i, confidence, NOW)
        return self.service.complete(attempt, NOW)

    def target_status(self):
        return self.service.status(Repository(self.root))["files"]["sample.py"]["targets"][0]

    def test_export_reads_head_not_worktree_and_binds_context(self):
        (self.root / "sample.py").write_text("dirty bytes\n")
        manifest = export_target(self.root / "sample.py", contexts=[(self.root / "context.py", 1, 3)])
        self.assertEqual(manifest["target"]["code"], CODE)
        self.assertEqual(manifest["context"][0]["code"], "SETTING = 1\n# context\n# context\n")
        self.assertEqual(self.service.import_quiz(self.value(manifest=manifest), NOW)["status"], "validated")

    def test_export_bounds_paths_binary_and_symlinks(self):
        for start, end in ((1, 9), (0, 12), (1, 100), (True, 20)):
            with self.subTest(start=start, end=end), self.assertRaises(ReviewError):
                export_target(self.root / "sample.py", start, end)
        self.commit({"large.py": "# line\n" * 301})
        with self.assertRaises(ReviewError):
            export_target(self.root / "large.py")
        self.assertEqual(export_target(self.root / "large.py", 1, 20)["target"]["end_line"], 20)
        (self.root / "link.py").symlink_to("sample.py")
        (self.root / "binary.bin").write_bytes(b"\0" * 20)
        self.git("add", "--all")
        self.git("commit", "-m", "fixture objects")
        for file in ("link.py", "binary.bin"):
            with self.subTest(file=file), self.assertRaises(ReviewError):
                export_target(self.root / file)

    def test_import_rejects_bad_shapes_and_retains_reason(self):
        for bad in ("count", "options", "answer", "explanation", "rationale", "duplicate_prompt"):
            with self.subTest(bad=bad):
                value = self.value()
                if bad == "count":
                    value["questions"] = value["questions"][:2]
                elif bad == "options":
                    value["questions"][0]["options"][1] = value["questions"][0]["options"][0]
                elif bad == "answer":
                    value["questions"][0]["correct_index"] = True
                elif bad == "explanation":
                    value["questions"][0]["explanation"] = ""
                elif bad == "rationale":
                    value["questions"][0]["rationale"]["path"] = "../../secret"
                else:
                    value["questions"][1]["prompt"] = value["questions"][0]["prompt"]
                result = self.service.import_quiz(value, NOW)
                self.assertEqual(result["status"], "rejected")
                self.assertTrue(result["reason"])
                record = self.service.store.read()["sets"][result["set_id"]]
                self.assertNotIn("questions", record)
                with self.assertRaises(ReviewError):
                    self.service.start(result["set_id"], NOW)

    def test_import_rejects_tampered_code_hash_and_path(self):
        for key, value in (("code", "invented"), ("file_hash", "bad"), ("path", "../sample.py")):
            quiz = self.value()
            quiz["manifest"] = copy.deepcopy(self.manifest)
            quiz["manifest"]["target"][key] = value
            self.assertEqual(self.service.import_quiz(quiz, NOW)["status"], "rejected")

    def test_keys_withheld_until_all_answers_and_first_answers_immutable(self):
        set_id = self.imported()
        attempt = self.service.start(set_id, NOW)["attempt_id"]
        view = self.service.show(attempt)
        serialized = json.dumps(view)
        for secret in ("correct_index", "explanation", "rationale", "PRIVATE_KEY"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(self.service.answer(attempt, "q1", 0, "shaky", NOW), {"accepted": True, "idempotent": False})
        self.assertEqual(self.service.answer(attempt, "q1", 0, "shaky", NOW), {"accepted": True, "idempotent": True})
        with self.assertRaises(ReviewError):
            self.service.answer(attempt, "q1", 1, "shaky", NOW)
        with self.assertRaises(ReviewError):
            self.service.answer(attempt, "q1", 0, "solid", NOW)
        with self.assertRaises(ReviewError):
            self.service.complete(attempt, NOW)
        with self.assertRaises(ReviewError):
            self.service.results(attempt)
        self.assertEqual(self.service.start(set_id, NOW)["attempt_id"], attempt)
        for i in (1, 2):
            self.service.answer(attempt, f"q{i + 1}", i, "guessed", NOW)
        results = self.service.complete(attempt, NOW)
        self.assertTrue(results["current_sample_pass"])
        self.assertIn("PRIVATE_KEY_EXPLANATION", json.dumps(results))
        self.assertEqual(self.service.complete(attempt, NOW), results)

    def test_duplicates_cannot_reset_first_attempt_with_new_ids_or_generator(self):
        set_id = self.imported()
        results = self.finish(set_id, wrong=True)
        copied = self.value()
        copied["id"] = "new-set-id"
        copied["generator"] = "new-generator-label"
        for q in copied["questions"]:
            q["id"] = "new-question-id"
            q["rationale"]["reason"] = "  PRIVATE_KEY_RATIONALE\n"
        result = self.service.import_quiz(copied, NOW)
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["set_id"], set_id)
        self.assertEqual(self.service.start(set_id, NOW)["attempt_id"], results["attempt_id"])
        self.assertFalse(results["current_sample_pass"])

    def test_practice_cannot_create_a_pass_or_clear_confidently_wrong(self):
        set_id = self.imported()
        with self.assertRaises(ReviewError):
            self.service.start(set_id, NOW, practice=True)
        self.finish(set_id, wrong=True)
        result = self.finish(set_id, practice=True)
        self.assertTrue(result["passed_against_key"])
        self.assertFalse(result["current_sample_pass"])
        self.assertEqual(self.target_status()["current_confidently_wrong"], 1)

    def test_new_confidently_wrong_revokes_pass_and_rejection_restores_it(self):
        passed = self.finish(self.imported("pass"))
        bad_set = self.imported("disputed")
        self.finish(bad_set, wrong=True)
        self.assertEqual(self.target_status()["status"], "revoked")
        self.assertFalse(self.service.results(passed["attempt_id"])["current_sample_pass"])
        self.service.reject(bad_set, "The answer key is wrong", NOW)
        self.assertEqual(self.target_status()["status"], "sample_passed")
        self.assertTrue(self.service.results(passed["attempt_id"])["current_sample_pass"])
        self.assertEqual(self.target_status()["historical_confidently_wrong"], 0)
        self.assertEqual(len(self.service.store.read()["attempts"]), 2)

    def test_rejecting_a_pass_set_removes_its_pass_and_reimport_stays_rejected(self):
        set_id = self.imported()
        self.finish(set_id)
        self.service.reject(set_id, "Faulty question", NOW)
        self.assertFalse(self.target_status()["current_passing_samples"])
        self.assertEqual(self.service.import_quiz(self.value(), NOW)["status"], "rejected")

    def test_fresh_set_resolves_target_flag_but_unrelated_target_does_not(self):
        self.finish(self.imported("failed"), wrong=True)
        other_manifest = export_target(self.root / "sample.py", 1, 12, "other-range")
        self.finish(self.imported("other", other_manifest))
        original = next(t for t in self.service.status(Repository(self.root))["files"]["sample.py"]["targets"]
                        if t["target"] == "whole-file")
        self.assertEqual(original["current_confidently_wrong"], 1)
        self.finish(self.imported("fresh pass"))
        self.assertEqual(self.target_status()["current_confidently_wrong"], 0)

    def test_file_change_outside_target_and_context_change_make_results_stale(self):
        for change in ("outside", "context"):
            with self.subTest(change=change):
                manifest = export_target(self.root / "sample.py", 1, 12,
                                         contexts=[(self.root / "context.py", 1, 3)])
                set_id = self.imported(change, manifest)
                attempt = self.service.start(set_id, NOW)["attempt_id"]
                if change == "outside":
                    self.commit({"sample.py": CODE + "# changed outside target\n"})
                else:
                    self.commit({"context.py": "SETTING = 2\n" + "# context\n" * 12})
                with self.assertRaisesRegex(ReviewError, "stale"):
                    self.service.answer(attempt, "q1", 0, "solid", NOW)
                with self.assertRaisesRegex(ReviewError, "stale"):
                    self.service.complete(attempt, NOW)

    def test_reachable_identical_bytes_retain_pass_and_duplicate_identity(self):
        set_id = self.imported()
        self.finish(set_id)
        self.commit({"unrelated.txt": "changed elsewhere\n"})
        self.assertEqual(self.target_status()["status"], "sample_passed")
        fresh = export_target(self.root / "sample.py")
        duplicate = self.service.import_quiz(self.value(manifest=fresh), NOW)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["set_id"], set_id)

    def test_unreachable_revision_is_orphaned(self):
        self.git("checkout", "-b", "quiz-branch")
        self.commit({"unrelated.txt": "branch\n"})
        self.manifest = export_target(self.root / "sample.py")
        set_id = self.imported()
        self.finish(set_id)
        self.git("checkout", "main")
        self.assertEqual(self.target_status()["status"], "orphaned")
        with self.assertRaisesRegex(ReviewError, "orphaned"):
            self.service.start(set_id, NOW)

    def test_scans_preserve_review_store_and_read_only_queries_never_write(self):
        self.imported()
        path = self.state_dir / "reviews.json"
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["doctor", str(self.root), "--state-dir", str(self.state_dir),
                                   "--sessions-dir", str(self.sessions)]), 0)
            self.assertEqual(main(["quiz", "status", str(self.root), "--state-dir", str(self.state_dir), "--read-only"]), 0)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_state_inside_checkout_rejected_even_for_invalid_import(self):
        service = ReviewService(self.root / ".blindspot")
        value = self.value()
        value["manifest"] = copy.deepcopy(self.manifest)
        value["manifest"]["target"]["file_hash"] = "bad"
        with self.assertRaises(ReviewError):
            service.import_quiz(value, NOW)
        self.assertFalse((self.root / ".blindspot").exists())

    def test_corrected_set_records_relationship_and_validates_binding(self):
        set_id = self.imported()
        self.service.reject(set_id, "incorrect key", NOW)
        value = self.value("corrected")
        value["supersedes"] = set_id
        result = self.service.import_quiz(value, NOW)
        self.assertEqual(self.service.store.read()["sets"][result["set_id"]]["supersedes"], set_id)

    def test_concurrent_start_creates_only_one_first_attempt(self):
        set_id = self.imported()
        args = [sys.executable, "-B", "-m", "blindspot", "quiz", "start", set_id,
                "--state-dir", str(self.state_dir)]
        children = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        replies = []
        for child in children:
            stdout, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, stderr.decode())
            replies.append(json.loads(stdout))
        self.assertEqual(replies[0]["attempt_id"], replies[1]["attempt_id"])
        self.assertEqual(len(self.service.store.read()["attempts"]), 1)

    def test_interactive_pause_resume_and_no_early_key_exposure(self):
        set_id = self.imported()
        args = ["quiz", "review", set_id, "--state-dir", str(self.state_dir)]
        output = io.StringIO()
        with patch("builtins.input", side_effect=["1", "solid", EOFError()]), redirect_stdout(output), redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 130)
        self.assertNotIn("PRIVATE_KEY", output.getvalue())
        attempts = self.service.store.read()["attempts"]
        self.assertEqual(len(attempts), 1)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["2", "shaky", "3", "guessed"]), redirect_stdout(output):
            self.assertEqual(main(args), 0)
        self.assertIn("previously submitted", output.getvalue())
        self.assertIn("PRIVATE_KEY_EXPLANATION", output.getvalue())

    def test_read_only_mutations_and_export_output_are_rejected(self):
        set_id = self.imported()
        path = self.state_dir / "reviews.json"
        before = path.read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["quiz", "start", set_id, "--read-only", "--state-dir", str(self.state_dir)]), 2)
            self.assertEqual(main(["target", "export", str(self.root / "sample.py"), "--read-only",
                                   "--output", str(self.base / "out.json")]), 2)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.base / "out.json").exists())

    def test_mutation_guards_run_before_creating_lock_inside_checkout(self):
        set_id = self.imported()
        attempt = self.service.start(set_id, NOW)["attempt_id"]
        directory = self.root / ".blindspot"
        directory.mkdir()
        state = directory / "reviews.json"
        state.write_bytes(self.service.store.path.read_bytes())
        before = state.read_bytes(), state.stat().st_mtime_ns
        bad = ReviewService(directory)
        for mutate in (lambda: bad.start(set_id, NOW),
                       lambda: bad.answer(attempt, "q1", 0, "solid", NOW),
                       lambda: bad.complete(attempt, NOW),
                       lambda: bad.reject(set_id, "faulty", NOW)):
            with self.assertRaisesRegex(ReviewError, "outside"):
                mutate()
            self.assertFalse((directory / "reviews.lock").exists())
            self.assertEqual((state.read_bytes(), state.stat().st_mtime_ns), before)

    def test_completion_rechecks_content_after_every_answer_is_saved(self):
        set_id = self.imported()
        attempt = self.service.start(set_id, NOW)["attempt_id"]
        for i in range(3):
            self.service.answer(attempt, f"q{i + 1}", i, "solid", NOW)
        self.commit({"sample.py": CODE + "# subsequent committed change\n"})
        with self.assertRaisesRegex(ReviewError, "stale"):
            self.service.complete(attempt, NOW)
        record = self.service.store.read()["attempts"][attempt]
        self.assertIsNone(record["completed_at"])
        with self.assertRaises(ReviewError):
            self.service.results(attempt)
        self.assertEqual(self.target_status()["current_passing_samples"], 0)

    def test_report_and_brief_include_samples_without_changing_provenance(self):
        from blindspot.scan.report import build_report, render
        from blindspot.state import State
        set_id = self.imported()
        self.finish(set_id)
        before = self.service.store.path.read_bytes(), self.service.store.path.stat().st_mtime_ns
        report = build_report(self.root, self.base / "no-sessions",
                              State(self.state_dir, read_only=True), NOW)
        self.assertEqual(report["analysis_status"], "unavailable")
        self.assertIsNone(report["state_rates"])
        self.assertEqual(report["review_status"]["files"]["sample.py"]["current_passing_samples"], 1)
        self.assertIn("1 current passing target samples", render(report))
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["brief", str(self.root / "sample.py"), "--read-only",
                         "--state-dir", str(self.state_dir), "--sessions-dir", str(self.base / "no-sessions")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["file"]["review"]["current_passing_samples"], 1)
        self.assertEqual((self.service.store.path.read_bytes(), self.service.store.path.stat().st_mtime_ns), before)

    def test_uncertain_wrong_answer_does_not_revoke_earlier_sample(self):
        self.finish(self.imported("pass"))
        self.finish(self.imported("uncertain"), wrong=True, confidence="shaky")
        self.assertEqual(self.target_status()["status"], "sample_passed")
        self.assertEqual(self.target_status()["current_confidently_wrong"], 0)

    def test_cli_rejects_duplicate_json_keys_without_creating_state(self):
        directory = self.base / "uncreated-state"
        file = self.base / "bad.json"
        file.write_text('{"schema_version": 1, "schema_version": 2}')
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["quiz", "import", str(file), "--state-dir", str(directory)]), 2)
        self.assertFalse(directory.exists())

    def test_import_rejects_boolean_versions_and_null_line_bounds(self):
        for kind in ("quiz-version", "manifest-version", "line-bound"):
            with self.subTest(kind=kind):
                value = copy.deepcopy(self.value())
                if kind == "quiz-version":
                    value["schema_version"] = True
                elif kind == "manifest-version":
                    value["manifest"]["schema_version"] = True
                else:
                    value["manifest"]["target"]["start_line"] = None
                self.assertEqual(self.service.import_quiz(value, NOW)["status"], "rejected")

    def test_export_enforces_byte_limit_on_target_and_context(self):
        self.commit({"wide.py": ("#" * 2000 + "\n") * 10})
        with self.assertRaisesRegex(ReviewError, "16 KiB"):
            export_target(self.root / "wide.py")
        with self.assertRaisesRegex(ReviewError, "16 KiB"):
            export_target(self.root / "sample.py", contexts=[(self.root / "wide.py", None, None)])

    def test_feedback_preserves_answers_and_separates_workflow_from_understanding(self):
        result = self.finish(self.imported(), wrong=True)
        attempt = result["attempt_id"]
        before = copy.deepcopy(self.service.store.read()["attempts"])
        summary = self.service.status(Repository(self.root))
        self.assertEqual(summary["experiment"]["unclassified_completed_attempts"], 1)
        reply = self.service.feedback(attempt, NOW, purpose="workflow-test", useful="yes",
                                      active_minutes=0.5, note="Deliberately mixed answers")
        summary = self.service.status(Repository(self.root))
        self.assertEqual(summary["experiment"]["workflow_test_attempts"], 1)
        self.assertEqual(summary["experiment"]["understanding_review_attempts"], 0)
        self.assertEqual(summary["experiment"]["usefulness"]["yes"], 0)
        self.assertEqual(summary["current_confidently_wrong"], 1)
        self.assertEqual(self.service.store.read()["attempts"], before)
        self.assertFalse(self.service.results(attempt)["current_sample_pass"])
        duplicate = self.service.feedback(attempt, NOW, purpose="workflow-test", useful="yes",
                                          active_minutes=0.5, note="Deliberately mixed answers")
        self.assertTrue(duplicate["idempotent"])
        self.assertEqual(duplicate["feedback_id"], reply["feedback_id"])
        self.service.feedback(attempt, NOW, purpose="understanding-review", useful="no", note="Corrected purpose")
        summary = self.service.status(Repository(self.root))
        self.assertEqual(len(summary["feedback"]), 2)
        self.assertEqual(summary["experiment"]["workflow_test_attempts"], 0)
        self.assertEqual(summary["experiment"]["understanding_review_attempts"], 1)
        self.assertEqual(summary["experiment"]["distinct_targets_with_understanding_feedback"], 1)
        self.assertEqual(summary["experiment"]["usefulness"]["no"], 1)

    def test_feedback_can_record_confirmed_purpose_without_inventing_usefulness(self):
        attempt = self.finish(self.imported())["attempt_id"]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["quiz", "feedback", attempt, "--purpose", "workflow-test",
                                   "--state-dir", str(self.state_dir)]), 0)
        feedback = self.service.store.read()["feedback"][-1]
        self.assertEqual(feedback["useful"], "unreported")
        self.assertIsNone(feedback["prior_familiarity"])
        self.assertIsNone(feedback["active_minutes"])

    def test_feedback_requires_completion_and_validates_user_annotations(self):
        attempt = self.service.start(self.imported(), NOW)["attempt_id"]
        with self.assertRaisesRegex(ReviewError, "Complete"):
            self.service.feedback(attempt, NOW, purpose="workflow-test", useful="yes")
        attempt = self.finish(self.imported("completed"))["attempt_id"]
        for change in ({"purpose": "invalid"}, {"useful": "invalid"}, {"familiarity": "invalid"},
                       {"active_minutes": float("nan")}, {"active_minutes": float("inf")},
                       {"active_minutes": -1}, {"active_minutes": True}, {"note": "x" * 4001}):
            with self.subTest(change=change), self.assertRaises(ReviewError):
                self.service.feedback(attempt, NOW, **({"purpose": "workflow-test", "useful": "yes"} | change))
        self.assertEqual(self.service.store.read()["feedback"], [])

    def test_feedback_cli_read_only_and_scan_preservation(self):
        attempt = self.finish(self.imported())["attempt_id"]
        args = ["quiz", "feedback", attempt, "--purpose", "understanding-review", "--useful", "yes",
                "--familiarity", "some", "--active-minutes", "3.5", "--note", "Useful caller correction",
                "--state-dir", str(self.state_dir)]
        before = self.service.store.path.read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main([*args, "--read-only"]), 2)
        self.assertEqual(self.service.store.path.read_bytes(), before)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
            before = self.service.store.path.read_bytes()
            self.assertEqual(main(["doctor", str(self.root), "--state-dir", str(self.state_dir),
                                   "--sessions-dir", str(self.sessions)]), 0)
        self.assertEqual(self.service.store.path.read_bytes(), before)

    def test_feedback_guard_and_legacy_state_reads_do_not_write(self):
        attempt = self.finish(self.imported())["attempt_id"]
        data = self.service.store.read()
        data.pop("feedback")
        self.service.store.path.write_text(json.dumps(data))
        before = self.service.store.path.read_bytes(), self.service.store.path.stat().st_mtime_ns
        self.assertEqual(self.service.store.read()["feedback"], [])
        self.service.status(Repository(self.root))
        self.assertEqual((self.service.store.path.read_bytes(), self.service.store.path.stat().st_mtime_ns), before)
        directory = self.root / ".blindspot"
        directory.mkdir()
        (directory / "reviews.json").write_bytes(before[0])
        with self.assertRaisesRegex(ReviewError, "outside"):
            ReviewService(directory).feedback(attempt, NOW, purpose="workflow-test", useful="unsure")
        self.assertFalse((directory / "reviews.lock").exists())
