from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import os
from pathlib import Path

from ..adapters.claude_code import discover, parse
from ..models import Diagnostic, Event, Transcript, Window
from ..state import State
from .repo import resolve_root
from .deduplicate import coalesce


@dataclass
class SessionEvidence:
    events: dict[str, list[Event]]
    windows: list[Window]
    sources: list[Transcript]
    diagnostics: list[Diagnostic]
    orphans: list[dict]
    unsupported_nested: list[str]
    manual_links: list[str]
    temporary_links: list[str]
    recorded_operation_counts: dict[str, int]
    cross_source_duplicates: int


def load_sources(directory: Path) -> tuple[list[Transcript], list[Path]]:
    main, nested = discover(directory)
    return [parse(path) for path in main], nested


def associate(root: Path, sources: list[Transcript], nested: list[Path], state: State,
              source_roots: list[Path] | None = None) -> SessionEvidence:
    events: dict[str, list[Event]] = {}
    windows = []
    relevant = []
    diagnostics = []
    orphans = []
    manual_links = []
    temporary_links = []
    requested_roots = {os.path.normpath(str(p.expanduser().absolute())) for p in source_roots or []}
    temporary = {}
    for origin in sorted(requested_roots):
        matches = [s for s in sources if next(iter(s.contexts), None) == origin]
        if not matches:
            raise ValueError("--source-root must match the first recorded cwd of a discovered main transcript.")
        for source in matches:
            if any(not Path(cwd).is_relative_to(origin) for cwd in source.contexts):
                raise ValueError("A --source-root transcript spans other checkout contexts; reconcile that source separately.")
            temporary[source.source_key] = {"root": str(root)}
    cache: dict[str, Path | None] = {}

    def lookup(cwd: str) -> Path | None:
        if cwd not in cache:
            cache[cwd] = resolve_root(Path(cwd))
        return cache[cwd]

    for source in sources:
        link = temporary.get(source.source_key, state.data["links"].get(source.source_key))
        linked_root = Path(link["root"]) if isinstance(link, dict) and isinstance(link.get("root"), str) else None
        associated_contexts = []
        unknown_contexts = []
        for context in source.contexts.values():
            found = lookup(context.cwd)
            target = linked_root if linked_root is not None else found
            if target == root:
                associated_contexts.append(context)
            elif found is None:
                unknown_contexts.append(context.cwd)
        if unknown_contexts or not source.contexts:
            orphans.append({"source_key": source.source_key, "source": source.path,
                "cwd": sorted(unknown_contexts), "reason": "checkout_unresolved"})
        if not associated_contexts:
            continue
        relevant.append(source)
        diagnostics.extend(d for d in source.diagnostics if d.cwd is None or
                           any(d.cwd == c.cwd for c in associated_contexts))
        if linked_root is not None:
            is_temporary = source.source_key in temporary
            (temporary_links if is_temporary else manual_links).append(source.source_key)
            diagnostics.append(Diagnostic("temporary_checkout_link" if is_temporary else "manual_checkout_link", source.path))
        starts = [c.started for c in associated_contexts if c.started]
        ends = [c.ended for c in associated_contexts if c.ended]
        windows.append(Window(source.source_key, min(starts) if starts else None,
            max(ends) if ends else None, any(c.uncertain for c in associated_contexts)))
        cwds = {c.cwd for c in associated_contexts}
        for event in source.events:
            if event.kind != "file_edit" or event.cwd not in cwds:
                continue
            if event.path is None:
                continue
            # Explicit links map old context-relative paths, never encoded folder names.
            if linked_root is not None:
                base = next(iter(source.contexts))
                relative = os.path.relpath(event.path, base)
            else:
                # Canonicalize the cwd alias (e.g. /var -> /private/var), retaining
                # lexical path history instead of resolving the current file itself.
                canonical = os.path.normpath(os.path.join(str(Path(event.cwd).resolve()),
                    os.path.relpath(event.path, event.cwd)))
                relative = os.path.relpath(canonical, root)
            if relative == ".." or relative.startswith("../") or os.path.isabs(relative):
                diagnostics.append(Diagnostic("edit_outside_checkout", event.source_ref, event.cwd))
                continue
            events.setdefault(relative, []).append(event)
    parent_paths = {Path(source.path) for source in relevant}
    unsupported = []
    for path in nested:
        path = path.resolve()
        # Directory layout can connect nested sources to a main file, never to a cwd.
        if any(parent.with_suffix(".jsonl") in parent_paths for parent in path.parents if parent.name):
            unsupported.append(str(path))
            diagnostics.append(Diagnostic("unsupported_nested_source", str(path)))
    recorded = Counter(outcome for path_events in events.values() for event in path_events
                       for outcome in ([o.outcome for o in event.observations] or [event.outcome]))
    collapsed = 0
    for path in events:
        events[path].sort(key=lambda e: (e.source_key, e.seq, e.block_index))
        events[path], extra, count = coalesce(events[path])
        diagnostics.extend(extra)
        collapsed += count
    return SessionEvidence(events, windows, relevant, diagnostics, orphans,
        sorted(unsupported), sorted(manual_links), sorted(temporary_links),
        dict(sorted(recorded.items())), collapsed)
