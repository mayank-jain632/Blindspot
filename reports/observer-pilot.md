# Phase 1: local VS Code collector pilot

Current build: **0.3**. This document preserves the earlier pilot/results. Use
[the current setup, desktop checks and SQL results](observer-03.md) for new runs.

Status: first desktop pass audited; pause/resume and stop/start still need a
follow-up. See [results and the two-minute follow-up](observer-pilot-results.md).
Automated checks exercise
the protocol, collector, transport, and API wiring. They cannot establish how the
real editor reports folds, reloads, or focus. The full visibility MVP comes later.
See [automated results and remaining gates](observer-validation.md).
Extension 0.2.0 adds automatic connection recovery, heartbeats, and batching.
The user has confirmed desktop Stop/Start and Pause/Resume. Follow the
[update and desktop recovery steps](observer-recovery.md): restart the Python
receiver and reload the Development Host once to load both parts of this update.

## What this build does

- VS Code recording controls and a persistent status indicator.
- Explicit opt-in for one trusted, local Git workspace matching the receiver.
- Source snapshots from eligible working-tree files and open documents, including
  unsaved document changes. SHA-256 binds observations to UTF-8 snapshot text.
- Active-editor reported line ranges in a focused VS Code window, sampled at one-second intervals and flushed
  on editor/range/focus changes. A sampling interval over 2.5 seconds is a gap,
  rather than credited display time. No dwell threshold is selected yet.
- Focus loss, pause/resume, source changes, interactions, filesystem notifications,
  pilot markers, and recording lifecycle metadata. Changes are unattributed.
- A loopback-only interactive site with file/event filtering, captured source
  inspection, reported-range highlighting, and a metadata report download.

The inspector aggregates ranges **per exact hash**. It does not carry observations
to different content, compute current codebase coverage, or identify human/agent
authors. Even identical source revisited later only establishes display evidence.

## Start it

The disposable fixture has already been created at `sandbox/observer-pilot`.
Keep the existing `sandbox/phase1-pilot` and real repositories separate.

1. In a terminal at the Blindspot project root, run:

   ```sh
   .venv/bin/python -B -m blindspot observer serve \
     --workspace sandbox/observer-pilot \
     --state-dir reports/local/observer-state \
     --port 7777
   ```

   Keep this terminal running. Expect `Observer: http://127.0.0.1:7777` and the
   pilot workspace path. If the port is occupied, use `--port 7778`; the connection
   file communicates the chosen port to the extension. An existing receiver lock
   requires stopping the previous receiver first.

2. In VS Code, open the **Blindspot project root**, not just `extension/`.
   Open Run and Debug, select **Blindspot: Observer pilot**, then press F5
   (or select Run → Start Debugging). No npm install or compilation is needed.

3. In the new **Extension Development Host** window, verify that Explorer shows
   `observer-pilot` with `visible.py`, `closed.py`, and `atomic.py`. Trust this
   disposable workspace if VS Code asks. Look for **Blindspot: off** in the status
   bar. The extension activates without recording.

4. Press Cmd+Shift+P, select **Blindspot: Start Recording**, and click
   **Start local recording** in the opt-in message. Expect **Blindspot: connected · recording**.
   Consent is remembered for that workspace until the extension reloads; subsequent
   Start commands create fresh sessions without another opt-in prompt.
   If it fails, open View → Output and select **Blindspot Observer**; report the
   error text here. Do not share `connection.json` or its token.

5. Run **Blindspot: Open Local Inspector** from the same command palette (or visit
   `http://127.0.0.1:7777`). Expect snapshots and a session start in the timeline.
   The site refreshes every three seconds. **Switching to the browser takes focus
   away from VS Code, so it stops accruing editor display time.** Return to the
   editor when testing dwell.

The supplied launch configuration sets the connection-file path automatically.
If launching the extension another way, set `blindspot.connectionFile` in user
settings to the absolute path of `reports/local/observer-state/connection.json`.
Only one folder is supported. Remote workspaces are rejected by this pilot.

## First manual pass: about 10–15 minutes

Use **Blindspot: Add Pilot Marker** before each case, naming it `01-baseline`,
`02-scroll`, etc. Marker timestamps let us separate cases later. Clicking the
status bar opens all recording controls.

| Case | Actions in the Development Host | Expected evidence |
|---|---|---|
| 01 Baseline | Open `visible.py`, leave its first screen focused for five seconds. | That source hash gets reported ranges and approximately five seconds of display time; not every line in the file. |
| 02 Scroll | Scroll down several screens, dwell for three seconds, then rapidly scroll up/down. | Ranges change within the same hash. Repeated ranges merge in the version summary; brief transitions have short durations. |
| 03 Lost focus | Keep `visible.py` open, switch to the browser or another app for ten seconds. Return for two seconds. | No editor display time for those ten background seconds. There may be a gap diagnostic if the extension was suspended. |
| 04 Pause | Pause, edit `visible.py`, save, wait five seconds, then Resume. | Paused time has no visibility/snapshots/interactions. Resume captures the resulting source version; it does not reconstruct edits made while paused. |
| 05 Unsaved edit / undo | With recording on, change a return expression without saving. Wait two seconds, then Undo. | A dirty document snapshot with a new hash; undo returns to the original hash. Display evidence stays separate by hash. |
| 06 Closed-file shell edit | Keep `closed.py` closed. In the pilot's integrated terminal, run the command below. | Filesystem event and new disk snapshot, but no visibility for `closed.py` until you open it. Cause remains unattributed. |
| 07 Atomic replace | Keep `atomic.py` closed. Run the atomic replacement command below, then rename `atomic.py` to `renamed.py` in Explorer. | Event(s) and the resulting snapshots. Rename is represented as path create/delete observations, not a proven file identity. Coalescing/missed intermediate versions must be reported. |
| 08 Stop / restart | Stop Recording, wait five seconds, Start Recording again. | Session end then a new session ID. No display evidence for the stopped interval. |

For case 06, ensure the integrated terminal's current directory is
`sandbox/observer-pilot` (the new host normally starts there), then paste:

```sh
printf '\n# closed-file shell edit\n' >> closed.py
```

For case 07, from that same pilot terminal:

```sh
node -e 'const fs=require("node:fs"); fs.writeFileSync("atomic.py.tmp", "def label():\n    return \"after\"\n"); fs.renameSync("atomic.py.tmp", "atomic.py");'
```

Terminal text is not captured as source visibility. VS Code may retain the last
active editor while keyboard focus is in the terminal; reported editor ranges can
therefore continue accruing time for that pane. The pilot labels keyboard focus
as unverified. These commands only
mutate the disposable fixture. Saving is not required for document snapshots;
disk and document observations may arrive in different orders.

## Surface and recovery cases

After the first pass, test these if convenient; otherwise list them as not run.

- **Folds:** fold a function in `visible.py`. Inspect the reported ranges. They
  may include folded line spans, so highlighting is not a claim that hidden lines
  were displayed. Tell us whether the ranges include the collapsed body.
- **Horizontal clipping:** enable a long line and scroll horizontally. This
  pilot records line spans, not character columns; it cannot judge clipped text.
- **Terminal/sidebar focus:** keep the source pane visible but put keyboard focus
  into the integrated terminal or sidebar. Tell us whether editor ranges continue
  to accrue time. They can: `activeTextEditor` is not an editor-focus guarantee.
  Maximize the terminal too, to test whether hidden editor ranges remain reported.
- **Split editors:** split the editor and open different files. Only the active
  text editor is sampled; an inactive visible pane is unsupported.
- **Diff view:** use Source Control to open a diff. This pilot cannot reliably
  distinguish every modified diff surface from a normal file editor. Report what
  the API recorded; diff visibility is not validated coverage.
- **Receiver restart:** use the [recovery pass](observer-recovery.md). The extension
  should show reconnecting, automatically create a new session after the receiver
  returns, and record the uncertain gap. Paused recording stays paused; Stop
  cancels retries. No activity during the interruption is reconstructed.
- **Host reload:** run Developer: Reload Window in the Development Host. Recording
  should be off afterwards and require Start again. Abrupt shutdown can leave
  the earlier journal session without an end record; that is a gap.
- **Branches:** after committing only the fixture's changes, switch branches
  with differing fixture contents. Look for resulting snapshots and separate
  hashes. Intermediate filesystem transitions can be coalesced; no Git history
  or rename inference is made by the collector yet.
- **Overhead:** run Developer: Show Running Extensions, find Blindspot Observer,
  and record the reported activation/runtime figures. Tell us whether typing,
  scrolling, or saving felt delayed with recording on versus paused. Activation
  time alone is not continuous recording overhead; report the metric label too.

Agent hooks, concurrent agent correlation, automated unchanged-range mapping,
remote surfaces, and large-repository performance follow this first pass. No hook
or agent configuration is installed by this build.

## Report back

1. Run **Blindspot: Stop Recording** and wait for the events to arrive.
2. In the localhost site, click **Download report**. This exports metadata,
   relative file paths, workspace path, and source hashes, but no snapshot text.
3. Send the report file here, or paste the `event_counts`, `displayed_versions`,
   diagnostic events, and session entries. Include this short checklist:

   ```text
   Start / status indicator:
   Baseline and scroll:
   Background / paused time excluded:
   Unsaved edit and undo hashes:
   Closed-file edit and atomic replacement:
   Stop / restart:
  Folds / splits / diff / receiver restart (or not run):
   Terminal/sidebar focus and maximized terminal:
   Runtime metric label + value, and perceived slowdown:
   VS Code version:
   Errors or unexpected behavior:
   ```

4. Stop the receiver with Ctrl+C after downloading.

An offline metadata report is also available **after stopping the receiver**:

```sh
.venv/bin/python -B -m blindspot observer report \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state
```

## Data and limits

The receiver writes `events.jsonl` and a private connection file in
`reports/local/observer-state`, outside the inspected pilot. The journal includes
**source text** to let us verify version binding. It is ignored by the parent Git
repository and is not sent to a model or cloud service. The downloaded metadata
report still includes local paths; review it before sharing publicly.

The extension only reads inspected source. The fixture setup script and your
manual test edits are the operations that change the pilot. Neither the new
collector nor this pilot modifies existing transcript/evidence/quiz stores.

Eligible inventory: tracked and nonignored new files in a local Git workspace,
selected by the extension's declared source extensions (including Markdown and
configuration text). Excludes `.git`, `.claude`, `.blindspot`, environments,
vendor/build directories, locks/minified assets, `.env` files, binary text and
symlinks. Up to 500 candidate paths and 256 KiB per source snapshot; inventory
diagnostics expose truncation. Submodule content and other workspace folders are
not enumerated. Unsupported/excluded source has no viewing claim.

This is an experiment, not complete event history: filesystem events can coalesce,
atomic intermediate contents can be missed, and no observer can recover activity
while stopped. Ranges are inclusive, one-based line spans over the captured text;
the trailing empty line after a newline counts toward snapshot line count. Folds,
characters off-screen, terminal source displays, inactive panes and other apps
are not reliable source-visibility evidence here. No percent understood or percent
viewed is shown.

`focused: true` means VS Code's window-focus observation, qualified by
`focus_scope: "window"` and `editor_focus: "unverified"` in extension records.
It is not evidence of keyboard focus or attention in the source pane.

The append journal is temporary Phase 1 storage, batched, fsynced and retry-idempotent, with
one receiver writer. A partial/corrupt journal refuses startup rather than silently
discarding records; preserve it and use a new state directory, updating the
connection setting/launch path. Automatic repair, retention controls, SQLite,
large-repository optimization, and migrations belong to later work. The journal and
website retain/read all pilot events in memory; keep this first run short.

## Next gate

Compare your known actions against the downloaded records, fix capture gaps and
measure overhead, then extend the experiment to structured agent context. Only
after those checks should Phase 2 implement durable storage and reliable coverage
derivation. Phase 3 ships both the interactive localhost visibility dashboard and
the extension interface. Quiz generation remains paused until Phase 4.

VS Code's [extension tutorial](https://code.visualstudio.com/api/get-started/your-first-extension)
documents the Development Host workflow; its
[API reference](https://code.visualstudio.com/api/references/vscode-api) documents
the editor, document, focus and filesystem events used here.
