"""Disposable browser fixture. Never opens the user's recording store."""
import json
import signal
import threading

from blindspot.observer.server import make_server
from tests.test_dashboard import DashboardTests, CODE, NOW


def main():
    populated = DashboardTests(); populated.setUp()
    empty = DashboardTests(); empty.setUp()
    servers = []
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, lambda *_: stopped.set())
    try:
        set_id = populated.quiz()
        store = populated.store
        from blindspot.observer.store import digest
        store.append(populated.event("session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        store.append(populated.event("snapshot", {"path": "a.py", "text": CODE, "content_hash": digest(CODE), "line_count": len(CODE.split('\n')), "origin": "document"}))
        store.append(populated.event("visibility", {"path": "a.py", "content_hash": digest(CODE), "ranges": [[1, 3]], "start_ms": 0, "end_ms": 1000, "duration_ms": 1000, "focused": True,
            "focus_scope": "window", "editor_focus": "unverified", "pane_id": "main", "active": True, "exposure": "reported-visible"}, 1000))
        store.append(populated.event("interaction", {"path": "a.py", "kind": "selection", "cause": "keyboard-event"}, 1000))
        for fixture in (populated, empty):
            server = make_server(fixture.store, "fixture-private-token", 0, review_directory=fixture.state_dir)
            threading.Thread(target=server.serve_forever, daemon=True).start(); servers.append(server)
        print(json.dumps({"url": f"http://127.0.0.1:{servers[0].server_address[1]}",
                          "empty_url": f"http://127.0.0.1:{servers[1].server_address[1]}", "set_id": set_id}), flush=True)
        stopped.wait()
    finally:
        for server in servers: server.shutdown(); server.server_close()
        populated.doCleanups(); empty.doCleanups()


if __name__ == '__main__': main()
