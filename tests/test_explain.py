from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

from blindspot.observer.dashboard import Dashboard
from blindspot.observer.explain import LLMError, Ollama, loopback_url, valid_model
from blindspot.observer.server import make_server
from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.store import digest
from .support import SandboxCase
from .test_guide import PY


class FakeOllama:
    """Minimal stand-in for the Ollama HTTP API."""
    def __init__(self, models=("llama3:8b", "qwen2.5-coder:7b", "nomic-embed-text"), reply="- It fetches the URL (L26)."):
        self.models, self.reply, self.requests = list(models), reply, []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_GET(self):
                self.send(200, {"models": [{"name": m} for m in owner.models]})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(body)
                if body["model"] not in owner.models: return self.send(404, {"error": "model not found"})
                self.send(200, {"message": {"role": "assistant", "content": owner.reply}})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
    def close(self): self.server.shutdown(); self.server.server_close()


class OllamaClientTests(SandboxCase):
    def test_only_loopback_endpoints_are_accepted(self):
        for url in ("http://127.0.0.1:11434", "http://localhost:11434/", "http://[::1]:11434"):
            loopback_url(url)
        for url in ("http://example.com:11434", "http://192.168.1.5:11434", "file:///etc/passwd", "http://user:pw@127.0.0.1", "ftp://127.0.0.1"):
            with self.assertRaises(ValueError): loopback_url(url)

    def test_status_lists_models_and_prefers_a_coder_model(self):
        fake = FakeOllama(); self.addCleanup(fake.close)
        status = Ollama(fake.url).status()
        self.assertTrue(status["available"])
        self.assertEqual(status["models"], ["llama3:8b", "qwen2.5-coder:7b"])  # embedding models are not for chat
        self.assertEqual(status["default"], "qwen2.5-coder:7b")
        self.assertEqual(Ollama(fake.url, "llama3:8b").status()["default"], "llama3:8b")
        self.assertEqual(Ollama(fake.url, "missing").status()["default"], "qwen2.5-coder:7b")

    def test_status_reports_not_running_and_no_models(self):
        self.assertFalse(Ollama("http://127.0.0.1:1").status()["available"])
        self.assertIn("not running", Ollama("http://127.0.0.1:1").status()["error"])
        fake = FakeOllama(models=()); self.addCleanup(fake.close)
        status = Ollama(fake.url).status()
        self.assertFalse(status["available"]); self.assertIn("no models", status["error"])

    def test_chat_errors_are_readable_and_think_blocks_removed(self):
        fake = FakeOllama(reply="<think>private reasoning</think>\nAnswer"); self.addCleanup(fake.close)
        client = Ollama(fake.url)
        self.assertEqual(client.chat("llama3:8b", "s", "u"), "Answer")
        with self.assertRaisesRegex(LLMError, "ollama pull nope"): client.chat("nope", "s", "u")
        with self.assertRaisesRegex(LLMError, "not running"): Ollama("http://127.0.0.1:1").chat("llama3:8b", "s", "u")
        with self.assertRaises(LLMError): valid_model("bad model; rm -rf")
        fake.reply = "<think>only thoughts</think>"
        with self.assertRaisesRegex(LLMError, "nothing"): client.chat("llama3:8b", "s", "u")


class ExplainTests(SandboxCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.commit({"m.py": PY})
        self.fake = FakeOllama(); self.addCleanup(self.fake.close)
        self.store = SQLiteStore(self.base / "observer", self.root); self.addCleanup(self.store.close)
        self.dashboard = Dashboard(self.store, self.state_dir, Ollama(self.fake.url))
        sid = str(uuid.uuid4()); now = datetime.now(timezone.utc).isoformat()
        def event(sequence, kind, payload, ms=0):
            return {"schema_version": 1, "workspace": str(self.root), "session_id": sid, "sequence": sequence,
                    "observed_at": now, "monotonic_ms": ms, "kind": kind, "payload": payload}
        self.store.append(event(0, "session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        self.store.append(event(1, "snapshot", {"path": "m.py", "text": PY, "content_hash": digest(PY), "line_count": len(PY.split("\n")), "origin": "document"}))
        self.store.append(event(2, "visibility", {"path": "m.py", "content_hash": digest(PY), "ranges": [[8, 16]], "start_ms": 0, "end_ms": 1000,
            "duration_ms": 1000, "focused": True, "focus_scope": "window", "editor_focus": "unverified", "pane_id": "main",
            "active": True, "exposure": "reported-visible"}, 1000))
        self.hash = digest(PY)

    def ask(self, **extra):
        return self.dashboard.explain({"path": "m.py", "hash": self.hash, **extra})

    def test_unit_prompt_contains_only_that_unit_and_the_gap(self):
        result = self.ask(start=23, end=26)
        self.assertEqual((result["scope"], result["cached"], result["model"]), ("unit", False, "qwen2.5-coder:7b"))
        self.assertIn("fetches the URL", result["text"])
        sent = self.fake.requests[0]
        user = sent["messages"][1]["content"]
        self.assertEqual(sent["stream"], False)
        self.assertIn("Never on screen: 23-26 (4 of 4 lines)", user)
        self.assertIn("raise ValueError", user)
        self.assertNotIn("time.sleep", user)  # retry() was not requested
        self.assertNotIn("LIMIT", user)
        self.assertIn("Last changed:", user)

    def test_class_prompt_uses_only_its_own_lines(self):
        self.ask(start=19, end=29)
        user = self.fake.requests[0]["messages"][1]["content"]
        self.assertIn("class Client", user)
        self.assertNotIn("def get", user)  # methods are separate units

    def test_cache_hits_regenerate_and_invalidation(self):
        first = self.ask(start=23, end=26)
        second = self.ask(start=23, end=26)
        self.assertTrue(second["cached"]); self.assertEqual(second["text"], first["text"]); self.assertEqual(len(self.fake.requests), 1)
        self.assertFalse(self.ask(start=23, end=26, regenerate=True)["cached"]); self.assertEqual(len(self.fake.requests), 2)
        self.assertFalse(self.ask(start=23, end=26, model="llama3:8b")["cached"])  # another model is another answer
        self.assertTrue((self.store.directory / "explanations.json").is_file())

    def test_file_summary_sends_an_outline_not_code(self):
        result = self.ask()
        self.assertEqual(result["scope"], "file")
        user = self.fake.requests[0]["messages"][1]["content"]
        self.assertIn("Client.get", user); self.assertIn("Retry helpers.", user)
        self.assertNotIn("raise ValueError", user)

    def test_invalid_requests_never_reach_the_model(self):
        for body in ({"start": 1, "end": 2}, {"start": 23}, {"start": "23", "end": 26}, {"extra": 1}):
            with self.assertRaises(ValueError): self.ask(**body)
        with self.assertRaises(ValueError): self.dashboard.explain({"path": "m.py", "hash": "stale"})
        with self.assertRaises(ValueError): self.dashboard.explain([])
        with self.assertRaises(LLMError): self.ask(model="bad name!")
        self.assertEqual(self.fake.requests, [])

    def test_http_endpoints_require_a_local_origin_and_map_model_errors(self):
        server = make_server(self.store, "token", 0, review_directory=self.state_dir, ollama=Ollama(self.fake.url))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        def post(body, origin=True):
            headers = {"Content-Type": "application/json", **({"Origin": endpoint} if origin else {})}
            return urlopen(Request(endpoint + "/api/dashboard/explain", data=json.dumps(body).encode(), headers=headers), timeout=10)
        with urlopen(endpoint + "/api/dashboard/explain/status", timeout=5) as response:
            self.assertEqual(json.load(response)["default"], "qwen2.5-coder:7b")
        with self.assertRaises(HTTPError) as error: post({"path": "m.py", "hash": self.hash}, origin=False)
        self.assertEqual(error.exception.code, 403)
        with post({"path": "m.py", "hash": self.hash, "start": 23, "end": 26}) as response:
            self.assertIn("fetches", json.load(response)["text"])
        with self.assertRaises(HTTPError) as error: post({"path": "m.py", "hash": self.hash, "model": "not-installed"})
        self.assertEqual(error.exception.code, 502)
        self.assertIn("ollama pull not-installed", json.loads(error.exception.read())["error"])
