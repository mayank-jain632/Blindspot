"""Create a fresh, disposable Git fixture; never overwrite an existing pilot."""
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    pilot = root / "sandbox" / "observer-pilot"
    if pilot.exists():
        raise SystemExit(f"Already exists: {pilot}. Preserve it; no files changed.")
    pilot.mkdir(parents=True)
    functions = ["\"\"\"Disposable viewport fixture. Change this code freely during the pilot.\"\"\"\n"]
    for number in range(1, 21):
        functions.append(f'''def scale_{number}(values):
    """Scale a series by {number}, retaining only nonnegative inputs.

    This block intentionally occupies several lines to test scrolling and folds.
    It is fixture code, not part of Blindspot's runtime.
    """
    accepted = [value for value in values if value >= 0]
    return [value * {number} for value in accepted]

''')
    (pilot / "visible.py").write_text("\n".join(functions))
    (pilot / "closed.py").write_text('"""Change this using the terminal without opening it in the editor."""\n\ndef total(values):\n    return sum(values)\n')
    (pilot / "atomic.py").write_text('"""Fixture for atomic replacement and renaming."""\n\ndef label():\n    return "before"\n')
    (pilot / ".gitignore").write_text(".claude/\n__pycache__/\n*.tmp\n")
    (pilot / "README.md").write_text("# Blindspot observer pilot\n\nDisposable source only. Follow reports/observer-pilot.md in the parent Blindspot project.\nSource snapshots are stored outside this checkout.\n")
    def git(*args):
        subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(pilot), *args], check=True, capture_output=True, text=True)
    git("init", "-b", "main")
    git("config", "user.name", "Blindspot Pilot")
    git("config", "user.email", "pilot@blindspot.invalid")
    git("add", "visible.py", "closed.py", "atomic.py", "README.md", ".gitignore")
    git("commit", "-m", "Create disposable observer fixture")
    print(pilot)


if __name__ == "__main__":
    main()
