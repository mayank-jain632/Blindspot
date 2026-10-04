"""Exercise real Node collector/transport against the Python loopback receiver."""
from pathlib import Path
import json
import shutil
import selectors
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uuid

from blindspot.observer.server import make_server
from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.store import digest


@unittest.skipUnless(shutil.which("node"), "Node required for cross-language pilot test")
class ObserverIntegrationTest(unittest.TestCase):
    def test_automatic_recovery_after_real_receiver_restart_and_token_rotation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            workspace = base / "workspace"; workspace.mkdir()
            fixture = workspace / "a.py"; fixture.write_text("one\ntwo\nthree")
            subprocess.run(["git", "init", str(workspace)], check=True, capture_output=True)
            before = fixture.read_bytes()
            state = base / "state"
            journal = SQLiteStore(state, workspace)
            token = "original-token-" * 4
            server = make_server(journal, token, 0)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            connection = base / "connection.json"
            config = {"endpoint": f"http://127.0.0.1:{port}", "token": token}
            connection.write_text(json.dumps(config))
            config.update(workspace=str(workspace), connection_file=str(connection), mode="recovery")
            project = Path(__file__).resolve().parents[1]
            child = subprocess.Popen(["node", "tests/fixtures/observer_extension_host.js"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=project)
            child.stdin.write(json.dumps(config)); child.stdin.close(); child.stdin = None
            def stage(expected):
                with selectors.DefaultSelector() as selector:
                    selector.register(child.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(timeout=15), f"No {expected} stage")
                line = child.stdout.readline()
                if not line:
                    self.fail(child.stderr.read())
                self.assertEqual(json.loads(line)["stage"], expected)
            try:
                stage("ready")
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                stage("disconnected")
                # Exercise failed fetch in recovery itself, not just the initial disconnect.
                time.sleep(2.5)
                journal.close()
                journal = SQLiteStore(state, workspace)
                server = make_server(journal, "rotated-token-" * 4, port)
                new_config = {"endpoint": config["endpoint"], "token": "rotated-token-" * 4}
                temporary = base / "connection.tmp"; temporary.write_text(json.dumps(new_config)); temporary.replace(connection)
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                stage("done")
                _, errors = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, errors)
                report = journal.report()
                self.assertEqual(report["event_counts"]["recording_gap"], 1)
                self.assertEqual(report["event_counts"]["session_start"], 2)
                self.assertEqual(report["event_counts"]["session_end"], 1)
                self.assertEqual(len({s["session_id"] for s in report["sessions"]}), 2)
                self.assertTrue(report["recording_gaps"][0]["duration_uncertain"])
                self.assertEqual(fixture.read_bytes(), before)
            finally:
                if child.poll() is None: child.kill()
                child.communicate(timeout=5)
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                journal.close()

    def test_extension_stop_start_cycles_against_real_receiver(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            workspace = base / "workspace"; workspace.mkdir()
            fixture = workspace / "a.py"
            fixture.write_text("one\ntwo\nthree")
            passive = workspace / "b.py"; passive.write_text("passive\nsource\nlines")
            subprocess.run(["git", "init", str(workspace)], check=True, capture_output=True)
            before = fixture.read_bytes()
            journal = SQLiteStore(base / "state", workspace)
            token = "extension-test-token-" * 3
            server = make_server(journal, token, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            config = {"endpoint": f"http://127.0.0.1:{server.server_address[1]}", "token": token}
            connection = base / "connection.json"
            connection.write_text(json.dumps(config))
            config.update(workspace=str(workspace), connection_file=str(connection))
            project = Path(__file__).resolve().parents[1]
            try:
                result = subprocess.run(["node", "tests/fixtures/observer_extension_host.js"], input=json.dumps(config), text=True,
                                        capture_output=True, timeout=15, cwd=project)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["sessions"], 3)
                report = journal.report()
                self.assertEqual(report["event_counts"]["session_start"], 3)
                self.assertEqual(report["event_counts"]["session_end"], 3)
                self.assertEqual(report["event_counts"]["state"], 6)
                self.assertEqual(len({session["session_id"] for session in report["sessions"]}), 3)
                for session in report["sessions"]:
                    events = [e for e in report["events"] if e["session_id"] == session["session_id"]]
                    self.assertEqual([e["sequence"] for e in events], list(range(len(events))))
                    self.assertTrue(any(e["kind"] == "visibility" for e in events))
                    self.assertEqual(events[0]["payload"]["collector_version"], json.loads((project / "extension/package.json").read_text())["version"])
                    self.assertEqual(events[-1]["kind"], "session_end")
                self.assertEqual(fixture.read_bytes(), before)
                self.assertTrue(any(e["kind"] == "visibility" and e["payload"].get("path") == "b.py" and not e["payload"]["active"] for e in report["events"]))
                self.assertEqual(passive.read_text(), "passive\nsource\nlines")
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                journal.close()

    def test_cli_connection_writer_lock_shutdown_and_offline_report(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            workspace = base / "workspace"; workspace.mkdir()
            state = base / "state"
            project = Path(__file__).resolve().parents[1]
            command = [sys.executable, "-B", "-m", "blindspot", "observer", "serve", "--workspace", str(workspace), "--state-dir", str(state), "--port", "0"]
            receiver = subprocess.Popen(command, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                connection = state / "connection.json"
                while not connection.exists() and time.monotonic() < deadline and receiver.poll() is None:
                    time.sleep(0.03)
                self.assertTrue(connection.exists(), "CLI did not publish connection file")
                self.assertEqual(connection.stat().st_mode & 0o777, 0o600)
                config = json.loads(connection.read_text())
                duplicate = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=5)
                self.assertEqual(duplicate.returncode, 2)
                self.assertIn("already using", duplicate.stderr)
                session_id = str(uuid.uuid4())
                for sequence, kind, payload in [(0, "session_start", {"mode": "active-editor-reported-ranges"}), (1, "session_end", {})]:
                    event = {"schema_version": 1, "session_id": session_id, "sequence": sequence, "workspace": str(workspace), "observed_at": "2026-10-03T10:00:00+00:00", "monotonic_ms": sequence, "kind": kind, "payload": payload}
                    request = Request(config["endpoint"] + "/api/events", data=json.dumps(event).encode(), headers={"Authorization": "Bearer " + config["token"], "Content-Type": "application/json"})
                    with urlopen(request, timeout=3) as response:
                        self.assertTrue(json.load(response)["accepted"])
                receiver.send_signal(signal.SIGINT)
                output, errors = receiver.communicate(timeout=5)
                self.assertEqual(receiver.returncode, 0, errors)
                self.assertFalse(connection.exists())
                report = subprocess.run([sys.executable, "-B", "-m", "blindspot", "observer", "report", "--workspace", str(workspace), "--state-dir", str(state)], cwd=project, capture_output=True, text=True, timeout=5)
                self.assertEqual(report.returncode, 0, report.stderr)
                self.assertEqual(json.loads(report.stdout)["event_counts"], {"session_start": 1, "session_end": 1})
                self.assertEqual(list(workspace.iterdir()), [])
            finally:
                if receiver.poll() is None:
                    receiver.kill()
                receiver.communicate(timeout=5)

    def test_sqlite_overview_and_current_source_http_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve(); workspace = base / "workspace"; workspace.mkdir()
            subprocess.run(["git", "init", str(workspace)], check=True, capture_output=True)
            source = workspace / "a.py"; source.write_text("one\ntwo")
            journal = SQLiteStore(base / "state", workspace)
            server = make_server(journal, "private-token", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            endpoint = f"http://127.0.0.1:{server.server_address[1]}"
            def get(route, headers=None):
                with urlopen(Request(endpoint + route, headers=headers or {"Authorization": "Bearer private-token"}), timeout=3) as response: return json.load(response)
            try:
                self.assertTrue(get("/api/health")["capabilities"]["overview"])
                overview = get("/api/overview?dwell_ms=1000")
                self.assertEqual(overview["totals"]["unknown_lines"], 2)
                self.assertEqual(overview["health"]["storage"]["kind"], "sqlite")
                route = "/api/current-source?path=a.py&hash=" + digest("one\ntwo")
                self.assertEqual(get(route)["text"], "one\ntwo")
                with self.assertRaises(HTTPError) as error: get(route, {"Authorization": "Bearer wrong"})
                self.assertEqual(error.exception.code, 401)
                with self.assertRaises(HTTPError) as error: get("/api/overview?dwell_ms=NaN")
                self.assertEqual(error.exception.code, 400)
                source.write_text("changed")
                with self.assertRaises(HTTPError) as error: get(route)
                self.assertEqual(error.exception.code, 409)
                with self.assertRaises(HTTPError): get("/api/current-source?path=../secret.py&hash=" + digest("changed"))
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3); journal.close()

    def test_node_to_receiver_version_focus_pause_and_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            workspace = base / "workspace"; workspace.mkdir()
            journal = SQLiteStore(base / "state", workspace)
            token = "integration-token-" * 3
            server = make_server(journal, token, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            config = {"endpoint": f"http://127.0.0.1:{server.server_address[1]}", "token": token, "workspace": str(workspace)}
            script = r'''
const fs=require('node:fs');
const {Collector}=require('./extension/core');
const {Transport}=require('./extension/transport');
const config=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
  let lostAck=false;
  const transport=new Transport(config,error=>{throw error;},async(url,options)=>{
    const response=await fetch(url,options);
    if(url.endsWith('/api/events/batch')&&!lostAck) {lostAck=true;throw new Error('Simulated lost acknowledgement after persistence');}
    return response;
  });
  await transport.health();
  let clock=0;
  const collector=new Collector(config.workspace,e=>transport.enqueue(e),()=>clock);
  const show=text=>collector.setView({path:'visible.py',text,focused:true,ranges:[[1,2]]});
  show('one\ntwo\nthree'); clock=1000; collector.tick();
  clock=1250; collector.setView(null); clock=5000; collector.tick();
  clock=5500; show('one\ntwo\nthree');clock=6000;collector.pause();
  clock=9000;collector.resume();show('changed\ntwo\nthree');clock=10000;collector.tick();
  clock=20000;collector.tick();clock=21000;collector.stop();
  await transport.drain();
  if(transport.failed) process.exitCode=1;
})().catch(error=>{process.stderr.write(error.message);process.exitCode=1;});
'''
            try:
                result = subprocess.run(["node", "-e", script], input=json.dumps(config), text=True,
                                        capture_output=True, timeout=15, cwd=Path(__file__).resolve().parents[1])
                self.assertEqual(result.returncode, 0, result.stderr)
                report = journal.report()
                self.assertEqual(report["event_counts"]["session_end"], 1)
                self.assertEqual(report["ingestion_metrics"]["duplicate_events"], 1)
                self.assertLess(report["ingestion_metrics"]["transactions"], len(report["events"]))
                self.assertEqual(len(report["displayed_versions"]), 2)
                self.assertEqual([v["display_ms"] for v in report["displayed_versions"]], [1750, 2000])
                self.assertEqual([e["payload"]["reason"] for e in report["events"] if e["kind"] == "diagnostic"], ["sampling_gap", "sampling_gap"])
                self.assertEqual(list(workspace.iterdir()), [])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                journal.close()


if __name__ == "__main__":
    unittest.main()
