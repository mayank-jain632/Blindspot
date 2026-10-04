from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

from ..state import State
from ..review.service import ReviewService
from .classify import classify, queue
from .repo import DEFAULT_EXCLUSIONS, Repository
from .sessions import associate, load_sources

LABELS = {"agent_observed": "agent edits recorded", "no_agent_observed": "no agent edits recorded",
          "unknown": "evidence unresolved", "inherited": "other identities only"}
POLICY_VERSION = 2


def encode(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(type(value).__name__)


def safe(value: object) -> str:
    # Escape control characters in paths/identities instead of emitting terminal codes.
    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def build_report(path: Path, sessions_dir: Path, state: State, now: datetime,
                 grace: float = 24, exclusions: list[str] | None = None,
                 includes: list[str] | None = None, sources=None,
                 source_roots: list[Path] | None = None) -> dict:
    repo = Repository(path)
    state.guard_repository(repo.root)
    root = str(repo.root)
    record = state.checkout(root, repo.key)
    identities = {repo.canonical_email(email) for email in record.get("identities", [])}
    if repo.email and record.get("use_configured_identity", True):
        identities.add(repo.email)
    exclusions = DEFAULT_EXCLUSIONS if exclusions is None else exclusions
    includes = includes or []
    files, excluded = repo.inventory(exclusions, includes)
    authors = repo.history(files)
    transcripts, nested = sources if sources is not None else load_sources(sessions_dir)
    evidence = associate(repo.root, transcripts, nested, state, source_roots)
    prior = state.data["inventories"].get(root, {})
    inventory = {s.source_key: {"path": s.path, "size": s.size, "digest": s.digest,
        "processed_bytes": s.processed_bytes} for s in evidence.sources}
    lost = sorted(set(prior) - set(inventory))
    for key in lost:
        inventory[key] = {**prior[key], "missing": True}
    known_loss = bool(lost)
    available = bool(evidence.sources)
    reports = [classify(f, evidence.events.get(f.path, []), evidence.windows,
        identities, grace, now, known_loss) for f in files.values()]
    reports.sort(key=lambda f: f.path)
    counts = {key: sum(f.state == key for f in reports) for key in LABELS}
    review_queue = queue(reports) if available else []
    review_status = ReviewService(state.directory, read_only=True).status(repo)
    for entry in review_queue:
        review = review_status["files"].get(entry["path"], {})
        passes = review.get("current_passing_samples", 0)
        entry["current_passing_samples"] = passes
        if passes:
            entry["reasons"] = [r for r in entry["reasons"] if r != "no_quiz_sample"]
            entry["reasons"].append(f"{passes}_current_passing_samples")
    churn_top = [f.path for f in sorted(reports, key=lambda f: (-f.churn_90d, f.path))[:10]]
    top = [f["path"] for f in review_queue[:10]]
    sensitivity = []
    base_states = {f.path: (f.state, f.commit_context) for f in reports}
    for hours in (0, 2, 24, 72):
        variants = [classify(f, evidence.events.get(f.path, []), evidence.windows,
            identities, hours, now, known_loss) for f in files.values()]
        variant_top = [f["path"] for f in queue(variants)[:10]] if available else []
        sensitivity.append({"grace_hours": hours,
            "state_counts": {key: sum(f.state == key for f in variants) for key in LABELS} if available else None,
            "commit_context_counts": dict(sorted(Counter(f.commit_context for f in variants if f.state == "agent_observed").items())) if available else None,
            "changed_from_selected_policy": sum(base_states[f.path] != (f.state, f.commit_context) for f in variants) if available else None,
            "top_ten_overlap_with_selected": len(set(top) & set(variant_top)) if available else None})
    checkout_events = [event for events in evidence.events.values() for event in events]
    quality_flags = []
    if available and files:
        quality_flags.extend(f"dominant_category:{key}" for key, count in counts.items()
                             if count / len(files) > .85)
        if counts["unknown"] / len(files) > .5:
            quality_flags.append("unknown_share_above_half")
    diagnostics = [asdict(d) for d in evidence.diagnostics]
    diagnostics.extend({"category": "known_source_coverage_loss", "source_ref": prior[key]["path"], "cwd": root} for key in lost)
    for event_path, events in sorted(evidence.events.items()):
        if event_path not in files:
            diagnostics.append({"category": "activity_outside_eligible_head_inventory",
                "source_ref": events[0].source_ref, "cwd": root})
    source_summaries = [{"source_key": s.source_key, "path": s.path,
        "versions": sorted(s.versions), "size": s.size, "digest": s.digest,
        "processed_bytes": s.processed_bytes, "record_types": s.record_types,
        "unknown_record_types": s.unknown_record_types,
        "tool_names": s.tool_names, "duplicate_operations": s.duplicate_operations}
        for s in evidence.sources]
    policy = {"classifier_version": POLICY_VERSION, "parser_version": 2,
        "deduplication_version": 1,
        "measurement_mode": "logs_only", "grace_hours": grace,
        "exclusions": exclusions, "includes": includes, "denominator": "all_eligible",
        "identity_digest": hashlib.sha256(json.dumps(sorted(identities)).encode()).hexdigest()}
    report = {"schema_version": 1, "checkout": root, "requested_path": str(path.resolve()),
        "head": repo.head, "repository_key": repo.key, "as_of": now.isoformat(),
        "analysis_status": "available" if available else "unavailable",
        "read_only": state.read_only,
        "eligible_files": len(files), "excluded": excluded,
        "identity": {"configured": repo.email or None, "confirmed": sorted(identities),
            "candidates": [{"email": email, "name": name} for email, name in authors.items()
                if email not in identities and repo.name and name == repo.name]},
        "policy": policy, "state_counts": counts if available else None,
        "state_rates": {key: count / len(files) for key, count in counts.items()} if available and files else None,
        "operation_counts": dict(sorted(Counter(e.outcome for e in checkout_events).items())),
        "operation_count_scope": "consistent_copies_coalesced; all_observed_checkout_paths_including_paths_outside_eligible_HEAD",
        "recorded_operation_counts": evidence.recorded_operation_counts,
        "deduplication": {"cross_source_copies_collapsed": evidence.cross_source_duplicates,
            "repeated_records_collapsed": sum(evidence.recorded_operation_counts.values()) - len(checkout_events),
            "limitations": "Only consistent copies with matching ID, timestamp, cwd, tool and input fingerprint are coalesced across sources."},
        "eligible_operation_counts": dict(sorted(Counter(e.outcome for path, events in evidence.events.items()
            if path in files for e in events).items())),
        "commit_context_counts": dict(sorted(Counter(f.commit_context for f in reports if f.state == "agent_observed").items())) if available else None,
        "mode_counts": dict(sorted(Counter(e.mode_raw if e.mode_raw is not None else "<unrecorded>"
            for e in checkout_events if e.outcome == "ok").items())),
        "source_count": len(evidence.sources), "sources": source_summaries,
        "versions": sorted({v for s in evidence.sources for v in s.versions}),
        "unknown_record_types": dict(sorted(sum((Counter(s.unknown_record_types) for s in evidence.sources), Counter()).items())),
        "discovery_diagnostic_counts": dict(sorted(Counter(d.category for s in transcripts for d in s.diagnostics).items())),
        "observed_windows": [asdict(w) for w in evidence.windows],
        "orphans": evidence.orphans, "unsupported_nested": evidence.unsupported_nested,
        "unassociated_nested_count": len(nested) - len(evidence.unsupported_nested),
        "manual_links": evidence.manual_links,
        "temporary_source_links": evidence.temporary_links, "diagnostics": diagnostics,
        "diagnostic_counts": dict(sorted(Counter(d["category"] for d in diagnostics).items())),
        "files": ([asdict(f) for f in reports] if available else
                  [{"path": f.path, "content_hash": f.content_hash,
                    "total_lines": f.total_lines, "commits": [asdict(c) for c in f.commits]}
                   for f in reports]), "queue": review_queue, "review_status": review_status,
        "queue_churn_top_ten_overlap": len(set(top) & set(churn_top)) if available else None,
        "quality_flags": quality_flags,
        "sensitivity": sensitivity, "superseded": repo.current_head() != repo.head,
        "limitations": ["historical path activity; survival into HEAD unproven",
            "shell mutations and unsupported agents may be absent",
            "observation bounds can span idle time and delayed commits",
            "quiz results are target samples against stored keys; familiarity marks are not implemented"]}
    for file in report["files"]:
        file["review"] = review_status["files"].get(file["path"],
            {"current_passing_samples": 0, "targets": []})
    state.data["checkouts"][root] = {**record, "repository_key": repo.key,
        "identities": sorted(identities)}
    state.data["inventories"][root] = inventory
    state.save()
    return report


def render(report: dict, doctor: bool = False) -> str:
    lines = [f"checkout: {safe(report['checkout'])}", f"revision: {report['head']}",
        f"as of: {report['as_of']}",
        f"{report['eligible_files']} eligible files; {sum(report['excluded'].values())} excluded",
        f"{report['source_count']} supported sources; {len(report['unsupported_nested'])} unsupported nested sources"]
    if report["read_only"]:
        lines.append("Read-only: application state will not be saved.")
    if report["temporary_source_links"]:
        lines.append(f"Temporary source mappings: {len(report['temporary_source_links'])}; links will not be saved.")
    if report["requested_path"] != report["checkout"]:
        lines.append("Scope: supplied path resolves to the checkout root shown above.")
    lines.append("")
    if report["analysis_status"] == "unavailable":
        lines.extend(["Analysis unavailable: no supported transcript associated with this checkout.",
                      "Git-only inventory is shown; no provenance rates are available.",
                      "Use --source-root for a temporary mapping, or blindspot link to save an association."])
    else:
        for key, label in LABELS.items():
            rate = report["state_rates"][key] if report["state_rates"] else None
            rate_text = f"{rate:.1%}" if rate is not None else "not available"
            lines.append(f"{report['state_counts'][key]:5}  {label} ({rate_text})")
        lines.extend(["", f"Commit context ({report['policy']['grace_hours']:g}h grace; timing inference):"])
        for key, count in report["commit_context_counts"].items():
            lines.append(f"  {count:5}  {key}")
        lines.extend(["", "Review next:"])
        for entry in report["queue"][:10]:
            passes = entry["current_passing_samples"]
            sample = f"{passes} current passing target sample(s)" if passes else "no current passing quiz sample"
            lines.append(f"  {safe(entry['path'])} — {entry['state']}; {entry['churn_90d']} recent commits; {sample}")
        if not report["queue"]:
            lines.append("  No candidates under the current policy; all eligible files remain accessible.")
    review = report["review_status"]
    lines.extend(["", f"Review records: {sum(f['current_passing_samples'] for f in review['files'].values())} current passing target samples; "
                  f"{review['current_confidently_wrong']} current confidently-wrong answers against valid keys.",
                  "Target samples do not establish whole-file understanding or change evidence states."])
    experiment = review["experiment"]
    if experiment["completed_attempts"]:
        lines.append(f"Experiment feedback: {experiment['workflow_test_attempts']} workflow tests; "
                     f"{experiment['understanding_review_attempts']} understanding reviews; "
                     f"{experiment['unclassified_completed_attempts']} completed attempts awaiting feedback.")
    if doctor:
        lines.extend(["", "Edit outcomes (consistent copies coalesced): " + json.dumps(report["operation_counts"], sort_keys=True),
            "Recorded edit outcomes: " + json.dumps(report["recorded_operation_counts"], sort_keys=True),
            f"Repeated edit records collapsed: {report['deduplication']['repeated_records_collapsed']} ({report['deduplication']['cross_source_copies_collapsed']} across sources)",
            "Recorded policies: " + json.dumps(report["mode_counts"], sort_keys=True),
            "Adapter source versions: " + json.dumps(report["versions"]),
            "Unknown record types: " + json.dumps(report["unknown_record_types"], sort_keys=True),
            "Diagnostics: " + json.dumps(report["diagnostic_counts"], sort_keys=True),
            "Quality diagnostics: " + json.dumps(report["quality_flags"]),
            "Discovery diagnostics (all sources): " + json.dumps(report["discovery_diagnostic_counts"], sort_keys=True),
            f"Orphan sources across discovery: {len(report['orphans'])}",
            f"Unassociated nested sources across discovery: {report['unassociated_nested_count']}"])
        if report["analysis_status"] == "available":
            lines.extend(["", "Window sensitivity:"])
            for entry in report["sensitivity"]:
                lines.append(f"  {entry['grace_hours']:2}h: {entry['changed_from_selected_policy']} changed state/context; top-ten overlap {entry['top_ten_overlap_with_selected']}")
            lines.append(f"Queue/churn-only top-ten overlap: {report['queue_churn_top_ten_overlap']}")
        else:
            lines.extend(["", "Window sensitivity and queue/churn comparison unavailable without supported evidence."])
    if report["superseded"]:
        lines.append("HEAD moved during this scan; this captured revision is superseded.")
    lines.extend(["", "Scope: committed source; historical path activity; available supported records.",
        "No recorded edit is not proof of human authorship. Modes do not prove review.",
        "Shell mutations and unsupported agent history may be absent."])
    return "\n".join(lines)
