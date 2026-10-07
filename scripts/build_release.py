"""Build local release artifacts. Does not publish or upload anything."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)


def main():
    run("npm", "--prefix", "dashboard", "ci")
    run("npm", "--prefix", "dashboard", "run", "build")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(ROOT / "blindspot/observer/web" / name, ROOT / "extension/media/overview" / name)
    shutil.copyfile(ROOT / "LICENSE", ROOT / "extension/LICENSE")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    run(sys.executable, "-m", "build", "--wheel")
    run("npm", "ci", cwd=ROOT / "extension")
    vsce = ROOT / "extension/node_modules/.bin/vsce"
    run(str(vsce), "package", "--no-dependencies", "--out", str(out / "blindspot-observer-0.4.0.vsix"), cwd=ROOT / "extension")
    with zipfile.ZipFile(out / "blindspot_local-0.4.0-py3-none-any.whl") as wheel:
        names = wheel.namelist()
        assert "blindspot/observer/dashboard_dist/index.html" in names
        assert any(n.startswith("blindspot/observer/dashboard_dist/assets/") and n.endswith(".js") for n in names)
        assert any(n.endswith(".woff2") for n in names)
    with zipfile.ZipFile(out / "blindspot-observer-0.4.0.vsix") as vsix:
        names = vsix.namelist()
        assert "extension/media/overview/index.html" in names
        assert "extension/license.txt" in {n.lower() for n in names}
        assert "extension/readme.md" in {n.lower() for n in names}
        assert not any("node_modules/" in n or n.startswith("extension/test/") for n in names)
    print(f"Inspected local packages: {out}. Publisher ID must be confirmed before publishing.")


if __name__ == "__main__":
    main()
