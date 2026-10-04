# Local collector experiment: implementation and validation

Current build: **0.3**. This document preserves the earlier pilot/results. Use
[the current setup, desktop checks and SQL results](observer-03.md) for new runs.

Date: 2026-10-03. Status: automated implementation checks pass and the first
VS Code desktop report has been audited. Core version/range collection, focus
changes, closed-file edits, atomic replacement, and export consistency are
demonstrated on the disposable fixture. The user reports no perceived slowdown.
The user confirmed the corrected desktop stop/start and pause/resume flows on 2026-10-04.
Desktop surface/recovery/performance
checks remain open. See [desktop results and follow-up](observer-pilot-results.md).
Phase 1's acceptance gate is still open.

## Latest follow-up: observer 0.2.1

The [performance pass](observer-performance.md) adds a repeatable real-receiver
benchmark, a bounded exact-content hash cache, and a guard against document reads
in paused editor callbacks. Both benchmark runs preserve every generated event,
hash, display-time sum, and replay. Current checks: **24 Node and 17 Python
observer/integration tests pass**. Desktop recovery/surfaces and runtime profiling
remain open; synthetic results do not establish typing latency.

## Current build: observer 0.2.0 (2026-10-04)

Automatic recovery, heartbeat-derived status, recorded uncertain interruptions,
bounded event batching, and batched persistence are implemented. See
[behavior, limits, and desktop update instructions](observer-recovery.md).

Validation: **96 Python regression checks and 22 Node checks pass**. The Python
run includes the entire previous CLI/evidence/review suite and 17 observer cases.
The real cross-language recovery test stops the receiver, leaves it unavailable
through an automatic recovery probe, reopens the same journal, rotates the token
and receiver identifier, then verifies automatic recovery in a fresh paused
session. It accepts no source/display activity before explicit Resume, ends
cleanly afterwards, and leaves the temporary source file unchanged.

Additional checks cover active recording recovery, Stop during an in-flight
probe, rejection of a different workspace, heartbeat expiry without new events,
batch validation before any write, exact duplicate/retry handling, late replies
after queue overflow, large Unicode batch sizing, and persistence failure stopping
further writes. The real HTTP ingestion test loses an acknowledgement after
persistence and confirms retry adds no second event. A browser-script harness
verifies cookie rotation, disconnected export blocking, preservation of stale
status while filtering, and storage-error status. Editor/browser surfaces remain
mocked in these wiring checks; this is not a replacement for the desktop pass.

Under synthetic load, a 200-event burst requires four HTTP requests, and a
three-event receiver batch requires one disk flush; duplicate-only retry causes
no write. Identical adjacent viewport intervals coalesce while preserving total
display time and distinct range/source boundaries. These results establish
request/write reductions, not a measured runtime latency improvement.

The original desktop export is preserved. Pause/Resume confirmation is user
feedback, with no new exported artifact yet. Desktop recovery, surface precision,
and measured overhead remain open before SQLite/visibility derivation.

## Earlier restart fix: extension 0.1.1

The user subsequently reported that Start after Stop said "already recording."
The initial single-session test did not cover canceled startup or delayed failures
from an earlier session. Regression tests reproduced a pending startup that Stop
could not clear and a stale upload failure that could shut down a newer session.
On 2026-10-04 the user confirmed the updated desktop flow worked as expected.
This confirms restart usability; the exact original failing sequence was not captured.

Recording attempts now own their collector, transport, listeners, and filesystem
callbacks. Stop immediately releases the active attempt, including pending
startup. Canceled continuations and earlier upload failures cannot alter a newer
attempt. Workspace consent is remembered within this extension activation, with
an explicit modal prompt on first opt-in; each Start still creates a new session.
The status distinguishes starting from recording and controls offer valid actions.
Focus-transition records also share one timestamp to remove the observed boundary
offset in new recordings. Existing journal/report data is preserved.

Validation after the fix: **12 Node checks and 13 Python observer/integration
checks pass**. The real receiver accepts three consecutive extension Stop/Start
cycles, with distinct IDs, contiguous sequences, pause/resume, and clean ends.
VS Code surfaces in that integration are mocked; the user separately confirmed
actual desktop restart behavior. The 79 earlier regression checks were unchanged
and were not rerun for this extension-only fix.

Load the update once using **Developer: Reload Window** in the Development Host,
keep the receiver running, then try **Start → Stop → Start**. New session-start
events report `collector_version: "0.1.1"`. No reload is part of the normal
stop/start flow. Download the follow-up report after ending the second session.

## Delivered

- Dependency-free JavaScript extension, opt-in recording, controls/status bar,
  document and disk snapshots, reported ranges, interactions, window-focus events,
  gap diagnostics, filesystem observations, and manual pilot markers.
- Python loopback receiver with workspace binding, local authentication,
  Host/Origin checks, bounded event bodies, private connection file, source-hash
  validation, sequential/idempotent ingestion, fsynced experimental JSONL journal,
  single receiver writer, and conservative restart handling.
- Interactive localhost inspector with filtering, source-version selection,
  reported-range highlighting, event timeline, and source-free metadata download.
- Isolated committed Git fixture in `sandbox/observer-pilot`, ignored by the parent
  repository; a Development Host launch configuration and manual instructions.
- Approved roadmap and design headers updated to include both localhost and
  extension interfaces for the visibility MVP. Quiz generation remains paused.

## Initial automated results (0.1.0)

All **100 distinct checks** pass across the completed runs:

| Checks | Result | Scope |
|---|---|---|
| Existing Python regression suite | 79 passed | Evidence parsing/reporting, read-only behavior, identities, target binding, quiz lifecycle and preservation |
| Python observer and integration tests | 12 passed in the final focused run | Protocol/version/range/time validation, idempotency, overlap/pause rejection, restart gaps, incomplete journals, authentication, actual CLI startup/lock/shutdown/report, real Node-to-Python HTTP ingestion |
| Node tests | 9 passed in the final run | Collector focus/pause/scroll/edit/undo/gaps, source bounds, ordered transport retry/failure, loopback configuration, extension API wiring in a mock host |

A full Python discovery run passed 89 checks before the last two observer cases
were added; the final focused run reran all 12 observer/integration cases after
the final code changes. JavaScript syntax checks also passed for the extension,
collector, transport, and browser script. No packages were installed.

The real HTTP integration sends synthetic collector events across Node and Python.
Its known timeline produces 1,750 ms for the original hash and 2,000 ms for a
changed hash, separate range evidence, two sampling-gap diagnostics, and a session
end. Unfocused/paused intervals do not create display evidence. The receiver
rejects intervals preceding their source snapshot and retry conflicts.

The CLI integration verifies private connection-file permissions, a second writer
being rejected, accepted session events, Ctrl+C shutdown removing the connection
file, successful offline metadata reporting, and no observed-workspace writes.

Tests create temporary workspaces and state. The prepared manual fixture is the
only lasting new test repository. Existing real repositories, Claude logs, saved
evidence/configuration, and quiz attempts were not modified by this build.

## Findings and limits

The protocol can bind raw reported ranges and durations to an exact captured
source version. Source text is retained locally in the experimental journal;
metadata exports omit it. No whole-codebase visibility or understanding score is
derived yet, and ranges are not transferred across different hashes.

VS Code's `activeTextEditor` may retain the last editor while keyboard focus is
in another surface. This build therefore qualifies each visibility record with
window focus and unverified editor focus. Folded spans, horizontal clipping,
diff/hidden/split panes, filesystem-event coalescing, large repositories and
continuous recording overhead still require desktop tests. The
[official API reference](https://code.visualstudio.com/api/references/vscode-api)
describes the active-editor fallback; it is not an attention signal.

In 0.2.0 the inspector separately shows last reported recording state and live
heartbeat-derived connection state. A heartbeat establishes recent connectivity,
not editor attention or complete capture. Abrupt shutdown can leave a session
without an end record. Receiver recovery starts a fresh session and records the
uncertain gap; host reload still requires explicit Start.

Agent attribution/hooks, terminal source capture, change-range mapping, SQLite,
retention controls, and a current-version coverage gauge are not implemented.
The pilot is limited to one trusted local Git workspace, 500 candidate paths,
256 KiB snapshots and short runs. The journal and UI use in-memory event lists;
these are experiment limits, not a long-term storage design.

## Next decision

Complete the remaining manual cases and compare their records against known actions.
Resolve capture failures and overhead issues, then add structured agent context
and remaining collector scenarios. After Phase 1 meets its gate, Phase 2 builds
durable storage/derivation and Phase 3 delivers both full visibility interfaces.
Phase 4 resumes on-demand quizzes. Do not treat passing protocol tests as proof
that the editor collection experiment has already been validated.
