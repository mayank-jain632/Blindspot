from datetime import datetime, timezone
import uuid

from blindspot.observer.dashboard import Dashboard
from blindspot.observer.guide import blame, build, extract
from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.store import digest
from .support import SandboxCase

PY = '''"""Retry helpers."""
import time
from . import util

LIMIT = 3


@util.cached
def retry(fn, attempts: int = LIMIT) -> int:
    """Call fn until it works."""
    for _ in range(attempts):
        try:
            return fn()
        except ValueError:
            time.sleep(1)
    raise RuntimeError("gave up")


class Client:
    """Talks to the service."""
    timeout = 5

    def get(self, url):
        if not url:
            raise ValueError("empty")
        return fetch(url)

    async def close(self):
        pass
'''
JS = '''import { a } from './a.js';
export function load(x) {
  return a(x);
}

const save = async (y) => {
  await a(y);
};

class Store {
  put(k, v) {
    this.m[k] = v;
  }
}
'''


def by_name(guide):
    return {i["name"]: i for i in guide["items"]}


class GuideBuildTests(SandboxCase):
    def test_python_units_ranges_and_ownership(self):
        items = by_name(build(PY, "r.py", [[1, 6]]))
        self.assertEqual(set(items), {"retry", "Client", "Client.get", "Client.close", "Top-level code"})
        retry = items["retry"]
        self.assertEqual((retry["start"], retry["end"]), (8, 16))  # decorator line included
        self.assertEqual(retry["doc"], "Call fn until it works.")
        self.assertEqual(retry["raises"], ["RuntimeError"])
        self.assertIn("time.sleep", retry["calls"]); self.assertNotIn("range", retry["calls"])
        self.assertGreaterEqual(retry["branches"], 2)
        client = items["Client"]
        # The class owns its header, docstring and attribute, not its methods.
        self.assertEqual(client["lines"], 3)
        self.assertEqual(items["Client.get"]["kind"], "method")

    def test_unseen_counts_and_states(self):
        guide = build(PY, "r.py", [[8, 16], [19, 22]])
        items = by_name(guide)
        self.assertEqual(items["retry"]["state"], "seen")
        self.assertEqual(items["Client"]["state"], "seen")
        self.assertEqual(items["Client.get"]["state"], "unseen")
        self.assertEqual(items["Client.get"]["unseen_ranges"], [[23, 26]])
        self.assertEqual(items["Top-level code"]["state"], "unseen")
        self.assertEqual(guide["overview"]["units_with_unseen"], 3)  # get, close, top-level code

    def test_partial_state(self):
        guide = build(PY, "r.py", [[8, 12]])
        retry = by_name(guide)["retry"]
        self.assertEqual((retry["state"], retry["unseen"], retry["unseen_ranges"]), ("partial", 4, [[13, 16]]))

    def test_module_gaps_skip_blank_edges(self):
        top = by_name(build(PY, "r.py", []))["Top-level code"]
        self.assertEqual(top["start"], 1)
        self.assertEqual(top["lines"], 5)  # lines 1-5: docstring, imports, blank, LIMIT
        self.assertEqual(build(PY, "r.py", [])["overview"]["doc"], "Retry helpers.")

    def test_overview_imports(self):
        overview = build(PY, "r.py", [])["overview"]
        self.assertEqual(overview["imports"], ["time", ".util"])

    def test_uncertain_boundaries_use_conservative_blocks(self):
        for text, name in [("def ok(x):\n    return x\n\ndef broken(:\n", "bad.py"),
                           (JS, "s.js"),
                           ('function f() {\nreturn "}";\n}\n', "x.js")]:
            guide = build(text, name, [])
            self.assertEqual(guide["parser"], "blocks")
            self.assertTrue(all(i["kind"] == "block" for i in guide["items"]))
            self.assertEqual(sum(i["lines"] for i in guide["items"]), sum(bool(line.strip()) for line in text.splitlines()))
        self.assertEqual(build(JS, "s.js", [])["overview"]["imports"], ["./a.js"])

    def test_markdown_sections_and_fallback_blocks(self):
        md = build("# Title\nintro\n\n## Part\ntext\n", "r.md", [])
        self.assertEqual(md["parser"], "headings")
        self.assertEqual(by_name(md)["Title"]["lines"], 2)  # blank edge clipped; Part is its own unit
        blocks = build('{"a": 1}\n\n{"b": 2}\n', "x.json", [])
        self.assertEqual((blocks["parser"], len(blocks["items"])), ("blocks", 2))

    def test_plain_script_without_definitions_becomes_blocks(self):
        guide = build("import os\nprint(os.name)\n\nx = 1\n", "s.py", [[1, 2]])
        self.assertEqual(guide["parser"], "blocks")
        self.assertEqual([(i["start"], i["end"], i["state"]) for i in guide["items"]], [(1, 2, "seen"), (4, 4, "unseen")])
        self.assertEqual(guide["overview"]["imports"], ["os"])

    def test_unseen_total_matches_dashboard_line_count(self):
        guide = build("x = 1\ny = 2\n", "s.py", [[1, 2]])
        self.assertEqual((guide["line_count"], guide["unseen_lines"]), (2, 0))

    def test_pathological_long_lines_stay_fast(self):
        import time
        started = time.monotonic()
        for text in ("  public " + "\t" * 40000 + "x\n", "public " + "a<b>[] " * 5000 + "(\n", "const " + "a" * 200000 + " = (\n"):
            for name in ("f.java", "f.js", "f.c"): build(text, name, [])
        self.assertLess(time.monotonic() - started, 2)

    def test_empty_and_crlf_text(self):
        self.assertEqual(build("", "e.py", [])["items"], [])
        guide = build("def f():\r\n    return 1\r\n", "w.py", [])
        self.assertEqual(by_name(guide)["f"]["lines"], 2)


class GuideHistoryTests(SandboxCase):
    def test_blame_and_changes_use_last_touching_commit(self):
        old = "def f():\n    return 1\n\ndef g():\n    return 2\n"
        self.commit({"m.py": old}, when="2026-01-01T00:00:00Z")
        self.git("commit", "--allow-empty", "-m", "noop")
        (self.root / "m.py").write_text(old.replace("return 2", "return 3"))
        self.git("add", "-A"); self.git("commit", "-m", "Change g result", when="2026-09-30T00:00:00Z")
        text = (self.root / "m.py").read_text()
        history = blame(self.root, "m.py", len(text.split("\n")))
        guide = build(text, "m.py", [[1, 3]], history, now=datetime(2026, 10, 4, tzinfo=timezone.utc))
        items = by_name(guide)
        self.assertEqual(items["f"]["changes"][0]["summary"], "Synthetic change")
        self.assertFalse(items["f"]["recently_changed"])
        self.assertEqual(items["g"]["changes"][0]["summary"], "Change g result")
        self.assertEqual(items["g"]["changes"][0]["date"], "2026-09-30")
        self.assertTrue(items["g"]["recently_changed"])
        self.assertEqual([c["summary"] for c in guide["recent_changes"]], ["Change g result", "Synthetic change"])
        self.assertEqual(guide["recent_changes"][0]["unseen"], 1)

    def test_uncommitted_and_untracked_lines(self):
        self.commit({"m.py": "def f():\n    return 1\n"})
        (self.root / "m.py").write_text("def f():\n    return 2\n")
        text = (self.root / "m.py").read_text()
        history = blame(self.root, "m.py", len(text.split("\n")))
        item = by_name(build(text, "m.py", [], history))["f"]
        self.assertEqual(item["changes"][0]["summary"], "Uncommitted changes")
        self.assertIsNone(item["changes"][0]["commit"])
        self.assertTrue(item["recently_changed"])
        (self.root / "u.py").write_text("x = 1\n")
        self.assertIsNone(blame(self.root, "u.py", 2))
        self.assertIn("Change history is unavailable", build("x = 1\n", "u.py", [])["notes"][0])


class GuideEndpointTests(SandboxCase):
    def test_dashboard_guide_uses_recorded_display_and_checks_hash(self):
        self.root = self.root.resolve()
        self.commit({"m.py": PY})
        store = SQLiteStore(self.base / "observer", self.root); self.addCleanup(store.close)
        dashboard = Dashboard(store, self.state_dir)
        sid = str(uuid.uuid4()); now = datetime.now(timezone.utc).isoformat()
        def event(sequence, kind, payload, ms=0):
            return {"schema_version": 1, "workspace": str(self.root), "session_id": sid, "sequence": sequence,
                    "observed_at": now, "monotonic_ms": ms, "kind": kind, "payload": payload}
        store.append(event(0, "session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        store.append(event(1, "snapshot", {"path": "m.py", "text": PY, "content_hash": digest(PY), "line_count": len(PY.split("\n")), "origin": "document"}))
        store.append(event(2, "visibility", {"path": "m.py", "content_hash": digest(PY), "ranges": [[8, 16]], "start_ms": 0, "end_ms": 1000,
            "duration_ms": 1000, "focused": True, "focus_scope": "window", "editor_focus": "unverified", "pane_id": "main",
            "active": True, "exposure": "reported-visible"}, 1000))
        guide = dashboard.guide("m.py", digest(PY))
        items = by_name(guide)
        self.assertEqual(items["retry"]["state"], "seen")
        self.assertEqual(items["Client.get"]["state"], "unseen")
        self.assertEqual(items["retry"]["changes"][0]["summary"], "Synthetic change")
        with self.assertRaises(ValueError): dashboard.guide("m.py", "stale")
        with self.assertRaises(ValueError): dashboard.guide("../etc/passwd", digest(PY))
