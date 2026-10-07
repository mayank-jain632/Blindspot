"""Disposable seeded project for release screenshots; no existing state is opened."""
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import tempfile
import threading

from blindspot.observer.dashboard import Dashboard
from blindspot.observer.server import make_server
from blindspot.observer.sqlite_store import SQLiteStore
from scripts.seed_demo import add_quiz, build_project, record


def main():
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    with tempfile.TemporaryDirectory(prefix="blindspot-screenshots-") as temporary:
        base = Path(temporary).resolve()
        project = base / "Shelfmark"
        now = datetime.now(timezone.utc)
        build_project(project, now)
        store = SQLiteStore(base / "state", project)
        record(store, project, now)
        add_quiz(Dashboard(store), project, now)
        server = make_server(store, "disposable-screenshot-token", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}"}), flush=True)
        try: stopped.wait()
        finally:
            server.shutdown(); server.server_close(); store.close()


if __name__ == "__main__": main()
