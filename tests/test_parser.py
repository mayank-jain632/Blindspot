from dataclasses import asdict
import json
from pathlib import Path

from blindspot.adapters.claude_code import discover, parse
from blindspot.scan.report import encode
from .support import SandboxCase


class ParserTests(SandboxCase):
    def edits(self, report):
        return [event for event in report.events if event.kind == "file_edit"]

    def test_fixture_multiple_blocks_and_pending_result(self):
        template = Path(__file__).parent / "fixtures" / "session.jsonl"
        self.source.write_text(template.read_text().replace("__CHECKOUT__", str(self.root)))
        report = parse(self.source)
        edits = self.edits(report)
        self.assertEqual([e.block_index for e in edits], [0, 1])
        self.assertEqual([e.outcome for e in edits], ["ok", "unknown"])
        self.assertEqual(edits[0].mode_raw, "acceptEdits")
        self.assertTrue(edits[0].result_ref.endswith(":3"))
        self.assertEqual(edits[0].path, str(self.root / "agent.py"))

    def test_mode_order_and_no_retroactive_fill(self):
        self.transcript([self.user(), self.call(), self.result(),
            {"type": "permission-mode", "permissionMode": "default"},
            self.call(path="second.py", tool_id="two"), self.result("two")])
        edits = self.edits(parse(self.source))
        self.assertEqual([e.mode_raw for e in edits], [None, "default"])

    def test_missing_mode_and_plan_do_not_discard_edits(self):
        self.transcript([self.user(permissionMode="plan"), self.call(), self.result()])
        report = parse(self.source)
        self.assertEqual(self.edits(report)[0].outcome, "ok")
        self.assertIn("edit_in_plan_policy", [d.category for d in report.diagnostics])

    def test_failed_result_and_missing_error_field(self):
        self.transcript([self.user(), self.call(), self.result(error=True)])
        self.assertEqual(self.edits(parse(self.source))[0].outcome, "error")
        result = self.result()
        del result["message"]["content"][0]["is_error"]
        self.transcript([self.user(), self.call(), result])
        self.assertEqual(self.edits(parse(self.source))[0].outcome, "ok")

    def test_conflicting_and_unsupported_results_remain_unknown(self):
        self.transcript([self.user(), self.call(), self.result(), self.result(error=True)])
        self.assertEqual(self.edits(parse(self.source))[0].outcome, "unknown")
        result = self.result()
        result["message"]["content"][0]["is_error"] = "false"
        self.transcript([self.user(), self.call(), result])
        self.assertEqual(self.edits(parse(self.source))[0].outcome, "unknown")

    def test_duplicates_and_conflicting_ids_preserve_paths(self):
        self.transcript([self.user(), self.call(), self.call(), self.result()])
        report = parse(self.source)
        self.assertEqual(len(self.edits(report)), 1)
        self.assertEqual(report.duplicate_operations, 1)
        self.assertEqual(len(self.edits(report)[0].observations), 2)
        self.assertEqual([o.seq for o in self.edits(report)[0].observations], [2, 3])
        self.assertTrue(all(o.result_refs[0].endswith(":4") for o in self.edits(report)[0].observations))
        self.transcript([self.user(), self.call(), self.call(path="other.py"), self.result()])
        edits = self.edits(parse(self.source))
        self.assertEqual(len(edits), 2)
        self.assertEqual([e.outcome for e in edits], ["unknown", "unknown"])

    def test_malformed_and_partial_lines_are_safe_and_reparsed(self):
        self.transcript([self.user(), self.call()])
        self.source.write_bytes(self.source.read_bytes() + b'{"secret": "NEVER_EXPORT"\n' + b'{"type":"user"')
        first = parse(self.source)
        self.assertIn("malformed_line", [d.category for d in first.diagnostics])
        self.assertIn("incomplete_final_line", [d.category for d in first.diagnostics])
        self.assertNotIn("NEVER_EXPORT", json.dumps(asdict(first), default=encode))
        offset = first.processed_bytes
        self.source.write_bytes(self.source.read_bytes()[:offset] + json.dumps(self.result()).encode() + b"\n")
        second = parse(self.source)
        self.assertEqual(self.edits(second)[0].outcome, "ok")

    def test_payloads_are_not_retained(self):
        call = self.call(name="Write")
        call["message"]["content"][0]["input"]["content"] = "SECRET_SOURCE_BYTES"
        user = self.user(message={"content": "SECRET_PROMPT"})
        result = self.result()
        result["message"]["content"][0]["content"] = "SECRET_RESULT"
        self.transcript([user, call, result])
        serialized = json.dumps(asdict(parse(self.source)), default=encode)
        for secret in ("SECRET_SOURCE_BYTES", "SECRET_PROMPT", "SECRET_RESULT"):
            self.assertNotIn(secret, serialized)

    def test_unknown_records_and_notebook(self):
        self.transcript([self.user(), {"type": "future-type", "message": "ignored"},
            self.call(name="NotebookEdit", path="a.ipynb"), self.result()])
        report = parse(self.source)
        self.assertEqual(report.record_types["future-type"], 1)
        self.assertEqual(self.edits(report)[0].op, "notebook")

    def test_result_pairing_is_source_local_and_nested_is_inventoried(self):
        self.transcript([self.user(), self.call()])
        nested = self.source.with_suffix("") / "subagents" / "agent.jsonl"
        nested.parent.mkdir(parents=True)
        nested.write_text(json.dumps(self.result()) + "\n")
        main, children = discover(self.sessions)
        self.assertEqual(main, [self.source])
        self.assertEqual(children, [nested])
        self.assertEqual(self.edits(parse(self.source))[0].outcome, "unknown")
