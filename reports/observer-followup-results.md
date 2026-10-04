# Desktop observer follow-up: audit and decision

Date: 2026-10-04. Observer 0.2.1. Status: recovery and exact-version collection
have desktop evidence; terminal visibility precision and a late interruption need
resolution before the collector gate closes. This is an audit, not a new build.
Quiz generation remains paused.

## Inputs and preservation

The user reports performing all requested desktop checks and supplied:

- `sandbox/observer-pilot/blindspot-observer-report (1).json`
- A Running Extensions screenshot showing observer 0.2.1, Activation: 3 ms,
  Profile: 0.00 ms.

Export SHA-256:
`942fe718f4ce616197280060db923fbc098034af7bd0d6eb08f4a5618b2cee96`.
Generated at `2026-10-04T07:33:08.310309+00:00`.

The export and existing source-bearing journal were read without modification.
All 1,933 exported events match the journal after snapshot text is removed.
The original 825-event export is an unchanged prefix of this cumulative report.
There are eight sessions: one 0.1.0, two 0.1.1, and five 0.2.1 sessions.
The 0.2.1 sessions contribute 1,079 events, 27 snapshots, 969 visibility intervals,
three recovery gaps, and 145.050 seconds of reported editor display time.

Every journal event through this export passes replay validation. All 74 snapshot
hashes verify against retained source; per-session sequences are contiguous,
version ranges remain in bounds, and exported range/duration summaries recompute
exactly. These are consistency checks, not proof of complete capture.

## Findings

| Check | Evidence and interpretation |
|---|---|
| Recovery while recording | A fresh 0.2.1 session references its predecessor through a qualified gap and records subsequent visibility. The gap reason is `session_unavailable`; detection-to-recovery timestamps span 30.049 seconds, which is not an exact outage duration. |
| Recovery while paused | The recovered session starts paused, remains so for 15.929 seconds, then records explicit Resume. No snapshots, interactions, or visibility occur during that paused interval. Its gap reason is `connection_lost`. |
| Stop during disconnection | The `recovery-cancelled` marker precedes a later fresh session without a recovery-gap link to the canceled session. This is consistent with explicit Start after cancellation; the export cannot independently prove the UI remained off throughout the prescribed wait. |
| Background focus | All five 0.2.1 sessions have zero display-time overlap with recorded unfocused intervals. The earlier 0.1.0 boundary offset does not recur here. |
| Folding | During the fold case, `visible.py` reports `[1,4]` and `[12,41]`. Its `scale_1` definition spans 4–11: the header remains reported and the folded body, lines 5–11, is omitted. This validates this instance, not all folding configurations. |
| Terminal case | Editor ranges continue in the terminal-test segment, including 8.810 seconds reporting only line 1. This is consistent with a retained editor range as the terminal expands. Exact keyboard-focus/panel state is absent, so the export cannot itself establish which intervals represent a fully hidden pane. Window focus alone is insufficient for a reliable displayed-source claim. |
| Split panes | Visibility switches between `visible.py` and `closed.py` around the split-case marker. Evidence remains serial for the active editor; it does not cover the inactive pane or establish simultaneous visibility. |
| Rapid scrolling | The final session records 795 intervals across 217 distinct range sets. Of these, 711 last less than 10 ms. Total credited display is 14.900 seconds over a 17.852-second session, including a 2.873-second background interval. Many records do not inflate elapsed display time, but briefly reported ranges must remain distinct from meaningful dwell. |
| Batching | Current receiver-process metrics show 960 events in 169 append batches/disk flushes, approximately 5.68 events per flush, with zero acknowledged duplicate records. These cover only the last two sessions, not all cumulative history. |
| Profiling | Activation: 3 ms is a small startup figure. Profile: 0.00 ms alone does not establish zero continuous overhead; the screenshot does not document the profiled workload, duration, or sampling conditions. |

Only end markers are available for the fold/terminal/split cases, so exact surface
boundaries are inferred from the preceding events and the user's reported actions.
No new paused-versus-recording perceived-latency feedback accompanies this export.

## Additional interruption to clarify

There is a third recovery gap after the surface checks. It references the surface
session's last acknowledged observation at `07:30:55.814Z`, detects failure at
`07:31:08.474Z`, and recovers at `07:31:21.877Z`. The reason is
`session_unavailable`, with **230 unacknowledged events** and explicit uncertain
duration. Those are delivery-uncertain observations, not a count of proven lost
events; a lost receipt could mean some were already persisted.

The interrupted session has a contact timestamp in the final receiver process,
and the process metrics account for both that session and its recovered successor.
That supports expiry within the same receiver process rather than a simple
receiver-process restart for this third gap. It does not establish the cause:
receiver suspension, delays, missed contact, or intentional interruption remain
possible. The timestamps must not be treated as a reconstructed continuous trace.

User clarification was requested about whether the receiver was deliberately
interrupted near the final scrolling test and whether an unexpected reconnect
was observed. If collection expired during ordinary continuous use, investigate
heartbeat/ingestion timing before proceeding. If the interruption was intentional,
record the test conditions and confirm the recovery behavior against them.

## Take and next decision

Recovery, pause preservation, snapshot binding, export integrity, and background
focus handling have useful real-desktop evidence. The terminal case demonstrates
why window focus and reported editor ranges must retain their qualifications.
The fast-scroll trace also supports reporting brief appearance and dwell as
separate evidence, without interpreting either as understanding.

Resolve the third gap and decide how to exclude or qualify hidden/terminal editor
surfaces before claiming the collector gate is complete. A stricter visibility
surface policy needs actual VS Code validation, not inference from the current
raw records. Diff views, horizontal clipping, large-project/all-day memory, and
structured agent correlation still lack this run's validation.

After that scoped collector gate, Phase 2 can implement SQLite/idempotent storage
and conservative current-version derivation. The later full localhost and VS Code
interfaces should carry these limits visibly. Independent quizzes remain later.
