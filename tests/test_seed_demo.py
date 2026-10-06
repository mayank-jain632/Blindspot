from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from blindspot.observer.dashboard import Dashboard
from blindspot.observer.sqlite_store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]


class SeedDemoTests(unittest.TestCase):
    def test_seed_builds_a_mixed_demo_with_one_quiz(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "demo"
            subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "seed_demo.py"), "--out", str(out)], check=True, capture_output=True)
            store = SQLiteStore(out / "state", (out / "project").resolve())
            try:
                data = Dashboard(store, out / "state").overview()
            finally:
                store.close()
            states = {f["path"]: f["state"] for f in data["files"]}
            self.assertEqual(states["catalog.py"], "reported")
            self.assertEqual(states["notifications.py"], "no_evidence")
            self.assertEqual(states["loans.py"], "partial")
            self.assertEqual(data["review"]["confidently_wrong_files"], 1)
            self.assertGreaterEqual(len(data["weekly"]), 2)
            refused = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "seed_demo.py"), "--out", str(out)], capture_output=True)
            self.assertNotEqual(refused.returncode, 0)  # never overwrites without --force
