from contextlib import redirect_stderr, redirect_stdout
import copy
from datetime import datetime, timezone
import hashlib
import io
import json

from blindspot.cli import main
from blindspot.scan.report import build_report, encode
from blindspot.state import State
from .support import SandboxCase

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


class CopyTests(SandboxCase):
    def setUp(self):
        super().setUp()
        self.commit({"agent.py": "original\n", "other.py": "original\n"})

    def report(self, rows, copied=None, **kwargs):
        self.transcript(rows)
        second = self.source.with_name("z-copy.jsonl")
        second.write_text("".join(json.dumps(row) + "\n" for row in (rows if copied is None else copied)))
        return build_report(self.root, self.sessions, State(self.state_dir), NOW, **kwargs)

    def file(self, report):
        return next(f for f in report["files"] if f["path"] == "agent.py")

    def test_copies_count_once_and_preserve_every_reference(self):
        rows = [self.user(permissionMode="auto"), self.call(), self.result(), self.result()]
        report = self.report(rows)
        file = self.file(report)
        self.assertEqual(file["success_count"], 1)
        self.assertEqual(report["recorded_operation_counts"], {"ok": 2})
        self.assertEqual(report["operation_counts"], {"ok": 1})
        self.assertEqual(report["deduplication"]["cross_source_copies_collapsed"], 1)
        event = file["events"][0]
        self.assertEqual(len(event["observations"]), 2)
        self.assertEqual(len({o["source_key"] for o in event["observations"]}), 2)
        self.assertTrue(all(len(o["result_refs"]) == 2 for o in event["observations"]))
        self.assertEqual(file["mode_counts"], {"auto": 1})

    def test_copied_windows_all_contribute_to_timing(self):
        self.commit({"agent.py": "changed\n"}, when="2026-10-01T18:00:00Z")
        rows = [self.user(), self.call(), self.result()]
        copied = [*rows, self.user("2026-10-01T19:00:00Z")]
        file = self.file(self.report(rows, copied, grace=0))
        self.assertEqual(file["success_count"], 1)
        self.assertEqual(file["confirmed_commit_count"], 2)
        self.assertEqual(file["outside_commit_count"], 1)

    def test_missing_result_is_not_completed_by_another_source(self):
        rows = [self.user(), self.call(), self.result()]
        report = self.report(rows, rows[:-1])
        file = self.file(report)
        self.assertEqual((file["success_count"], file["unresolved_count"]), (1, 1))
        self.assertEqual(file["commit_context"], "unavailable")
        self.assertIn("copied_operation_incomplete_results", report["diagnostic_counts"])
        self.assertFalse(report["deduplication"]["cross_source_copies_collapsed"])

    def test_contradictory_results_remain_unknown_with_original_observations(self):
        rows = [self.user(), self.call(), self.result()]
        report = self.report(rows, [self.user(), self.call(), self.result(error=True)])
        file = self.file(report)
        self.assertEqual(file["state"], "unknown")
        self.assertEqual(file["unresolved_count"], 2)
        self.assertEqual(report["recorded_operation_counts"], {"error": 1, "ok": 1})
        self.assertIn("copied_operation_conflicting_results", report["diagnostic_counts"])
        self.assertEqual({o["outcome"] for e in file["events"] for o in e["observations"]}, {"ok", "error"})

    def test_different_inputs_times_or_modes_are_not_silently_merged(self):
        rows = [self.user(permissionMode="default"), self.call(), self.result()]
        for variant in ("input", "timestamp", "mode", "missing_timestamp", "id"):
            with self.subTest(variant=variant):
                copied = copy.deepcopy(rows)
                if variant == "input":
                    copied[1]["message"]["content"][0]["input"]["new_string"] = "different"
                elif variant == "timestamp":
                    copied[1]["timestamp"] = "2026-10-01T10:01:01Z"
                elif variant == "mode":
                    copied[0]["permissionMode"] = "auto"
                elif variant == "missing_timestamp":
                    del copied[1]["timestamp"]
                else:
                    copied[1]["message"]["content"][0]["id"] = "different-id"
                    copied[2]["message"]["content"][0]["tool_use_id"] = "different-id"
                report = self.report(rows, copied)
                self.assertEqual(self.file(report)["success_count"], 2)
                self.assertFalse(report["deduplication"]["cross_source_copies_collapsed"])

    def test_reused_id_at_another_path_keeps_both_paths(self):
        report = self.report([self.user(), self.call(), self.result()],
                             [self.user(), self.call(path="other.py"), self.result()])
        self.assertTrue(all(f["success_count"] == 1 for f in report["files"]))

    def test_fingerprints_and_references_do_not_retain_payloads(self):
        call = self.call(name="Write")
        call["message"]["content"][0]["input"]["content"] = "PRIVATE_COPY_PAYLOAD"
        report = self.report([self.user(), call, self.result()])
        self.assertNotIn("PRIVATE_COPY_PAYLOAD", json.dumps(report, default=encode))
        self.assertEqual(self.file(report)["success_count"], 1)

    def test_counts_include_same_source_copies(self):
        rows = [self.user(), self.call(), self.call(), self.result()]
        report = self.report(rows)
        self.assertEqual(report["recorded_operation_counts"], {"ok": 4})
        self.assertEqual(report["operation_counts"], {"ok": 1})
        self.assertEqual(report["deduplication"]["repeated_records_collapsed"], 3)
        self.assertEqual(len(self.file(report)["events"][0]["observations"]), 4)


class ReadOnlyTests(SandboxCase):
    def setUp(self):
        super().setUp()
        self.commit({"agent.py": "original\n"})
        self.transcript([self.user(), self.call(), self.result()])

    def run_cli(self, command, *flags, state_dir=None):
        target = self.root / "agent.py" if command == "brief" else self.root
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            status = main([command, str(target), "--state-dir", str(state_dir or self.state_dir),
                "--sessions-dir", str(self.sessions), "--now", NOW.isoformat(), *flags])
        return status, output.getvalue()

    def snapshot(self, directory):
        return {str(p.relative_to(directory)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in directory.rglob("*") if p.is_file()}

    def test_all_read_only_queries_create_no_state_and_preserve_inputs(self):
        before = self.snapshot(self.base)
        for command in ("scan", "doctor", "brief", "identity"):
            status, output = self.run_cli(command, "--read-only", "--json")
            self.assertEqual(status, 0)
            if command != "identity":
                self.assertTrue(json.loads(output)["read_only"])
            self.assertFalse(self.state_dir.exists())
        self.assertEqual(self.snapshot(self.base), before)

    def test_existing_state_bytes_and_metadata_are_unchanged(self):
        build_report(self.root, self.sessions, State(self.state_dir), NOW)
        before = self.snapshot(self.base)
        self.assertEqual(self.run_cli("doctor", "--read-only")[0], 0)
        self.assertEqual(self.snapshot(self.base), before)

    def test_read_only_rejects_configuration_mutations(self):
        for command, flags in (("identity", ["--confirm", "alias@example.test"]),
                               ("identity", ["--remove", "fixture@example.test"])):
            self.assertEqual(self.run_cli(command, "--read-only", *flags)[0], 2)
        with redirect_stderr(io.StringIO()):
            status = main(["link", str(self.source), str(self.root), "--read-only",
                           "--state-dir", str(self.state_dir)])
        self.assertEqual(status, 2)
        self.assertFalse(self.state_dir.exists())

    def test_temporary_mapping_handles_moved_checkout_without_saving_links(self):
        origin = "/missing/old-checkout"
        rows = [self.user(), self.call(), self.result()]
        for row in rows:
            row["cwd"] = origin
        self.transcript(rows)
        status, output = self.run_cli("doctor", "--read-only", "--source-root", origin, "--json")
        self.assertEqual(status, 0)
        report = json.loads(output)
        self.assertEqual(report["state_counts"]["agent_observed"], 1)
        self.assertEqual(len(report["temporary_source_links"]), 1)
        self.assertEqual(report["manual_links"], [])
        self.assertFalse(self.state_dir.exists())
        status, output = self.run_cli("doctor", "--source-root", origin, "--json")
        self.assertEqual(status, 0)
        self.assertEqual(State(self.state_dir).data["links"], {})
        self.assertEqual(json.loads(self.run_cli("doctor", "--read-only", "--json")[1])["analysis_status"], "unavailable")

    def test_temporary_mapping_refuses_unmatched_and_unrelated_contexts(self):
        self.assertEqual(self.run_cli("doctor", "--read-only", "--source-root", "/wrong/origin")[0], 2)
        rows = [self.user(), self.call(), self.result(), self.user(cwd="/unrelated/checkout")]
        self.transcript(rows)
        self.assertEqual(self.run_cli("doctor", "--read-only", "--source-root", str(self.root))[0], 2)
        self.assertFalse(self.state_dir.exists())

    def test_read_only_global_option_both_positions(self):
        options = ["--state-dir", str(self.state_dir), "--sessions-dir", str(self.sessions), "--json"]
        for args in (["--read-only", "doctor", str(self.root)],
                     ["doctor", str(self.root), "--read-only"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([*args, *options]), 0)
        self.assertFalse(self.state_dir.exists())
