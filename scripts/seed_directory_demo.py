"""Create an isolated, explicitly synthetic directory-map demo. Never overwrite it."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import seed_demo as seed
from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.server import serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("sandbox/directory-demo"))
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    base = args.output.resolve()
    project, state = base / "Shelfmark", base / "state"
    if base.exists():
        if not args.serve:
            parser.error("Demo already exists. Choose a new --output; existing data is never overwritten.")
        if not (project / ".git").exists() or not (state / "observations.sqlite3").exists():
            parser.error("Existing output is not a prepared demo. Choose a new --output.")
    else:
        paths = {"catalog.py": "src/catalog/models.py", "search.py": "src/catalog/search.py",
                 "loans.py": "src/loans/ledger.py", "notifications.py": "src/loans/reminders.py",
                 "fines.py": "src/billing/fines.py", "cli.py": "src/cli.py",
                 "web/api.js": "src/web/api.js", "web/cache.js": "src/web/cache.js", "README.md": "README.md"}
        seed.FILES = {paths[name]: text for name, text in seed.FILES.items()}
        seed.FILES["src/cli.py"] = seed.FILES["src/cli.py"].replace("from catalog import", "from src.catalog.models import").replace("from loans import", "from src.loans.ledger import").replace("from search import", "from src.catalog.search import")
        seed.FILES["README.md"] = "# Shelfmark demo\n\nSynthetic example: initial display observations are seeded, not a real user's history.\n\nRun: `python3 -m src.cli find pragmatic`\n"
        seed.SEEN = {paths[name]: ranges for name, ranges in seed.SEEN.items()}
        seed.SESSIONS = [(days, [paths[name] for name in names]) for days, names in seed.SESSIONS]
        seed.COMMITS = [(days, [paths[name] for name in names], message) for days, names, message in seed.COMMITS]
        seed.EDITS = {index: [(paths[name], new, old) for name, new, old in edits] for index, edits in seed.EDITS.items()}
        now = datetime.now(timezone.utc)
        seed.build_project(project, now)
        tests = {
            "tests/test_billing.py": "import unittest\nfrom src.billing.fines import summarize\n\nclass BillingTest(unittest.TestCase):\n    def test_empty(self):\n        self.assertEqual(summarize([])['total_cents'], 0)\n",
            "tests/test_catalog.py": "import unittest\nfrom src.catalog.models import valid_isbn\n\nclass CatalogTest(unittest.TestCase):\n    def test_isbn(self):\n        self.assertTrue(valid_isbn('9780306406157'))\n",
        }
        for name, text in tests.items():
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        seed.git(project, "add", ".")
        seed.git(project, "commit", "-m", "Add demo checks")
        store = SQLiteStore(state, project)
        try: seed.record(store, project, now)
        finally: store.close()
    print(f"Seeded demonstration data, not measured personal history.\nProject: {project}\nState: {state}", flush=True)
    if args.serve:
        serve(state, project, 0)


if __name__ == "__main__": main()
