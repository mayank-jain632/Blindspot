"""Measure a synthetic collector/HTTP workload without touching pilot data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import resource
import secrets
import subprocess
import sys
import tempfile
import threading
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from blindspot.observer.server import make_server
from blindspot.observer.store import digest
from blindspot.observer.sqlite_store import SQLiteStore


def benchmark() -> dict:
    with tempfile.TemporaryDirectory(prefix="blindspot-benchmark-") as temporary:
        base = Path(temporary).resolve()
        workspace = base / "workspace"; workspace.mkdir()
        journal = SQLiteStore(base / "state", workspace)
        token = secrets.token_urlsafe(32)
        server = make_server(journal, token, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        cpu = time.process_time()
        try:
            config = {"workspace": str(workspace), "endpoint": f"http://127.0.0.1:{server.server_address[1]}", "token": token}
            result = subprocess.run(["node", str(PROJECT / "scripts/benchmark_observer.js")], input=json.dumps(config), capture_output=True, text=True, timeout=45, cwd=PROJECT)
            if result.returncode:
                raise RuntimeError(result.stderr)
            client = json.loads(result.stdout)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        receiver_cpu_ms = (time.process_time() - cpu) * 1000
        before = time.perf_counter(); report = journal.report(); report_ms = (time.perf_counter() - before) * 1000
        report_bytes = len(json.dumps(report).encode())
        before = time.perf_counter(); replay = SQLiteStore(base / "state", workspace); replay_ms = (time.perf_counter() - before) * 1000
        # Integrity gates: persisted count/order, exact hashes/time, clean end, replay.
        assert len(journal.events) == client["load"]["generated_events"], "Event loss"
        assert [event["sequence"] for event in journal.events] == list(range(len(journal.events))), "Sequence discontinuity"
        assert len(journal.sessions) == 1 and report["sessions"][0]["status"] == "ended", "Incomplete recording"
        snapshots = [event for event in journal.events if event["kind"] == "snapshot"]
        assert len(snapshots) == client["load"]["generated_snapshots"]
        assert all(event["payload"]["content_hash"] == digest(event["payload"]["text"]) for event in snapshots), "Source/hash mismatch"
        assert abs(sum(version["display_ms"] for version in report["displayed_versions"]) - client["load"]["generated_display_ms"]) < .001, "Display-time mismatch"
        assert replay.events == journal.events, "Replay mismatch"
        assert list(workspace.iterdir()) == [], "Observed workspace modified"
        replay.close()
        journal.close()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {
            "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": {"platform": platform.system(), "machine": platform.machine(), "python": platform.python_version(), "node": subprocess.check_output(["node", "--version"], text=True).strip(), "collector_version": json.loads((PROJECT / "extension/package.json").read_text())["version"]},
            "scope": "Synthetic Collector + Transport + real Python HTTP receiver, temporary empty workspace; no VS Code host, filesystem inventory, or browser rendering.",
            **client,
            "receiver": {"cpu_ms": receiver_cpu_ms, "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024, "ingestion_metrics": report["ingestion_metrics"], "journal_bytes": journal.path.stat().st_size, "metadata_report_bytes": report_bytes, "report_build_ms": report_ms, "replay_ms": replay_ms},
            "integrity": {"event_count_and_sequence": "passed", "snapshot_hashes": "passed", "display_time": "passed", "replay": "passed", "workspace_unchanged": "passed"},
            "limits": ["Synthetic load does not establish desktop typing latency or actual editor visibility.", "Callback spacing is requested, not fixed-rate scheduling; event-loop delay includes its 10 ms sampling baseline.", "RSS includes runtime overhead; receiver peak is process lifetime high-water mark.", "No performance acceptance threshold has been chosen; timings vary by machine and load.", "Source text and authentication tokens are omitted from this report."]
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON metrics file; keep outside the observed pilot")
    args = parser.parse_args()
    result = benchmark()
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
