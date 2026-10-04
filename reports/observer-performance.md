# Collector performance validation: observer 0.2.1

Current build: **0.3**. This document preserves the earlier pilot/results. Use
[the current setup, desktop checks and SQL results](observer-03.md) for new runs.

Date: 2026-10-04. The next collector validation step has been run against a real
local HTTP receiver using disposable state. This is measured synthetic overhead,
not a desktop typing-latency benchmark. Phase 1 remains open for desktop recovery
and editor-surface validation. Quiz generation remains paused.

## Changes delivered

Added a repeatable benchmark using the production collector, transport, journal,
and HTTP receiver. It exercises repeated viewport callbacks at 8 KiB and 256 KiB,
pause, 500 baseline source snapshots, changing source versions, alternating
ranges, focus gaps, heartbeat, batching, metadata generation, and journal replay.
It creates an empty temporary workspace and temporary state, not a real project
inventory; VS Code APIs, Git enumeration, watchers, and browser rendering are
outside this workload. No pilot files, logs, or quiz records are modified.

The baseline exposed repeated full-content validation/hashing during unchanged
viewport callbacks. Observer 0.2.1 now retains one validated path/text/hash pair,
at most one 256 KiB source, and reuses that hash only when both path and exact
contents match. It does not trust a document version number alone. Edits,
undo/revert, path switches, and intervening disk/document versions still bind to
their actual content. Stop releases the cached string.

Paused range/active-editor/focus callbacks now stop before calling `getText()`.
Resume still captures resulting contents; no paused edits are reconstructed.
This changes callback work, not visibility categories or source eligibility.

## Recorded results

Local environment: Apple Silicon (`arm64`), Python 3.11.14, Node v22.22.2.
Metrics are from one before/after run; scheduler and machine load can vary.
The microbenchmark repeatedly supplies the same source string, giving the cache
its best case. It excludes VS Code's `getText()` cost and newly allocated equal
strings may take longer to compare. It is not a promise of these savings for
every editor event.

| Measurement | Before: 0.2.0 | After: 0.2.1 |
|---|---:|---:|
| 3,000 unchanged callbacks, 8 KiB: collector CPU | 38.818 ms | 3.558 ms |
| 3,000 unchanged callbacks, 256 KiB: collector CPU | 872.925 ms | 4.045 ms |
| 256 KiB callback p95, unchanged-string microbenchmark | 0.306459 ms | 0.000459 ms |
| Mixed workload events generated / persisted | 1,060 / 1,060 | 1,060 / 1,060 |
| Mixed workload snapshots | 550 | 550 |
| HTTP batches / disk flushes | 41 / 41 | 44 / 44 |
| Mixed callback p95 | 0.129750 ms | 0.240833 ms |
| Batch HTTP response p95, including JSON receipt | 8.061667 ms | 8.180875 ms |
| Node RSS high-water sample | 86.77 MiB | 88.00 MiB |
| Python process RSS high-water mark | 38.06 MiB | 41.38 MiB |
| Journal replay | 45.324 ms | 41.805 ms |

The repeated-unchanged-source microbenchmark improves. The mixed workload does
**not** show a clear overall latency or memory improvement in this pair: callback
p95 and process CPU increase, and batch grouping varies with timing. Do not turn
the cache result into a general performance claim. Both mixed runs finish in
roughly 6.6 seconds, including intentional 10 ms waits between 600 callbacks.
The 10 ms event-loop delay sampling baseline is included in those delay metrics.

The after run uses a maximum queue of 64 events, zero retries, and a maximum batch
body of 587,862 bytes. The journal is about 5.11 MiB and metadata export about
0.58 MiB. Its report builds in 4.940 ms. Source-bearing journal memory grows with
history; short synthetic runs do not establish all-day or large-project behavior.
These measurements support continued collector testing, with SQLite/retention
still needed before treating this storage as an everyday product.

Integrity checks pass in both runs: event count, contiguous sequences, every
snapshot SHA-256, total reported display time, clean session end, identical replay,
and no observed-workspace writes. These check internal fidelity, not whether a
real folded or obscured pane was displayed.

Artifacts (ignored local metrics; no source/token payloads):

- `reports/local/observer-benchmark-before.json`
- `reports/local/observer-benchmark-after.json`

Reproduce the current build from the Blindspot root:

```sh
.venv/bin/python -B scripts/benchmark_observer.py \
  --output reports/local/observer-benchmark-repeat.json
```

Node is required; there are no new dependencies. The benchmark uses a temporary
loopback port and cleans up its temporary workspace/state. Omitting `--output`
prints only the metrics. The before artifact records the earlier 0.2.0 build;
the command measures whichever collector version is currently checked out.

## Regression checks

All **24 Node tests and 17 Python observer/integration tests pass** after this
change. The source-cache regression includes unchanged contents, different
contents with the same declared document version, reversion, path changes, and
disk/document overlap. The paused host test fails if a paused callback reads
document contents. Existing real-receiver recovery, rotated credentials,
focus/pause timing, batch idempotency, source binding, and CLI lifecycle still pass.
The earlier full 96-test Python suite was not rerun for this extension-only
change; the complete observer/integration portion was rerun.

## Remaining desktop checks

Reload the Extension Development Host once to load 0.2.1. If the receiver is
already on the 0.2.0 backend, it needs no additional restart for this cache change.
If the earlier update has not been loaded, follow the receiver restart and browser
reload instructions in [the recovery guide](observer-recovery.md).

1. Run the recording/paused/disconnected-Stop cases in that recovery guide and
   save the cumulative export outside the observed workspace.
2. Mark `surface-fold`, fold a function in `visible.py`, dwell three seconds,
   and report whether highlighted spans include the hidden body.
3. Mark `surface-terminal`, focus the integrated terminal for five seconds, then
   maximize it for five seconds. Return to the editor. The current API can retain
   editor ranges; record what happened instead of interpreting this as reading.
4. Mark `surface-split`, open a second file in a split pane, and switch between
   them. Only the active pane is supported. Diff views and horizontal clipping
   remain explicitly unvalidated.
5. Run **Developer: Show Running Extensions** and report Blindspot's labeled
   activation/runtime metrics, along with any typing/scrolling delay compared
   with paused recording. These are separate from the synthetic figures above.

Send the export path and observations back. Desktop claims remain pending until
those results exist. Next after collector acceptance: SQLite storage and
conservative current-version derivation, then the full localhost/VS Code MVP,
then independent on-demand quizzes.
