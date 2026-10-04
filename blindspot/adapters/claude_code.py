"""Streaming Claude transcript parser. Never retain prose or mutation payloads."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

from ..models import Context, Diagnostic, Event, Observation, Transcript, timestamp

EDIT_TOOLS = {"Edit": ("file_path", "edit"), "Write": ("file_path", "write"),
              "NotebookEdit": ("notebook_path", "notebook")}
SUPPORTED_TYPES = {"user", "assistant", "permission-mode"}
KNOWN_SKIPPED = {"attachment", "last-prompt", "ai-title", "atis-latch", "mode",
                "queue-operation", "bridge-session", "system", "file-history-snapshot",
                "file-history-delta", "custom-title", "cost-state", "progress"}


def source_key(path: Path) -> str:
    return hashlib.sha256(f"claude_code:{path.resolve()}".encode()).hexdigest()[:24]


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    if not root.is_dir():
        return [], []
    main = sorted(root.glob("*/*.jsonl"))
    main_set = set(main)
    nested = sorted(p for p in root.glob("**/*.jsonl") if p not in main_set)
    return main, nested


def parse(path: Path) -> Transcript:
    path = path.resolve()
    report = Transcript(source_key(path), str(path))
    cwd: str | None = None
    mode: str | None = None
    session = path.stem
    operations: dict[str, tuple[str, Event]] = {}
    duplicate_calls: dict[tuple[str, int], list[Event]] = {}
    results: dict[str, list[tuple[str, str]]] = {}
    conflicts: set[str] = set()
    types: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    digest = hashlib.sha256()
    try:
        handle = path.open("rb")
    except OSError:
        report.diagnostics.append(Diagnostic("source_unreadable", str(path)))
        return report
    with handle:
        for seq, raw in enumerate(handle, 1):
            digest.update(raw)
            report.size += len(raw)
            ref = f"{path}:{seq}"
            if not raw.endswith(b"\n"):
                report.diagnostics.append(Diagnostic("incomplete_final_line", ref, cwd))
                if cwd:
                    report.contexts[cwd].uncertain = True
                break
            report.processed_bytes += len(raw)
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                report.diagnostics.append(Diagnostic("malformed_line", ref, cwd))
                if cwd:
                    report.contexts[cwd].uncertain = True
                continue
            if not isinstance(row, dict):
                report.diagnostics.append(Diagnostic("unsupported_record_shape", ref, cwd))
                continue
            candidate = row.get("cwd")
            if isinstance(candidate, str) and os.path.isabs(candidate):
                cwd = os.path.normpath(candidate)
            if isinstance(row.get("sessionId"), str):
                session = row["sessionId"]
            ts = timestamp(row.get("timestamp"))
            kind = row.get("type") if isinstance(row.get("type"), str) else "<missing>"
            types[kind] += 1
            if cwd:
                context = report.contexts.setdefault(cwd, Context(cwd))
                context.observe(ts)
                if kind in {"user", "assistant"} and ts is None:
                    context.uncertain = True
            if isinstance(row.get("version"), str):
                report.versions.add(row["version"])
            if kind not in SUPPORTED_TYPES:
                continue
            if kind in {"user", "permission-mode"} and "permissionMode" in row:
                mode = row["permissionMode"] if isinstance(row["permissionMode"], str) else None
                report.events.append(Event(report.source_key, session, seq, -1,
                    "mode_change", None, ts, cwd, ref, mode_raw=mode))
            message = row.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block_index, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    tool_id = block.get("tool_use_id")
                    if not isinstance(tool_id, str):
                        report.diagnostics.append(Diagnostic("result_missing_id", ref, cwd))
                        continue
                    error = block.get("is_error", False)
                    shape_ok = isinstance(block.get("content"), (str, list, dict))
                    outcome = ("error" if error else "ok") if isinstance(error, bool) and shape_ok else "unknown"
                    results.setdefault(tool_id, []).append((outcome, ref))
                    continue
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name")
                if not isinstance(name, str):
                    report.diagnostics.append(Diagnostic("tool_missing_name", ref, cwd))
                    continue
                tools[name] += 1
                if name not in EDIT_TOOLS and name != "Bash":
                    continue
                args = block.get("input")
                tool_id = block.get("id") if isinstance(block.get("id"), str) else None
                raw_path = args.get(EDIT_TOOLS[name][0]) if name in EDIT_TOOLS and isinstance(args, dict) else None
                event_path = None
                if isinstance(raw_path, str) and raw_path:
                    if os.path.isabs(raw_path):
                        event_path = os.path.normpath(raw_path)
                    elif cwd:
                        event_path = os.path.normpath(os.path.join(cwd, raw_path))
                if name in EDIT_TOOLS and event_path is None:
                    report.diagnostics.append(Diagnostic("edit_path_unresolved", ref, cwd))
                # Retain only a digest of mutation inputs, never their contents.
                signature = hashlib.sha256(json.dumps([name, args, cwd], sort_keys=True).encode()).hexdigest()
                event = Event(report.source_key, session, seq, block_index,
                    "shell_activity" if name == "Bash" else "file_edit", tool_id, ts,
                    cwd, ref, path=event_path, mode_raw=mode,
                    op=EDIT_TOOLS[name][1] if name in EDIT_TOOLS else "none", raw_tool=name,
                    input_fingerprint=signature if name in EDIT_TOOLS else None)
                if tool_id and tool_id in operations:
                    if operations[tool_id][0] == signature:
                        report.duplicate_operations += 1
                        original = operations[tool_id][1]
                        duplicate_calls.setdefault((original.source_ref, original.block_index), []).append(event)
                    else:
                        conflicts.add(tool_id)
                        report.diagnostics.append(Diagnostic("conflicting_tool_id", ref, cwd))
                        # Retain both named paths as unresolved rather than losing one.
                        report.events.append(event)
                    continue
                if tool_id:
                    operations[tool_id] = (signature, event)
                else:
                    report.diagnostics.append(Diagnostic("tool_missing_id", ref, cwd))
                report.events.append(event)
    report.digest = digest.hexdigest()
    resolved = []
    for event in report.events:
        if event.kind == "mode_change":
            resolved.append(event)
            continue
        paired = results.get(event.tool_use_id or "", [])
        outcomes = {outcome for outcome, _ in paired}
        outcome = next(iter(outcomes)) if len(outcomes) == 1 and event.tool_use_id not in conflicts else "unknown"
        copies = [event, *duplicate_calls.get((event.source_ref, event.block_index), [])]
        observations = [Observation(copy.source_key, copy.session_id, copy.seq,
            copy.block_index, copy.source_ref, [ref for _, ref in paired],
            copy.mode_raw, outcome) for copy in copies]
        mode_conflict = len({copy.mode_raw for copy in copies}) > 1
        if mode_conflict:
            report.diagnostics.append(Diagnostic("copied_operation_policy_conflict", event.source_ref, event.cwd))
        resolved.append(replace(event, outcome=outcome, mode_raw=None if mode_conflict else event.mode_raw,
            result_ref=paired[0][1] if paired else None, observations=observations))
        if outcome == "unknown":
            report.diagnostics.append(Diagnostic("tool_outcome_unresolved", event.source_ref, event.cwd))
        if event.kind == "file_edit" and event.mode_raw == "plan":
            report.diagnostics.append(Diagnostic("edit_in_plan_policy", event.source_ref, event.cwd))
    report.events = resolved
    report.record_types = dict(sorted(types.items()))
    report.unknown_record_types = {key: count for key, count in sorted(types.items())
                                  if key not in SUPPORTED_TYPES | KNOWN_SKIPPED}
    report.tool_names = dict(sorted(tools.items()))
    return report
