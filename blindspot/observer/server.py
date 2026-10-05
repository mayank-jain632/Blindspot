from __future__ import annotations

import fcntl
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import uuid
from urllib.parse import urlparse, parse_qs

from .store import Journal, SessionUnavailable, STALE_SECONDS
from .sqlite_store import SQLiteStore

ASSETS = Path(__file__).parent / "web"
DASHBOARD_ASSETS = Path(__file__).parent / "dashboard_dist"
MAX_BODY = 2 * 1024 * 1024


def make_server(journal: Journal, token: str, port: int = 7777, *, review_directory: Path | None = None) -> ThreadingHTTPServer:
    from .dashboard import Dashboard
    from ..review import ReviewError
    from ..scan.repo import RepoError
    dashboard = Dashboard(journal, review_directory) if isinstance(journal, SQLiteStore) else None
    receiver_id = str(uuid.uuid4())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type="application/json", cookie=False):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header("Set-Cookie", f"blindspot={token}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)

        def valid_origin(self):
            host = self.headers.get("Host", "")
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
            origin = self.headers.get("Origin")
            return host in allowed and (origin is None or origin in {f"http://{h}" for h in allowed})

        def parse_request(self):
            if not super().parse_request(): return False
            if not self.valid_origin():
                self.reply(403, {"error": "Loopback host/origin required"})
                return False
            return True

        def authenticated(self):
            bearer = self.headers.get("Authorization", "")
            if hmac.compare_digest(bearer.encode("utf-8"), ("Bearer " + token).encode("ascii")):
                return True
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                return "blindspot" in cookie and hmac.compare_digest(cookie["blindspot"].value.encode("utf-8"), token.encode("ascii"))
            except Exception:
                return False

        def do_GET(self):
            if not self.valid_origin():
                return self.reply(403, {"error": "Loopback host/origin required"})
            parsed = urlparse(self.path)
            if dashboard and parsed.path.startswith("/api/dashboard"):
                try:
                    query = parse_qs(parsed.query)
                    if parsed.path == "/api/dashboard": return self.reply(200, dashboard.overview())
                    if parsed.path == "/api/dashboard/source":
                        return self.reply(200, dashboard.source(query.get("path", [""])[0], query.get("hash", [""])[0]))
                    if parsed.path == "/api/dashboard/guide":
                        return self.reply(200, dashboard.guide(query.get("path", [""])[0], query.get("hash", [""])[0]))
                    if parsed.path in {"/api/dashboard/review/attempt", "/api/dashboard/review/results"}:
                        return self.reply(200, dashboard.review_get(parsed.path.rsplit("/", 1)[-1], query.get("attempt_id", [""])[0]))
                    return self.reply(404, {"error": "Not found"})
                except (ValueError, ReviewError, RepoError, OSError, sqlite3.Error) as exc:
                    return self.reply(409, {"error": str(exc)})
            if dashboard and parsed.path == "/" and (DASHBOARD_ASSETS / "index.html").is_file():
                return self.reply(200, (DASHBOARD_ASSETS / "index.html").read_bytes(), "text/html; charset=utf-8", cookie=True)
            if parsed.path.startswith(("/assets/", "/fonts/", "/licenses/")):
                asset = (DASHBOARD_ASSETS / parsed.path.lstrip("/")).resolve()
                if asset.is_relative_to(DASHBOARD_ASSETS.resolve()) and asset.is_file():
                    return self.reply(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
                return self.reply(404, {"error": "Asset not found"})
            if parsed.path in {"/", "/inspector", "/app.js", "/style.css"}:
                name, mime = {"/": ("index.html", "text/html; charset=utf-8"), "/inspector": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}[parsed.path]
                return self.reply(200, (ASSETS / name).read_bytes(), mime, cookie=parsed.path in {"/", "/inspector"})
            if not self.authenticated():
                return self.reply(401, {"error": "Authentication required"})
            if parsed.path == "/api/health":
                if journal.write_failed:
                    return self.reply(503, {"error": "Receiver storage failed; resolve storage error and restart", "code": "storage_failure"})
                return self.reply(200, {"workspace": str(journal.workspace), "schema_version": 1, "receiver_id": receiver_id,
                                        "capabilities": {"batch_events": True, "heartbeat": True, "pane_events": isinstance(journal, SQLiteStore), "overview": isinstance(journal, SQLiteStore)}, "stale_after_ms": STALE_SECONDS * 1000})
            if parsed.path == "/api/report":
                return self.reply(200, {**journal.report(), "receiver": {"id": receiver_id, "status": "storage_failed" if journal.write_failed else "available", "stale_after_ms": STALE_SECONDS * 1000}})
            if parsed.path == "/api/overview":
                if not hasattr(journal, "overview"): return self.reply(409, {"error": "Restart the receiver with SQLite storage to load the overview"})
                try:
                    query = parse_qs(parsed.query)
                    return self.reply(200, {**journal.overview(float(query.get("dwell_ms", [1000])[0])), "receiver": {"id": receiver_id, "status": "storage_failed" if journal.write_failed else "available"}})
                except (ValueError, OSError, sqlite3.Error) as exc: return self.reply(400, {"error": str(exc)})
            if parsed.path == "/api/current-source":
                if not isinstance(journal, SQLiteStore): return self.reply(409, {"error": "Restart the receiver with SQLite storage"})
                from .visibility import current_source
                query = parse_qs(parsed.query)
                try:
                    return self.reply(200, current_source(journal, query.get("path", [""])[0], query.get("hash", [""])[0]))
                except (ValueError, OSError, sqlite3.Error) as exc: return self.reply(409, {"error": str(exc)})
            if parsed.path == "/api/source":
                query = parse_qs(parsed.query)
                with journal.lock:
                    version = journal.versions.get((query.get("path", [""])[0], query.get("hash", [""])[0]))
                    return self.reply(200 if version else 404, version or {"error": "Version not found"})
            return self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if dashboard and self.path in {"/api/dashboard/review/start", "/api/dashboard/review/answer", "/api/dashboard/review/complete"}:
                # Browser mutations require an explicit local Origin. Collector
                # authentication and its origin-less extension requests stay separate.
                if not self.valid_origin() or not self.headers.get("Origin"):
                    return self.reply(403, {"error": "Explicit loopback Origin required"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= MAX_BODY: return self.reply(413, {"error": "Request exceeds size limit"})
                    self.connection.settimeout(5)
                    body = json.loads(self.rfile.read(length))
                    return self.reply(200, dashboard.review_post(self.path.rsplit("/", 1)[-1], body))
                except (ValueError, TypeError, KeyError, ReviewError, RepoError) as exc:
                    return self.reply(409, {"error": str(exc)})
                except (OSError, sqlite3.Error):
                    return self.reply(503, {"error": "Local storage unavailable"})
            if not self.valid_origin() or not self.authenticated():
                return self.reply(403, {"error": "Local authenticated client required"})
            if self.path not in {"/api/events", "/api/events/batch", "/api/heartbeat"}:
                return self.reply(404, {"error": "Not found"})
            expected = self.headers.get("X-Blindspot-Receiver")
            if expected is not None and expected != receiver_id:
                return self.reply(409, {"error": "Receiver restarted; start a new session", "code": "receiver_changed"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.reply(413, {"error": "Event exceeds size limit"})
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/heartbeat":
                    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1 or data.get("workspace") != str(journal.workspace) or not isinstance(data.get("session_id"), str):
                        raise ValueError("Invalid heartbeat workspace/session")
                    journal.touch(data["session_id"])
                    return self.reply(200, {"accepted": True, "receiver_id": receiver_id})
                if self.path == "/api/events/batch":
                    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
                        raise ValueError("Invalid batch envelope")
                    result = journal.append_many(data.get("events"))
                    return self.reply(200, {"accepted": True, "received": len(data["events"]), **result, "receiver_id": receiver_id})
                added = journal.append(data)
                return self.reply(200, {"accepted": True, "duplicate": not added, "receiver_id": receiver_id})
            except SessionUnavailable as exc:
                return self.reply(409, {"error": str(exc), "code": "session_unavailable", "diagnostics": exc.diagnostics})
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                return self.reply(400, {"error": str(exc)})
            except OSError:
                return self.reply(503, {"error": "Receiver could not persist event; stop recording", "code": "storage_failure"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(directory: Path, workspace: Path, port: int, review_directory: Path | None = None) -> None:
    directory = directory.expanduser().resolve()
    workspace = workspace.expanduser().resolve(strict=True)
    if directory == workspace or workspace in directory.parents:
        raise ValueError("Observer state must be outside the observed workspace")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("An observer receiver is already using this state directory") from None
        journal = SQLiteStore(directory, workspace)
        token = secrets.token_urlsafe(32)
        try:
            server = make_server(journal, token, port, review_directory=review_directory)
        except Exception:
            journal.close()
            raise
        connection = directory / "connection.json"
        temp = directory / "connection.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as target:
            json.dump({"endpoint": f"http://127.0.0.1:{server.server_address[1]}", "token": token}, target)
        temp.replace(connection)
        print(f"Observer: http://127.0.0.1:{server.server_address[1]}", flush=True)
        print(f"Workspace: {workspace}\nConnection file: {connection}\nSource snapshots stay in this local state directory.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            connection.unlink(missing_ok=True)
            journal.close()
