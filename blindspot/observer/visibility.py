"""Current-source estimates. Raw observations retain their original versions."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re
import subprocess

from .store import MAX_TEXT, digest

SOURCE = re.compile(r"\.(py|js|jsx|ts|tsx|mjs|cjs|java|c|h|cpp|hpp|cc|cs|go|rs|rb|php|swift|kt|kts|scala|sh|bash|zsh|sql|html|css|scss|svelte|vue|json|toml|ya?ml|md)$", re.I)
EXCLUDED = re.compile(r"(^|/)(\.git|\.claude|\.blindspot|\.venv|venv|node_modules|vendor|dist|build|__pycache__)(/|$)|(^|/)\.env($|\.)|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)|\.min\.(js|css)$")


def inventory(root: Path):
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, timeout=5)
    if result.returncode: return [], ["Inventory unavailable: open a local Git workspace"]
    if len(result.stdout) > 2 * 1024 * 1024: return [], ["Git inventory exceeds 2 MiB limit"]
    names = sorted({x.decode("utf-8") for x in result.stdout.split(b"\0") if x})
    eligible = [n for n in names if not EXCLUDED.search(n) and (SOURCE.search(n) or n.split("/")[-1] in {"Dockerfile", "Makefile"})]
    diagnostics = ["Inventory truncated at 500 eligible candidates"] if len(eligible) > 500 else []
    files = []
    for name in eligible[:500]:
        path = root / name
        try:
            if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TEXT: continue
            data = path.read_bytes()
            if len(data) > MAX_TEXT: continue
            text = data.decode("utf-8")
            if "\0" in text: continue
            files.append({"path": name, "text": text, "content_hash": digest(text), "origin": "disk"})
        except (OSError, UnicodeError): diagnostics.append("Source unavailable: " + name)
    return files, diagnostics


def union_duration(intervals):
    end = None; total = 0
    for a, b in sorted(intervals):
        if end is None or a > end: total += b-a
        elif b > end: total += b-end
        end = b if end is None else max(end, b)
    return total


def unique_line_mapping(old: str, new: str):
    """Map only unique equal contiguous blocks; repeated/moved ambiguity gets no credit."""
    a, b = old.split("\n"), new.split("\n")
    if max(len(a), len(b)) > 5000: return {}
    old_lines, new_lines = "\n"+old+"\n", "\n"+new+"\n"
    def unique(haystack, needle):
        first = haystack.find(needle)
        return first >= 0 and haystack.find(needle, first+1) < 0
    mapped = {}
    for block in SequenceMatcher(None, a, b, autojunk=True).get_matching_blocks():
        if not block.size: continue
        needle = "\n"+"\n".join(a[block.a:block.a+block.size])+"\n"
        if unique(old_lines, needle) and unique(new_lines, needle):
            for offset in range(block.size): mapped[block.a+offset+1] = block.b+offset+1
    return mapped


def compact(lines):
    result = []
    for line in sorted(lines):
        if result and result[-1][1]+1 == line: result[-1][1] = line
        else: result.append([line, line])
    return result


def derive(current, observations, sources, dwell_ms=1000):
    """Union mirrored panes within sessions; maximum per-session dwell is conservative."""
    lines = defaultdict(lambda: defaultdict(list)); mapped_from = set(); exact = set()
    current_hash = digest(current); count = len(current.split("\n"))
    maps = {}
    for event in observations:
        payload = event["payload"]; old_hash = payload["content_hash"]
        if old_hash not in sources: continue
        if old_hash not in maps:
            maps[old_hash] = None if old_hash == current_hash else unique_line_mapping(sources[old_hash], current)
        mapping = maps[old_hash]
        for start, end in payload["ranges"]:
            for old_line in range(start, end+1):
                line = old_line if mapping is None else mapping.get(old_line)
                if line is None or not 1 <= line <= count: continue
                lines[line][event["session_id"]].append((payload["start_ms"], payload["end_ms"]))
                if mapping is None: exact.add(line)
                else: mapped_from.add(old_hash)
    dwell = {line: max(union_duration(intervals) for intervals in sessions.values()) for line, sessions in lines.items()}
    long = {line for line, duration in dwell.items() if duration >= dwell_ms}
    short = set(dwell)-long
    return {"line_count": count, "reported_lines": len(dwell), "dwell_lines": len(long), "brief_lines": len(short), "unknown_lines": count-len(dwell), "reported_ranges": compact(dwell), "dwell_ranges": compact(long), "brief_ranges": compact(short), "exact_ranges": compact(exact), "mapped_source_hashes": sorted(mapped_from)}


def current_files(store):
    """Resolve disk inventory and explicitly observed live dirty buffers under the lock."""
    files, diagnostics = inventory(store.workspace)
    documents = defaultdict(list)
    for path, sid, encoded, event_id in store.db.execute("SELECT * FROM documents ORDER BY event_id DESC"):
        # A new explicit baseline supersedes interrupted historical sessions. Other
        # currently active sessions remain candidates so conflicting buffers stay unknown.
        if not documents[path] or sid in store.active_sessions:
            documents[path].append((sid, json.loads(encoded)))
    output = []
    for file in files:
        unsupported = any(state["is_open"] and state.get("supported") is False for _, state in documents[file["path"]])
        dirty = [(sid, state) for sid, state in documents[file["path"]] if state["is_open"] and state["dirty"] and state.get("supported", True)]
        fresh = [(sid, state) for sid, state in dirty if sid in store.active_sessions and store.sessions[sid]["status"] == "recording" and sid in store.contacts and store.clock()-store.contacts[sid]["clock"] <= 7]
        uncertain = unsupported or bool(dirty and (len(fresh) != len(dirty) or len({state["content_hash"] for _, state in fresh}) != 1))
        if fresh and not uncertain:
            file = {**file, **store.versions[(file["path"], fresh[0][1]["content_hash"])], "origin": "unsaved document"}
        output.append({**file, "current_uncertain": uncertain})
    return output, diagnostics


def current_source(store, path, expected_hash):
    with store.lock:
        files, _ = current_files(store)
        file = next((f for f in files if f["path"] == path), None)
        if not file: raise ValueError("File is outside the eligible current inventory")
        if file["current_uncertain"]: raise ValueError("Current document state is uncertain; resume recording and refresh")
        if file["content_hash"] != expected_hash: raise ValueError("Source changed since the overview; refresh before inspecting")
        return {key: file[key] for key in ("path", "text", "content_hash", "origin")}


def file_stats(store, file, dwell_ms=1000):
    """Display evidence for one current file; the caller holds the store lock."""
    path = file["path"]
    sources = dict(store.db.execute("SELECT DISTINCT sources.hash,sources.text FROM snapshots JOIN sources ON sources.hash=snapshots.hash WHERE path=?", (path,)))
    observations = [{"session_id": sid, "payload": json.loads(payload)} for sid, payload in store.db.execute("SELECT session_id,payload FROM events WHERE path=? AND kind='visibility'", (path,))]
    return derive(file["text"], [] if file["current_uncertain"] else observations, sources, dwell_ms)


def overview(store, dwell_ms=1000):
    if type(dwell_ms) not in {int, float} or not math.isfinite(dwell_ms) or not 0 < dwell_ms <= 3600000: raise ValueError("Dwell filter must be between 0 and 3,600,000 ms")
    with store.lock:
        files, diagnostics = current_files(store)
        report = store.report(limit=200)
        context_rows = store.db.execute("SELECT session_id,payload FROM events WHERE kind='workspace_context' ORDER BY id DESC LIMIT 1").fetchone()
        tabs = set(json.loads(context_rows[1])["open_tabs"]) if context_rows else set()
        context_sid = context_rows[0] if context_rows else None
        context_fresh = bool(context_sid in store.active_sessions and store.sessions[context_sid]["status"] == "recording" and context_sid in store.contacts and store.clock()-store.contacts[context_sid]["clock"] <= 7)
        output = []
        for file in files:
            path = file["path"]; uncertain = file["current_uncertain"]
            stats = file_stats(store, file, dwell_ms)
            interactions = store.db.execute("SELECT COUNT(*) FROM events WHERE path=? AND kind='interaction'", (path,)).fetchone()[0]
            reason = "current document state uncertain" if uncertain else "no matching display evidence" if not stats["reported_lines"] else "brief display only" if not stats["dwell_lines"] else "some current lines have no evidence" if stats["unknown_lines"] else "reported across all eligible lines"
            output.append({"path": path, "content_hash": digest(file["text"]), "origin": file["origin"], "current_uncertain": uncertain, "open_tab": path in tabs, "interaction_events": interactions, "review_reason": reason, **stats})
        output.sort(key=lambda f: (not f["current_uncertain"], bool(f["dwell_lines"]), -f["unknown_lines"], f["path"]))
        totals = {key: sum(f[key] for f in output if not f["current_uncertain"]) for key in ("line_count", "reported_lines", "brief_lines", "dwell_lines", "unknown_lines")}
        totals.update(eligible_files=len(output), uncertain_files=sum(f["current_uncertain"] for f in output))
        return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "workspace": str(store.workspace), "dwell_ms": dwell_ms, "tab_context_fresh": context_fresh, "dwell_aggregation": "interval union within each session; maximum across sessions", "scope": "eligible current saved source with fresh dirty-document overlays; inclusive logical lines, including trailing empty lines; uncertain files excluded from line totals", "files": output, "totals": totals, "inventory_diagnostics": diagnostics, "timeline": report["events"], "health": {"sessions": report["sessions"], "ingestion_metrics": report["ingestion_metrics"], "storage": report["storage"], "recording_gaps": [json.loads(row[0]) for row in store.db.execute("SELECT payload FROM events WHERE kind='recording_gap' ORDER BY id DESC LIMIT 20")], "latest_connection_diagnostics": [json.loads(row[0]) for row in store.db.execute("SELECT payload FROM events WHERE kind='diagnostic' AND json_extract(payload,'$.reason')='connection_health' ORDER BY id DESC LIMIT 1")]}, "limits": ["Reported visibility is VS Code API evidence; keyboard focus, terminal occlusion, horizontal clipping and attention are unverified.", "Open tabs alone do not receive display credit. Inactive split panes can contribute reported ranges.", "Unknown means insufficient evidence, not unread. Earlier unrecorded activity remains unknown.", "Dwell threshold is a configurable reporting filter, not a validated attention threshold.", "Mapping credits only unique unchanged line blocks at the same path; repeated text and ambiguity are not inferred. Changed-version mapping is disabled above 5,000 lines.", "Interactions are historical context and may have an agent or unknown cause. No understanding score."]}
