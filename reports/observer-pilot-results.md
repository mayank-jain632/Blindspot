# First VS Code desktop pilot: results

Status: **core collection demonstrated on the disposable local workspace;
Phase 1 gate remains open**. Quiz generation remains paused.

Source: `sandbox/observer-pilot/blindspot-observer-report.json`, supplied by the
user. SHA-256: `be4fbbff8e9bb4ade157b48df606b87a940e9d26f50c574a1a42121e0343e44b`.
Recording: 2026-10-03, approximately 19:39–19:46 America/Chicago (the export's
UTC timestamps are 2026-10-04 00:39:26.521–00:46:19.136).
Session duration by monotonic clock: **412.593 seconds**.

The report and matching local journal were inspected without modifying them or
the pilot source. Snapshot source text was checked locally and is not reproduced
in this document. No new runtime code was needed to assess this pass.

## Observed results

| Observation | Result |
|---|---|
| Lifecycle | One session start and one clean session end; session sequences 0–824 are complete and ordered |
| Ingested events | 825: 37 snapshots, 672 visibility intervals, 75 interactions, 15 window-state events, 14 diagnostics, 9 filesystem events, 1 marker, 1 start and 1 end |
| Reported editor time | 110.281 seconds across `visible.py` and newly added `temp.md`; this is not reading time or a codebase coverage percentage |
| Version binding | 37 snapshot records representing 36 distinct path/hash pairs; 30 displayed path/hash pairs; every snapshot hash verified against local source text |
| Unsaved edits | 24 dirty document snapshots; observations bind separately to the changing source hashes |
| Returning to known content | One `visible.py` hash was observed again after another version; consistent with returning to earlier content, but the report cannot prove the Undo command caused it |
| Background focus | Five distinct unfocused intervals total 162.381 seconds; display time was excluded apart from a 0.106291 ms boundary offset at one focus return |
| Closed-file change | `closed.py` gets a filesystem change and a new disk snapshot, with no visibility intervals |
| Atomic replacement | `atomic.py` gets a create notification and a new disk snapshot, with no visibility intervals; the watcher label is the notification received, not a claim of file identity or complete intermediate history |
| Diagnostics | All 14 are inventory-scope metadata, with no truncation; no sampling-gap diagnostics were recorded |
| Localhost export | Every exported event matches its journal event after snapshot text is removed; event counts, durations, and merged range summaries recompute correctly |

The existing `visible.py` source version has merged reported ranges 1–201 across
the session. Individual intervals have smaller ranges; the summary does not mean
one screen displayed the whole file at once or that its contents were read.

All visibility intervals are within their captured source's line bounds, follow
an earlier snapshot of that version, and do not overlap one another. The complete
sequence and absence of sampling gaps are internal consistency evidence; they do
not prove every real-world change was captured.

## User feedback and remaining cases

For this first export, the user confirmed **pause/resume and stop/start were not attempted**, and reported
that recording and typing felt the same as usual. This is encouraging small-fixture
feedback, not a measured latency or memory benchmark. No profiler numbers or
large-repository workload are available.

A later stop/start attempt produced an "already recording" message. Extension
0.1.1 now fixes canceled-startup cleanup and isolation from previous-session
callbacks; see [the restart fix and regression results](observer-validation.md).
On 2026-10-04 the user confirmed the corrected desktop stop/start flow worked as
expected. The user also confirmed Pause/Resume on 2026-10-04. Surface precision,
desktop recovery, and measured overhead remain unconfirmed; the Phase 1 gate
remains open. No follow-up export was supplied with these confirmations, so the
earlier 825-event report remains the audited artifact. Observer 0.2.0 now adds
[connection recovery and batching](observer-recovery.md).

There are no pause/resume state events, second session, or rename notifications
in this export. Only the baseline case has a marker. Folding, horizontal clipping,
terminal/sidebar focus, diff/split editors, branch switches, receiver/host recovery,
and concurrent changes cannot be established from this report alone. Their absence
is not a collector failure: the actions were either unperformed or unconfirmed.

The 0.106291 ms apparent background overlap occurs because the view and subsequent
window-state event take separate monotonic timestamps in one callback. It is a
timing qualification, not evidence of seconds of background accrual. Extension
0.1.1 now uses one timestamp for that transition and checks it in the host test.
The report is preserved as recorded; its evidence is not silently corrected.

The trace also contains **457 of 672 visibility intervals shorter than 10 ms**.
Rapid range changes can produce these intervals without increasing total reported
time. This suggests testing interval coalescing/batched persistence in later storage
work; it does not establish slowdown, dropped events, or a faulty reading score.

## Earlier lifecycle follow-up instructions (0.1.1)

Stop/Start and Pause/Resume have since been confirmed by the user. The current
next manual pass is [the 0.2.0 recovery experiment](observer-recovery.md).
The instructions below document the earlier requested follow-up.

Keep the current journal and report. If the receiver is stopped, start it again
from the Blindspot root:

```sh
.venv/bin/python -B -m blindspot observer serve \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state \
  --port 7777
```

Use the same **Blindspot: Observer pilot** Development Host as before (launch with
F5 if needed). Run **Developer: Reload Window** there once to load the 0.1.1
restart fix. Keep the receiver running. Later Stop/Start cycles should work
without another reload. The localhost inspector does not accrue editor display time while
the browser has focus. This follow-up takes about two minutes:

1. Run **Blindspot: Start Recording**, accept the opt-in prompt, open `visible.py`,
   and leave it focused for three seconds.
2. Add marker **followup-pause**, then run **Blindspot: Pause Recording**.
   Add a harmless comment to `visible.py`, save, and wait five seconds.
3. Run **Blindspot: Resume Recording**, add marker **followup-resumed**, then
   leave the source editor focused for three seconds. Expected: paused and
   recording state events; no snapshots/interactions/visibility during the paused
   interval; a resulting source snapshot after resume. Markers remain allowed.
4. Run **Blindspot: Stop Recording**, wait five seconds, then **Start Recording**
   again. Add marker **followup-restarted**, leave `visible.py` focused for three
   seconds, then Stop. Expected: a clean end and a new session ID, with no evidence
   credited for the stopped interval.
5. Open the localhost inspector and Download report. Preserve the first report:
   save the second as `blindspot-observer-followup.json` in Downloads or
   `reports/local/`, outside the observed pilot. Send its path back here.

With the same state directory, the follow-up is cumulative: expect three total
sessions (the first pass plus these two), and at least one paused/recording state
pair. A restart never reconstructs unrecorded activity.

## Roadmap decision

The first desktop pass supports continuing the collector experiment. Finish the
remaining surface and recovery/overhead
checks before treating reported ranges as a current-version coverage gauge.
Structured agent context remains a separate collector extension. Phase 2 handles
durable storage and derivation; Phase 3 delivers the full localhost and extension
visibility interfaces; Phase 4 resumes on-demand understanding checks.
