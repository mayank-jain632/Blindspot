"""Bundle a checksum-pinned standalone CPython archive; build-time network only."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIMES = json.loads((ROOT / "scripts/python-runtimes.json").read_text())


def bundle(target):
    metadata = RUNTIMES[target]
    cache = ROOT / "dist/runtime-cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (target + ".tar.gz")
    if not archive.exists():
        temporary = archive.with_suffix(".download")
        try:
            print(f"Downloading pinned Python runtime for {target}", flush=True)
            with urlopen(metadata["url"], timeout=120) as source, temporary.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != metadata["sha256"]:
                raise ValueError(f"Runtime checksum mismatch: {target}")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError(f"Cached runtime checksum mismatch: {archive}")
    directory = ROOT / "extension/runtime"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir()
    shutil.copyfile(archive, directory / "python.tar.gz")
    (directory / "manifest.json").write_text(json.dumps({**metadata, "target": target}, indent=2) + "\n")
    # Keep upstream redistribution notices available alongside the packed runtime.
    with tarfile.open(archive) as source:
        notices = [m for m in source.getmembers() if m.isfile() and
                   any(word in Path(m.name).name.lower() for word in ("license", "copyright"))]
        if not notices:
            raise ValueError(f"Upstream runtime contains no redistribution notices: {target}")
        for index, member in enumerate(notices):
            (directory / f"NOTICE-{index}-{Path(member.name).name}").write_bytes(source.extractfile(member).read())
    print(f"Verified Python {metadata['version']} runtime: {target}", flush=True)
