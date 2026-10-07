"""Smoke-test the installed wheel outside the repository, then dispose its state."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="blindspot-release-") as temporary:
        base = Path(temporary).resolve()
        venv.create(base / "venv", with_pip=True)
        python = base / "venv/bin/python"
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(ROOT / "dist/blindspot_local-0.4.0-py3-none-any.whl")], cwd=base, check=True)
        project = base / "project"
        project.mkdir()
        (project / "sample.py").write_text("def total(values):\n    return sum(values)\n")
        subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
        state = base / "state"
        process = subprocess.Popen([str(base / "venv/bin/blindspot"), "observer", "serve", "--workspace", str(project), "--state-dir", str(state), "--port", "0"], cwd=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if (state / "connection.json").exists(): break
                if process.poll() is not None: raise RuntimeError(process.communicate())
                time.sleep(.1)
            connection = json.loads((state / "connection.json").read_text())
            url = connection["endpoint"]
            html = urlopen(url).read().decode()
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
            assert assets, "Built dashboard missing"
            for asset in assets: assert urlopen(url + asset).status == 200
            data = json.load(urlopen(url + "/api/dashboard"))
            assert not data["has_observations"] and len(data["files"]) == 1
            for headers, route, body in [({"Host": "attacker.example"}, "/", None), ({"Origin": "https://attacker.example"}, "/api/dashboard/review/start", b'{}')]:
                try: urlopen(Request(url + route, data=body, headers=headers))
                except HTTPError as error: assert error.code == 403
                else: raise AssertionError("Loopback boundary not enforced")
            print("Installed wheel smoke check passed: isolated CLI, dashboard assets, first run, Host/Origin rejection.")
        finally:
            process.terminate()
            try: process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate()


if __name__ == "__main__":
    main()
