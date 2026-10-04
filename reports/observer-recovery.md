# Connection recovery and batching: observer 0.2.0

Current build: **0.3**. This document preserves the earlier pilot/results. Use
[the current setup, desktop checks and SQL results](observer-03.md) for new runs.

Built 2026-10-04. The user has confirmed desktop Stop/Start and Pause/Resume.
Recovery and batching pass automated checks; the desktop recovery pass below
remains to be run. Quiz generation stays paused.
The current extension is 0.2.1, adding
[source-hash caching and measured synthetic overhead](observer-performance.md).
The recovery protocol/backend remains the 0.2.0 build described here.

## Behavior

The status bar distinguishes connected recording, connected pause, retrying, and
reconnecting. A heartbeat every two seconds checks the connection even when
paused or no editor is active. The receiver treats a monitored session as stale
after seven seconds without an accepted event or heartbeat. Legacy sessions are
unmonitored rather than assumed connected. Heartbeats update process-local state;
they do not append events or trigger disk flushes.

On connection failure, collection stops and automatic probes retry after 2, 4,
then at most 8 seconds between attempts. Each probe rereads the connection file,
so a restarted receiver's new port/token can be used. A recovered recording gets
a fresh session ID and a `recording_gap` event referencing the previous session.
Paused recording stays paused. **Stop cancels reconnection**, including a pending
probe; **Blindspot: Reconnect Now** requests an immediate probe. A changed
workspace, incompatible receiver, invalid event/configuration, or storage failure
stops the attempt with an error instead of retrying indefinitely.

Gap metadata includes detection and recovery timestamps, the last acknowledged
observation timestamp, reason, and number of unacknowledged events. Its duration
is explicitly uncertain. The last acknowledgement is an observation timestamp,
not proof that the connection remained healthy afterwards. An unacknowledged
event may already be on disk when a response was lost. Failed queues are discarded;
there is no disk spool or reconstruction of activity during disconnection.
Recovery captures resulting source snapshots only when recording resumes.

The localhost inspector polls every three seconds, labels stale/unavailable
data, disables export while unavailable, and pairs a fresh local cookie after
token rotation. It shows heartbeat-derived session state, recorded interruptions,
and events per disk flush for the current receiver process. Historical event
counts remain cumulative across restarts; process metrics reset on restart.

## Batching and persistence

- Ordinary events wait up to 200 ms before transmission. Lifecycle/state/gap
  events and full batches flush immediately. Drain flushes everything pending.
- Batches contain at most 64 events and 2 MiB of UTF-8 JSON. The in-memory queue
  is bounded at 512 events or 8 MiB; overflow suspends recording and enters
  recovery with delivery uncertainty recorded.
- A transient failure retries the exact serialized batch once. Session/sequence
  identity makes accepted retries idempotent. A receiver-instance identifier
  prevents continuing an old session after a receiver restart.
- The receiver validates the entire batch before appending new events and calls
  `fsync` once per batch with new records. Duplicate-only retries do not write.
  Journal records retain their existing JSONL format and replay compatibility.
  This is validation atomicity, not a crash-atomic database transaction: disk
  failure can leave a prefix or incomplete line. Persistence errors stop writes;
  an incomplete journal still refuses startup and is preserved for inspection.
- Adjacent intervals coalesce only for identical path, hash, and reported ranges,
  with a maximum total duration of 2.5 seconds. Different ranges/versions and
  intervening metadata remain distinct; display time is preserved. A one-second
  tick flushes accumulated intervals, and sampling delays stay unknown gaps.

A synthetic 200-event transport burst uses four requests instead of 200,
preserving event order. A three-record receiver batch uses one disk flush, and
an identical retry adds none. These measure request/write reduction under test;
they do not establish continuous editor latency or large-repository performance.
The journal and inspector still load pilot history in memory.

## Load the update once

Both the Python receiver and extension changed. Preserve the existing state
directory and first report; no reset or reinstall is needed.

1. Stop recording in the Development Host. Stop the old receiver with Ctrl+C.
   From the Blindspot project root, restart it:

   ```sh
   .venv/bin/python -B -m blindspot observer serve \
     --workspace sandbox/observer-pilot \
     --state-dir reports/local/observer-state \
     --port 7777
   ```

2. In the **Extension Development Host**, run **Developer: Reload Window** once
   (or launch **Blindspot: Observer pilot** with F5 again). Start Recording and
   accept the first opt-in after reload. Expect **Blindspot: connected · recording**.
   New session starts report `collector_version: "0.2.1"`.
3. Reload the localhost inspector once to load the new browser script. Leave the
   tab open; subsequent receiver restarts should recover without a page reload.

## Desktop recovery pass: about five minutes

Use only `sandbox/observer-pilot` for this pass. The original report remains the
audited artifact; this run appends new observations to the same local journal.

1. **Recording disconnect:** open `visible.py`, add marker `recovery-recording`,
   and leave it focused for three seconds. Ctrl+C the receiver, wait at least
   five seconds, then check that the status says **reconnecting · recording**.
   The browser should label its data stale and disable Download. Restart the
   receiver using the command above. Without Start or Resume, expect
   **connected · recording**, a new session, and a recovery-gap record.
   Automatic probing may take roughly ten seconds after the receiver returns.
   Switching to the terminal/browser stops accruing focused editor time.
2. **Paused disconnect:** Pause Recording, stop the receiver, wait five seconds,
   and restart it. Expect **connected · paused** after recovery. Leave it paused
   for another five seconds, then Resume explicitly. No source/display activity
   should appear in the recovered session before Resume.
3. **Cancel while offline:** stop the receiver during recording, wait for
   **reconnecting**, then Stop Recording. Restart the receiver and wait fifteen
   seconds. Expect **off**, with no automatic new session. Start explicitly to
   record again.
4. **Export:** stop recording, open the inspector, and check the gaps and session
   states. Download as `blindspot-observer-recovery.json` into Downloads or
   `reports/local/`, outside the observed workspace. Send the path and any status,
   connection, typing, or scrolling issues back here. Do not share the connection
   file or token.

If a receiver error mentions an incomplete journal, preserve that directory and
report the error; do not delete or edit the journal. Recovery does not repair
corrupt storage. Host reload still requires explicit Start and does not itself
continue a previous session.

## Remaining gate and roadmap

Phase 1 still needs desktop recovery, folds/terminal/sidebar/diff/split surface
checks, and measured overhead. Structured agent context remains separate from
visibility evidence. Once collector fidelity is established, Phase 2 adds SQLite
and conservative visibility derivation; Phase 3 delivers both full localhost and
VS Code visibility interfaces. Phase 4 resumes independent, on-demand quizzes.
