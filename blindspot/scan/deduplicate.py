"""Coalesce consistent copied calls after each source has paired its own results."""

from collections import defaultdict
from dataclasses import replace

from ..models import Diagnostic, Event


def coalesce(events: list[Event]) -> tuple[list[Event], list[Diagnostic], int]:
    groups: dict[tuple, list[Event]] = defaultdict(list)
    retained = []
    diagnostics = []
    collapsed = 0
    for event in events:
        # An ID alone cannot establish a copied operation across sources.
        if not event.tool_use_id or event.ts is None or not event.input_fingerprint:
            retained.append(event)
            continue
        key = (event.tool_use_id, event.ts, event.cwd, event.path,
               event.raw_tool, event.input_fingerprint)
        groups[key].append(event)
    for copies in groups.values():
        if len(copies) == 1:
            retained.extend(copies)
            continue
        outcomes = {e.outcome for e in copies}
        modes = {o.mode_raw for e in copies for o in e.observations} or {e.mode_raw for e in copies}
        if len(outcomes) > 1 or len(modes) > 1:
            conflict = "ok" in outcomes and "error" in outcomes
            if conflict:
                category = "copied_operation_conflicting_results"
            elif len(outcomes) > 1:
                category = "copied_operation_incomplete_results"
            else:
                category = "copied_operation_policy_conflict"
            diagnostics.extend(Diagnostic(category, e.source_ref, e.cwd) for e in copies)
            # A complete result in one file never completes a missing result in
            # another. Contradictory resolved results remain explicitly unknown.
            retained.extend(replace(e, outcome="unknown") if conflict else e for e in copies)
            continue
        observations = [o for e in copies for o in e.observations]
        retained.append(replace(copies[0], observations=observations))
        collapsed += len(copies) - 1
    retained.sort(key=lambda e: (e.source_key, e.seq, e.block_index))
    return retained, diagnostics, collapsed
