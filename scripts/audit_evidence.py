"""Independent spot-check of local reports against raw records and Git objects.

Run after producing reports/local/{saphire,mayank-portfolio}.json. This script
does not use Blindspot's parser, classifier, or Git reader. It emits structural
evidence only; never transcript prose, source content, or tool payloads.
"""

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def git(root, *args):
    return subprocess.check_output(["git", "-C", root, *args], env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def raw_index(source, root):
    calls, results, times = {}, {}, []
    mode, cwd = None, None
    with Path(source).open() as handle:
        for seq, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            cwd = row.get("cwd", cwd)
            if row.get("type") in {"user", "permission-mode"} and "permissionMode" in row:
                mode = row["permissionMode"]
            if cwd and str(Path(cwd).resolve()) == root and isinstance(row.get("timestamp"), str):
                times.append(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")))
            message = row.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    results.setdefault(block.get("tool_use_id"), []).append((seq, block.get("is_error", False)))
                elif block.get("type") == "tool_use" and block.get("name") in {"Edit", "Write", "NotebookEdit"}:
                    args = block.get("input", {})
                    value = args.get("notebook_path" if block["name"] == "NotebookEdit" else "file_path")
                    if not isinstance(value, str) or not cwd:
                        continue
                    absolute = value if os.path.isabs(value) else os.path.join(cwd, value)
                    relative = os.path.relpath(os.path.normpath(absolute), root)
                    calls.setdefault(block["id"], (relative, seq, mode))
    return calls, results, (min(times), max(times))


def main():
    rows = []
    for name in ("saphire", "mayank-portfolio"):
        report = json.loads((Path("reports/local") / f"{name}.json").read_text())
        root = report["checkout"]
        assert report["source_count"] == 1, "This spot-check expects one supported source per checkout."
        source = report["sources"][0]["path"]
        calls, results, bounds = raw_index(source, root)
        limits = {"agent_observed": 5, "unknown": 1, "inherited": 2} if name == "saphire" else {"agent_observed": 4, "no_agent_observed": 3}
        selected = [f for state, count in limits.items() for f in
                    [f for f in report["files"] if f["state"] == state][:count]]
        for file in selected:
            matching = [(tool_id, call) for tool_id, call in calls.items() if call[0] == file["path"]]
            successes, errors, modes, refs = 0, 0, Counter(), []
            for tool_id, (_, seq, mode) in matching:
                answers = results.get(tool_id, [])
                assert answers, "Unexpected unresolved operation in the selected real sample."
                flags = {error for _, error in answers}
                assert flags in ({True}, {False}), "Conflicting results require separate inspection."
                if flags == {False}:
                    successes += 1
                    modes[mode or "<unrecorded>"] += 1
                else:
                    errors += 1
                refs.append(f"{seq}→{answers[0][0]}")
            assert successes == file["success_count"]
            assert errors == file["error_count"]
            assert dict(modes) == file["mode_counts"]
            blob = git(root, "show", f"{report['head']}:{file['path']}")
            assert hashlib.sha256(blob).hexdigest() == file["content_hash"]
            commits = git(root, "log", "-z", "--format=%H%x00%aE%x00%aI", report["head"], "--", file["path"]).split(b"\0")
            if commits[-1:] == [b""]:
                commits.pop()
            records = [commits[i:i+3] for i in range(0, len(commits), 3)]
            confirmed = [r for r in records if r[1].decode() in report["identity"]["confirmed"]]
            assert len(confirmed) == file["confirmed_commit_count"]
            end = bounds[1] + timedelta(hours=report["policy"]["grace_hours"])
            outside = sum(not bounds[0] <= datetime.fromisoformat(r[2].decode()) <= end for r in confirmed)
            if file["state"] == "agent_observed":
                assert successes > 0
                assert outside == file["outside_commit_count"]
            elif file["state"] == "no_agent_observed":
                assert successes == 0 and confirmed and outside == len(confirmed)
            elif file["state"] == "inherited":
                assert successes == 0 and not confirmed
            else:
                history = git(root, "log", "--format=", "--name-status", "--follow", "-z", report["head"], "--", file["path"])
                assert any(re.fullmatch(rb"R\d+", token.strip(b"\n")) for token in history.split(b"\0"))
                assert "path_lineage_ambiguous" in file["limitations"]
            rows.append(f"| {name} | {file['path']} | {file['state']} | {successes}/{errors} | {', '.join(refs[:2]) or 'No direct edit records'} |")
    assert len(rows) == 15
    output = "# Independent evidence spot-check\n\n"
    output += "15 files checked against raw transcript structure and separate Git commands.\n"
    output += "Counts are successful/failed direct edits. Line pairs identify call→result.\n\n"
    output += "| Checkout | Path | State | Edits | Source line pairs |\n|---|---|---|---|---|\n"
    output += "\n".join(rows) + "\n"
    target = Path("reports/local/15-file-audit.md")
    target.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
