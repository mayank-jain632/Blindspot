from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


@dataclass(frozen=True)
class Diagnostic:
    category: str
    source_ref: str | None = None
    cwd: str | None = None


@dataclass(frozen=True)
class Observation:
    source_key: str
    session_id: str
    seq: int
    block_index: int
    source_ref: str
    result_refs: list[str]
    mode_raw: str | None
    outcome: str


@dataclass(frozen=True)
class Event:
    source_key: str
    session_id: str
    seq: int
    block_index: int
    kind: str
    tool_use_id: str | None
    ts: datetime | None
    cwd: str | None
    source_ref: str
    result_ref: str | None = None
    path: str | None = None
    mode_raw: str | None = None
    outcome: str = "unknown"
    op: str = "none"
    raw_tool: str | None = None
    input_fingerprint: str | None = None
    observations: list[Observation] = field(default_factory=list)


@dataclass
class Context:
    cwd: str
    started: datetime | None = None
    ended: datetime | None = None
    uncertain: bool = False

    def observe(self, ts: datetime | None) -> None:
        if ts is not None:
            self.started = min(self.started, ts) if self.started else ts
            self.ended = max(self.ended, ts) if self.ended else ts


@dataclass
class Transcript:
    source_key: str
    path: str
    events: list[Event] = field(default_factory=list)
    contexts: dict[str, Context] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    versions: set[str] = field(default_factory=set)
    record_types: dict[str, int] = field(default_factory=dict)
    unknown_record_types: dict[str, int] = field(default_factory=dict)
    tool_names: dict[str, int] = field(default_factory=dict)
    duplicate_operations: int = 0
    size: int = 0
    processed_bytes: int = 0
    digest: str = ""


@dataclass(frozen=True)
class Commit:
    sha: str
    author_time: datetime
    committer_time: datetime
    name: str
    email: str
    status: str


@dataclass
class FileHistory:
    path: str
    content_hash: str
    total_lines: int
    commits: list[Commit] = field(default_factory=list)
    lineage_ambiguous: bool = False


@dataclass(frozen=True)
class Window:
    source_key: str
    start: datetime | None
    end: datetime | None
    uncertain: bool = False


@dataclass
class FileReport:
    path: str
    state: str
    commit_context: str
    content_hash: str
    total_lines: int
    success_count: int
    error_count: int
    unresolved_count: int
    mode_counts: dict[str, int]
    confirmed_commit_count: int
    outside_commit_count: int
    churn_90d: int
    limitations: list[str]
    events: list[Event]
    commits: list[Commit]
