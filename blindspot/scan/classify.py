from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from ..models import Event, FileHistory, FileReport, Window


def contains(window: Window, when: datetime, grace_hours: float) -> bool:
    return bool(window.start is not None and window.end is not None and
                window.start <= when <= window.end + timedelta(hours=grace_hours))


def classify(history: FileHistory, events: list[Event], windows: list[Window],
             identities: set[str], grace_hours: float, now: datetime,
             known_loss: bool = False) -> FileReport:
    success = [e for e in events if e.outcome == "ok"]
    errors = [e for e in events if e.outcome == "error"]
    unresolved = [e for e in events if e.outcome == "unknown"]
    confirmed = [c for c in history.commits if c.email in identities]
    overlap = not success and any(contains(w, c.author_time, grace_hours)
        for w in windows for c in history.commits)
    limitations = ["historical_path_activity_not_current_content_attribution"]
    if history.lineage_ambiguous:
        limitations.append("path_lineage_ambiguous")
    if unresolved:
        limitations.append("edit_outcome_unresolved")
    if overlap:
        limitations.append("unexplained_session_overlap")
    if known_loss:
        limitations.append("known_source_coverage_loss")
    if not identities:
        limitations.append("identity_unavailable")
    if any(w.uncertain or w.start is None or w.end is None for w in windows):
        limitations.append("session_timing_or_source_incomplete")
    if history.lineage_ambiguous:
        state = "unknown"
    elif success:
        state = "agent_observed"
    elif unresolved or overlap or known_loss or not identities:
        state = "unknown"
    elif confirmed:
        state = "no_agent_observed"
    elif history.commits:
        state = "inherited"
    else:
        state = "unknown"

    relevant_keys = {key for event in success for key in
                     ([o.source_key for o in event.observations] or [event.source_key])}
    relevant = [w for w in windows if w.source_key in relevant_keys]
    context = "unavailable"
    outside = 0
    timing_ok = (state == "agent_observed" and bool(identities) and not known_loss
        and not unresolved and bool(relevant) and
        all(not w.uncertain and w.start is not None and w.end is not None for w in relevant)
        and all(e.ts is not None for e in success))
    if timing_ok:
        outside = sum(not any(contains(w, c.author_time, grace_hours) for w in relevant) for c in confirmed)
        context = "no_confirmed_commits" if not confirmed else "outside_commit" if outside else "inside_only"
    modes = Counter(e.mode_raw if e.mode_raw is not None else "<unrecorded>" for e in success)
    boundary = now - timedelta(days=90)
    return FileReport(history.path, state, context, history.content_hash, history.total_lines,
        len(success), len(errors), len(unresolved), dict(sorted(modes.items())),
        len(confirmed), outside,
        sum(boundary <= c.author_time <= now for c in history.commits),
        limitations, events, history.commits)


def queue(files: list[FileReport]) -> list[dict]:
    candidates = sorted((f for f in files if f.state in {"agent_observed", "unknown"}),
                        key=lambda f: (-f.churn_90d, f.path))
    return [{"path": f.path, "state": f.state, "churn_90d": f.churn_90d,
             "reasons": [f.state, "no_quiz_sample", f"{f.churn_90d}_recent_commits"]}
            for f in candidates]
