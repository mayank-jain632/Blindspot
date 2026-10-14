"""Build local release artifacts. Does not publish or upload anything."""
from pathlib import Path
import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bundle_runtime import bundle, RUNTIMES


def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)


def main():
    native = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system(), "unsupported") + "-" + {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}.get(platform.machine(), "unsupported")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=list(RUNTIMES), default=native)
    parser.add_argument("--all-targets", action="store_true")
    args = parser.parse_args()
    version = json.loads((ROOT / "extension/package.json").read_text())["version"]
    targets = list(RUNTIMES) if args.all_targets else [args.target]
    if any(target not in RUNTIMES for target in targets):
        parser.error("Choose a supported --target or --all-targets")
    try:
        build_available = importlib.util.find_spec("build.__main__") is not None
    except ModuleNotFoundError:
        build_available = False
    if not build_available:
        raise SystemExit(
            f"Missing Python build tool. Install it with: {sys.executable} -m pip install build"
        )
    run("npm", "--prefix", "dashboard", "ci")
    run("npm", "--prefix", "dashboard", "run", "build")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(ROOT / "blindspot/observer/web" / name, ROOT / "extension/media/overview" / name)
    shutil.copyfile(ROOT / "LICENSE", ROOT / "extension/LICENSE")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    run(sys.executable, "-m", "build", "--wheel")
    bundled = ROOT / "extension/receiver"
    if bundled.exists():
        shutil.rmtree(bundled)
    with zipfile.ZipFile(out / f"blindspot_local-{version}-py3-none-any.whl") as wheel:
        for name in wheel.namelist():
            if name.startswith("blindspot/"):
                wheel.extract(name, bundled)
    run("npm", "ci", cwd=ROOT / "extension")
    vsce = ROOT / "extension/node_modules/.bin/vsce"
    for target in targets:
        bundle(target)
        package = out / f"blindspot-observer-{version}-{target}.vsix"
        run(str(vsce), "package", "--no-dependencies", "--target", target, "--out", str(package), cwd=ROOT / "extension")
        with zipfile.ZipFile(package) as vsix:
            names = vsix.namelist()
            assert "extension/runtime/python.tar.gz" in names
            assert "extension/receiver_entry.py" in names
            assert any(n.startswith("extension/runtime/NOTICE-") for n in names)
            assert json.loads(vsix.read("extension/runtime/manifest.json"))["target"] == target
            assert "extension/media/overview/index.html" in names
            assert "extension/receiver/blindspot/observer/server.py" in names
            assert "extension/receiver/blindspot/observer/dashboard_dist/index.html" in names
            assert "extension/license.txt" in {n.lower() for n in names}
            assert "extension/readme.md" in {n.lower() for n in names}
            assert not any("node_modules/" in n or n.startswith("extension/test/") for n in names)
        if target == native:
            shutil.copyfile(package, out / f"blindspot-observer-{version}.vsix")
    # Leave the source checkout ready to test its native bundled runtime.
    if native in targets and targets[-1] != native:
        bundle(native)
    with zipfile.ZipFile(out / f"blindspot_local-{version}-py3-none-any.whl") as wheel:
        names = wheel.namelist()
        assert "blindspot/observer/dashboard_dist/index.html" in names
        assert any(n.startswith("blindspot/observer/dashboard_dist/assets/") and n.endswith(".js") for n in names)
        assert any(n.endswith(".woff2") for n in names)
    print(f"Inspected local packages: {out}. Publisher ID must be confirmed before publishing.")


if __name__ == "__main__":
    main()
