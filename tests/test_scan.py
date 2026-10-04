from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import io
import json
import os

from blindspot.cli import main
from blindspot.scan.report import build_report, encode, render
from blindspot.scan.repo import Repository, RepoError
from blindspot.state import State
from .support import SandboxCase

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


class ScanTests(SandboxCase):
    def report(self, **kwargs):
        return build_report(self.root, self.sessions, State(self.state_dir), NOW, **kwargs)

    def file(self, report, path="agent.py"):
        return next(f for f in report["files"] if f["path"] == path)

    def test_positive_missing_mode_and_outside_commit(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(), self.result()])
        report = self.report()
        file = self.file(report)
        self.assertEqual(file["state"], "agent_observed")
        self.assertEqual(file["mode_counts"], {"<unrecorded>": 1})
        self.assertEqual(file["commit_context"], "outside_commit")
        self.assertEqual(sum(report["state_counts"].values()), 1)

    def test_success_survives_another_unresolved_edit(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(), self.result(), self.call(tool_id="missing")])
        file = self.file(self.report())
        self.assertEqual(file["state"], "agent_observed")
        self.assertEqual(file["unresolved_count"], 1)
        self.assertEqual(file["commit_context"], "unavailable")

    def test_unresolved_write_and_failed_edit(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(name="Write")])
        self.assertEqual(self.file(self.report())["state"], "unknown")
        self.transcript([self.user(), self.call(), self.result(error=True)])
        self.assertEqual(self.file(self.report())["state"], "no_agent_observed")

    def test_shell_and_human_overlap_are_indistinguishable(self):
        self.commit({"agent.py": "changed\n"}, when="2026-10-01T10:01:30Z")
        self.transcript([self.user(), self.call(name="Bash"), self.result()])
        file = self.file(self.report())
        self.assertEqual(file["state"], "unknown")
        self.assertIn("unexplained_session_overlap", file["limitations"])
        self.transcript([self.user(), self.result()])
        self.assertEqual(self.file(self.report())["state"], "unknown")

    def test_delayed_commit_changes_inference_not_positive_evidence(self):
        self.commit({"agent.py": "changed\n"}, when="2026-10-02T09:00:00Z")
        self.transcript([self.user(), self.call(), self.result()])
        narrow = self.file(self.report(grace=2))
        wide = self.file(self.report(grace=24))
        self.assertEqual(narrow["state"], wide["state"])
        self.assertEqual(narrow["commit_context"], "outside_commit")
        self.assertEqual(wide["commit_context"], "inside_only")

    def test_inherited_and_identity_unavailable(self):
        self.commit({"agent.py": "other\n"}, email="other@example.test")
        self.transcript([self.user(), self.result()])
        self.assertEqual(self.file(self.report())["state"], "inherited")
        self.git("config", "--unset", "user.email")
        self.git("config", "--unset", "user.name")
        self.assertEqual(self.file(build_report(self.root, self.sessions,
            State(self.base / "fresh-state"), NOW))["state"], "unknown")

    def test_no_transcripts_has_no_rates_or_queue(self):
        self.commit({"agent.py": "original\n"})
        report = self.report()
        self.assertEqual(report["analysis_status"], "unavailable")
        self.assertIsNone(report["state_counts"])
        self.assertIsNone(report["state_rates"])
        self.assertEqual(report["queue"], [])
        self.assertNotIn("state", report["files"][0])
        output = render(report, doctor=True)
        self.assertIn("comparison unavailable without supported evidence", output)
        self.assertNotIn("None", output)

    def test_head_only_exclusions_binary_symlink_and_empty(self):
        self.commit({"agent.py": "committed\n", "empty.py": "", "vendor/a.py": "vendor\n",
                     "a.lock": "lock\n", "space name.py": "space\n", "line\nname.py": "newline\n"})
        (self.root / "blob.bin").write_bytes(b"\x00binary")
        (self.root / "link.py").symlink_to("agent.py")
        self.git("add", "--all")
        self.git("commit", "-m", "Synthetic binary", when="2026-09-02T00:00:00Z")
        self.transcript([self.user(), self.result()])
        (self.root / "agent.py").write_text("uncommitted\n")
        (self.root / "new.py").write_text("untracked\n")
        report = self.report()
        self.assertEqual(report["eligible_files"], 4)
        self.assertEqual(self.file(report, "empty.py")["total_lines"], 0)
        self.assertNotIn("new.py", [f["path"] for f in report["files"]])
        self.assertEqual(report["excluded"]["non_regular"], 1)
        included = self.report(includes=["vendor/*"])
        self.assertEqual(included["eligible_files"], 5)

    def test_rename_and_recreate_are_unknown(self):
        self.commit({"old.py": "original\n", "recreated.py": "first\n"})
        self.git("mv", "old.py", "agent.py")
        self.git("rm", "recreated.py")
        self.git("commit", "-m", "Synthetic rename", when="2026-09-02T00:00:00Z")
        self.commit({"recreated.py": "second\n"}, when="2026-09-03T00:00:00Z")
        self.transcript([self.user(), self.call(), self.result()])
        report = self.report()
        self.assertEqual(self.file(report)["state"], "unknown")
        self.assertEqual(self.file(report, "recreated.py")["state"], "unknown")

    def test_reverted_and_other_branch_edits_remain_path_activity(self):
        self.commit({"agent.py": "original\n"})
        head = Repository(self.root).head
        self.git("checkout", "-b", "agent-work")
        self.commit({"agent.py": "agent version\n"}, when="2026-10-01T10:01:00Z")
        self.git("checkout", "main")
        self.transcript([self.user(), self.call(), self.result()])
        report = self.report()
        self.assertEqual(report["head"], head)
        self.assertEqual(self.file(report)["state"], "agent_observed")
        self.assertIn("historical_path_activity_not_current_content_attribution", self.file(report)["limitations"])

    def test_known_source_loss_persists_and_reappearance_recovers(self):
        self.commit({"agent.py": "original\n", "absence.py": "original\n"})
        self.transcript([self.user(), self.call(), self.result()])
        contents = self.source.read_text()
        self.report()
        self.source.unlink()
        lost = self.report()
        self.assertIn("known_source_coverage_loss", lost["diagnostic_counts"])
        self.assertIn("known_source_coverage_loss", self.report()["diagnostic_counts"])
        self.source.write_text(contents)
        self.assertNotIn("known_source_coverage_loss", self.report()["diagnostic_counts"])

    def test_unchanged_scan_is_deterministic(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(), self.result()])
        self.assertEqual(json.dumps(self.report(), default=encode, sort_keys=True),
                         json.dumps(self.report(), default=encode, sort_keys=True))

    def test_nested_logs_are_disclosed_without_result_stitching(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call()])
        nested = self.source.with_suffix("") / "subagents" / "child.jsonl"
        nested.parent.mkdir(parents=True)
        nested.write_text(json.dumps(self.result()) + "\n")
        report = self.report()
        self.assertEqual(len(report["unsupported_nested"]), 1)
        self.assertEqual(self.file(report)["unresolved_count"], 1)

    def test_mailmap_and_identity_confirmation_are_canonicalized(self):
        self.commit({"agent.py": "original\n", ".mailmap": "Fixture User <fixture@example.test> <alias@example.test>\n"})
        self.commit({"agent.py": "alias\n"}, when="2026-09-02T00:00:00Z", email="alias@example.test")
        self.transcript([self.user(), self.result()])
        self.assertEqual(self.file(self.report())["confirmed_commit_count"], 2)

    def test_cli_unborn_and_invalid_timestamp_have_nonzero_status(self):
        stream = io.StringIO()
        with redirect_stderr(stream):
            status = main(["doctor", str(self.root), "--state-dir", str(self.state_dir)])
        self.assertEqual(status, 2)
        self.assertIn("first commit", stream.getvalue())
        self.commit({"agent.py": "original\n"})
        for invalid in ("2026-10-02", "", " "):
            with self.subTest(now=invalid), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["scan", str(self.root), "--now", invalid]), 2)

    def test_shallow_history_refused(self):
        self.commit({"agent.py": "original\n"})
        clone = self.base / "shallow"
        self.git("clone", "--depth", "1", self.root.as_uri(), str(clone))
        with self.assertRaisesRegex(RepoError, "Shallow"):
            Repository(clone)

    def test_cli_json_and_brief_global_options_both_positions(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(), self.result()])
        for argv in (["--state-dir", str(self.state_dir), "doctor", str(self.root)],
                     ["doctor", str(self.root), "--state-dir", str(self.state_dir)]):
            output = io.StringIO()
            with redirect_stdout(output):
                status = main([*argv, "--sessions-dir", str(self.sessions), "--json", "--now", NOW.isoformat()])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["state_counts"]["agent_observed"], 1)
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["brief", str(self.root / "agent.py"), "--state-dir", str(self.state_dir),
                "--sessions-dir", str(self.sessions), "--now", NOW.isoformat()])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["file"]["events"][0]["source_ref"])

    def test_explicit_link_and_identity_changes_survive_rescan(self):
        self.commit({"agent.py": "original\n"})
        rows = [self.user(), self.call(), self.result()]
        origin = "/missing/fixture-checkout"
        for row in rows:
            row["cwd"] = origin
        self.transcript(rows)
        self.assertEqual(self.report()["analysis_status"], "unavailable")
        options = ["--state-dir", str(self.state_dir), "--sessions-dir", str(self.sessions)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["link", str(self.source), str(self.root), *options]), 0)
        self.assertEqual(self.file(self.report())["state"], "agent_observed")
        self.assertTrue(self.report()["manual_links"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["identity", str(self.root), "--remove", "fixture@example.test", *options]), 0)
        report = self.report()
        self.assertEqual(report["identity"]["confirmed"], [])
        self.assertEqual(self.file(report)["commit_context"], "unavailable")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["identity", str(self.root), "--confirm", "fixture@example.test", *options]), 0)
        self.assertEqual(self.report()["identity"]["confirmed"], ["fixture@example.test"])

    def test_missing_timestamps_keep_positive_evidence_but_disable_inference(self):
        self.commit({"agent.py": "original\n"})
        call = self.call()
        del call["timestamp"]
        self.transcript([self.user(), call, self.result()])
        file = self.file(self.report())
        self.assertEqual(file["state"], "agent_observed")
        self.assertEqual(file["commit_context"], "unavailable")

    def test_path_escapes_remain_diagnostics_and_do_not_name_checkout_file(self):
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(path="../agent.py"), self.result()])
        report = self.report()
        self.assertEqual(self.file(report)["success_count"], 0)
        self.assertEqual(report["diagnostic_counts"]["edit_outside_checkout"], 1)

    def test_zero_eligible_denominator_is_not_zero_percent(self):
        self.commit({"vendor/a.py": "excluded\n"})
        self.transcript([self.user(), self.result()])
        report = self.report()
        self.assertEqual(report["eligible_files"], 0)
        self.assertIsNone(report["state_rates"])

    def test_source_does_not_cross_checkout_contexts(self):
        self.commit({"agent.py": "original\n"})
        other = self.base / "other"
        other.mkdir()
        self.git("init", str(other))
        rows = [self.user(), self.call(), self.result()]
        other_call = self.call(path="agent.py", tool_id="other")
        other_call["cwd"] = str(other)
        other_result = self.result("other")
        other_result["cwd"] = str(other)
        rows.extend([other_call, other_result])
        self.transcript(rows)
        self.assertEqual(self.file(self.report())["success_count"], 1)

    def test_state_override_cannot_write_into_inspected_repository(self):
        self.commit({"agent.py": "original\n"})
        state_dir = self.root / ".blindspot"
        with redirect_stderr(io.StringIO()):
            status = main(["doctor", str(self.root), "--state-dir", str(state_dir),
                           "--sessions-dir", str(self.sessions)])
        self.assertEqual(status, 2)
        self.assertFalse(state_dir.exists())

    def test_brief_reads_committed_file_even_when_parent_directory_is_deleted(self):
        self.commit({"nested/agent.py": "committed\n"})
        self.transcript([self.user(), self.call(path="nested/agent.py"), self.result()])
        (self.root / "nested/agent.py").unlink()
        (self.root / "nested").rmdir()
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["brief", str(self.root / "nested/agent.py"), "--state-dir", str(self.state_dir),
                           "--sessions-dir", str(self.sessions)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["file"]["state"], "agent_observed")
