# Observer 0.3: SQL storage and current-source visibility

Implemented on 2026-10-04. Automated checks pass; the new desktop acceptance pass
below remains open. Quiz generation stays paused. This follows the
[implementation plan](implementation-plan-03.md) and the
[approved roadmap](roadmap-proposal.md).

## What changed

- Every eligible plain-text pane in `visibleTextEditors` contributes its reported
  ranges while the VS Code window is focused, including inactive split panes.
  Background tabs are recorded separately as context, without display credit.
  Diff, notebook and remote surfaces are excluded. At most 16 panes are sampled.
- Recording diagnostics include bounded recent request timings, queue events and
  bytes, last accepted session/sequence, heartbeat timestamps, loop delay and
  recovery details. `Blindspot: Show Recording Diagnostics` opens the Output
  channel. A metadata health event is emitted about every 16 seconds; paused
  sessions retain health monitoring without source/interaction collection.
- `Blindspot: Toggle Editor Visibility Exclusion` suppresses display evidence
  while retaining recording and change context. Use it for hidden-editor work,
  such as a maximized terminal when the API still reports editor ranges. The
  status bar explicitly shows `visibility excluded`; toggle again to restore.
  Exclusion applies to all panes and is manual, not automatic occlusion detection.
- SQLite replaces JSONL for new observation ingestion. One receiver owns the
  writer lock. Each validated batch commits as a transaction with WAL and FULL
  synchronization; retries use unique session/sequence keys and exact-content
  fingerprints. Sources are deduplicated by hash. Invalid batches and failed
  commits receive no success acknowledgement. Storage failures halt writes.
- Current-source estimates use the eligible saved Git working tree, including
  nonignored new files, overlaid with fresh observed unsaved buffers. Hashes bind
  raw observations to exact contents. Verified unique unchanged blocks can carry
  evidence to a newer version at the same path; changed or ambiguous lines cannot.
- The interactive localhost view and `Blindspot: Show Codebase Overview` share
  the same interface and `/api/overview` contract. Both offer file filtering,
  brief/dwell/unknown line counts, current-source highlighting, interaction/tab
  context, recording health and the newest 200 metadata records. Double-click a
  source line in the VS Code view to open it. Full metadata downloads are available
  from localhost; the panel directs users there or to the report CLI.

The extension reads observed source and keeps application state outside the
observed checkout. Agent attribution and quiz behavior are unchanged. The
localhost overview and collector require no model session or cloud service.

## Measurement contract

| Category | Meaning |
|---|---|
| Reported lines | Matching current lines with some recorded reported-range time |
| Dwell lines | Reported lines meeting the chosen display-time filter |
| Brief lines | Some reported time, below that filter |
| Unknown lines | No matching recorded display evidence; not proof of being unread |
| Uncertain file | The current unsaved buffer cannot be established safely; excluded from line totals |
| Interaction events | Historical edits/selections with qualified or unknown causes; not an understanding score |
| Open tab | Last recorded tab context; freshness is shown separately |

The default 1,000 ms dwell filter is a product reporting choice, not a validated
attention threshold. The views also offer 250 ms and 3 seconds. Intervals for the
same line are unioned within each session so mirrored panes do not double time.
Across sessions the maximum duration is used, conservatively avoiding addition
of concurrent recordings whose monotonic clocks cannot be aligned. Within a
session multiple visits can accumulate. This can undercount separate sessions.

Exact content hashes retain evidence on undo/revert. Cross-version mapping uses
unique contiguous equal line blocks and is disabled above 5,000 lines; exact-hash
matching still works. Path changes receive no inferred mapping. Raw evidence is
never rewritten. Mapping verifies equal text, not unchanged semantics or control
flow; historical display does not prove current understanding.

A dirty buffer is current only with a fresh live recording heartbeat and a
matching snapshot. Paused, ended, interrupted, conflicting or unsupported dirty
buffers make that file uncertain. A new explicit baseline supersedes interrupted
session document state; other active conflicting buffers remain uncertain. A
saved or closed document releases its dirty overlay. Stopping with unsaved edits
therefore makes that file uncertain until it is observed again or saved/closed
while recording. No disk fallback is presented as the established unsaved version.

Eligibility remains capped at 500 candidate paths, 256 KiB UTF-8 per file, no
symlinks, ignored/generated/vendor/environment/lock/minified files. Logical lines
include a trailing empty line. Open tabs alone give no line credit. Public VS Code
ranges cannot establish keyboard focus, actual terminal occlusion, character
clipping, eye movement or reading. Older active-pane records retain their original
measurement scope. No existing history is reconstructed as multi-pane evidence.

## Load this build

These steps reuse the existing pilot. Development work tested only a temporary
copy of its journal; your live state has **not** been migrated by this build.

1. In the Development Host, run **Blindspot: Stop Recording**. In the receiver
   terminal press Ctrl+C. This prevents the previous receiver from adding JSONL
   records while the new receiver imports them.
2. From `/Users/mayankjain/Projects/blindspot`, run:

   ```sh
   .venv/bin/python -B -m blindspot observer serve \
     --workspace sandbox/observer-pilot \
     --state-dir reports/local/observer-state \
     --port 7777
   ```

   The receiver creates `observations.sqlite3` in that state directory and imports
   the existing `events.jsonl` atomically once. Original journal bytes stay intact;
   new records go to SQL. Incomplete/conflicting imports refuse startup and retain
   the original. A changed legacy journal after import also refuses startup rather
   than silently mixing histories. Keep all database files together; WAL files can
   contain committed records while the receiver is running.
3. In the existing **Extension Development Host**, run **Developer: Reload
   Window**. If it is closed, open the Blindspot root in VS Code and use the
   existing **Blindspot: Observer pilot** F5 launch. No dependency installation or
   build step is needed. Confirm **0.3.0** in **Developer: Show Running Extensions**.
4. Run **Blindspot: Start Recording** and accept the local opt-in. Expect
   `Blindspot: connected · recording`. The extension refuses an old receiver that
   lacks SQL/pane capabilities rather than submitting incompatible observations.
5. Run **Blindspot: Show Codebase Overview**. Also run **Blindspot: Open Local
   Inspector** and reload the localhost browser tab. Both should show the same
   workspace, current files and chosen dwell filter. Allow about five seconds for
   refresh. Switching to the browser removes VS Code window focus and ends display
   accrual there. Viewing the panel alone does not establish source attention.

This is the repository development build. The panel shares assets with the Python
package beside `extension/`; standalone VSIX packaging is a later delivery task.

## Focused desktop acceptance: about ten minutes

Use **Blindspot: Add Pilot Marker** before each case. Use existing pilot files;
only make edits in the disposable pilot. Save those edits before the final Stop.

| Marker | Specific actions | Expected result |
|---|---|---|
| `03-passive-split` | Split VS Code into two source panes, open different files, leave both visible for five seconds while editing/selecting only one. | Both panes receive `visibility` records with distinct `pane_id`; the passive pane has `active: false`. Both files can gain line evidence. |
| `03-background-tab` | Open another source file, switch that pane back to the previous file, then leave it for five seconds. | The background tab is context only; its lines gain no new evidence during this marked interval. Earlier evidence does not disappear. |
| `03-mirror` | Split the same file so both panes show the same few lines for several seconds. | Raw records show both panes. Derived dwell unions overlap, not twice the elapsed time. Use export to compare intervals; threshold counts alone do not measure the elapsed duration. |
| `03-exclude` | Toggle visibility exclusion, maximize the integrated terminal and wait five seconds. Restore the editor, toggle exclusion off and wait two seconds. | Status says `visibility excluded` during the hidden interval; no display credit there. Visibility resumes afterwards. |
| `03-current-buffer` | With recording on, edit a visible line without saving and wait two seconds. Open the overview, then undo and inspect again. Save before moving on. | The overview labels the unsaved version. Changed lines need their own evidence; unique unchanged blocks may retain earlier evidence. Undo returns to the original hash. |
| `03-health` | Leave recording on at least 20 seconds, then run Show Recording Diagnostics. Pause/resume once. | Queue sizes, accepted sequence and recent request timings appear, with a `connection_health` event in the timeline. Paused time adds no source-display records. |
| `03-recovery` | Stop the receiver, wait until reconnecting, restart the same command and wait for automatic recovery. | A fresh session and qualified recording gap; original and newly recorded SQL history remain. The gap contains receiver/client diagnostics when available. |
| `03-two-views` | Compare the same file and dwell setting in both views, then double-click a line in the VS Code inspector. | Matching data; the panel opens the corresponding local source line. Unknown and brief lines are visibly distinct. |

Report whether each case passed, any errors or perceived slowdown, and the new
metadata export path. Diagnostics explain observations; an expired heartbeat is
not by itself proof of which component stalled. No tests require touching real
repositories, old Claude transcripts or recorded quiz attempts.

After stopping recording, download from localhost. Offline exports are also
available after stopping the receiver:

```sh
.venv/bin/python -B -m blindspot observer report \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state

.venv/bin/python -B -m blindspot observer overview \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state \
  --dwell-ms 1000
```

Offline overview cannot verify fresh unsaved buffers. It can derive evidence for
current disk files. Reports contain metadata, paths and hashes, but no source
text; the private SQL store itself contains captured source text.

## Automated evidence

- **115 Python checks passed**, including all existing transcript/evidence/review
  regressions, SQL atomicity/idempotency, forced commit failure, a real subprocess
  crash rollback, import/reopen, path/eligibility guards, dirty/conflicting buffers,
  unchanged/ambiguous mapping and mirrored-pane time union.
- **34 Node checks passed**, including lifecycle/recovery, passive panes,
  visibility exclusion, unsupported surfaces, bounded diagnostics, shared view
  rendering, stale inspection invalidation and webview navigation/credential
  isolation. Syntax checks passed for all extension modules and browser script.
- Real Node extension/transport → Python SQLite HTTP checks pass, including
  passive split events, repeated start/stop, pause/resume, persisted history after
  restart/token rotation, workspace locking, API authentication and source-hash
  conflict responses. Editor surfaces in these tests are API mocks.
- Copied the actual **1,933-event, eight-session** journal into temporary state:
  all events reconstructed exactly, 39 source blobs deduplicated, reimport/reopen
  idempotent, `PRAGMA integrity_check` returned `ok`, original unchanged. Raw
  journal SHA-256: `5077d26e646ec4c9d46eaea7f1281562f8b49cd19836659e12c89cac5e3c0261`.
  This is the source-bearing journal checksum, not the earlier metadata-export
  checksum. Local metrics: `reports/local/observer-sqlite-import-audit.json`.
- Synthetic single-pane benchmark: **1,060 events in 49 committed transactions**,
  all ordering/hash/time/reopen gates passed. Receiver CPU about 138 ms over a
  6.98-second workload; callback p95 0.126 ms, batch-request p95 8.68 ms. A SQL
  reopen took 0.82 ms; full metadata export took 7.38 ms. These are one local run,
  not desktop latency or multi-pane/all-day performance guarantees. Local metrics:
  `reports/local/observer-benchmark-03.json`. Reproduce with:

  ```sh
  .venv/bin/python -B scripts/benchmark_observer.py \
    --output reports/local/observer-benchmark-03.json
  ```

## Roadmap position

Collector validation is supported by the previous desktop audit; the 0.3 pane and
UI behavior needs this focused desktop gate. Durable observation storage is now
implemented and tested. The visibility MVP has its first shared working prototype.
Next: audit the new desktop export, fix concrete failures, then measure a longer
real-work session with the views open. Retention, larger-history incremental
summaries and standalone packaging follow. Structured agent context can then be
added without making it a prerequisite for visibility. On-demand quiz generation
comes after the visibility workflow is useful and stable; difficulty tuning stays
later.

Implementation references: Python's [sqlite3 transaction documentation](https://docs.python.org/3.11/library/sqlite3.html),
[SQLite WAL](https://www.sqlite.org/wal.html), and the official
[VS Code API declarations](https://raw.githubusercontent.com/microsoft/vscode/main/src/vscode-dts/vscode.d.ts)
for `visibleTextEditors`, tab groups and plain-text/diff tab inputs. The API provides
reported visibility and tab identity, not proof of actual pixel visibility.
