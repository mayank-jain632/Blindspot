# Observer 0.3 implementation plan

User approved implementation of diagnostics, multi-pane observations, SQLite,
current-version derivation, and shared localhost/VS Code interfaces on 2026-10-04.
Quiz generation remains paused. The last interruption may have been accidental;
its root cause is not established by that clarification.

## Order and acceptance

1. Freeze evidence meanings: open tabs are context; all reported-visible plain
   source panes contribute qualified display evidence, active or passive. Edits
   and selections remain separate, unattributed where necessary. Neither is
   attention or understanding. Unknown terminal occlusion remains disclosed;
   an explicit visibility-exclusion control lets users mark hidden-editor work.
2. Add connection diagnostics: queue length/bytes, accepted sequence, recent
   request/heartbeat latency and failure, receiver contact age, recovery reason,
   and sampling delays. Keep a bounded diagnostic history without source/tokens.
3. SQLite with versioned schema, full-sync transactions, unique session/sequence
   keys, content-addressed snapshots, per-pane validation, and one process writer.
   Import the original JSONL atomically and idempotently; preserve bytes and older
   evidence/quiz stores. No history-size cache for ingestion; full export is an
   explicit operation, normal UI fetches bounded timeline and derived summaries.
4. Inventory eligible current saved source with local Git read operations, and
   overlay fresh open-document snapshots, including unsaved versions. Stale,
   paused, disconnected and exclusion intervals never imply exhaustive viewing.
   Exact hashes match directly. Carry evidence across changes only on unique
   contiguous unchanged line blocks, retaining source evidence and accumulated
   dwell. Repeated/ambiguous text and changed lines receive no inferred credit.
5. Shared overview and file inspection: eligible current line counts, reported
   brief/dwell/unknown counts, interaction and open-tab context, review reasons,
   recording health. Both localhost and a VS Code view consume one contract.
   A disclosed 1,000 ms default is a configurable display filter, not a validated
   attention threshold. Navigation reveals source and derivation reasons.
6. Tests: rollback/conflicts/retry/restart, interrupted and duplicate import,
   multi-pane duration union, edit/undo/repeated-block mapping, dirty overlays,
   disappeared files, eligibility/symlink guards, diagnostics privacy, and both
   views. Re-run existing regressions and benchmark against SQLite. Audit a copy
   of the user journal; do not migrate the live pilot state during development.

## Scope and manual gate

Implement for one trusted local Git workspace. SQLite is Python stdlib; no cloud
service or model session is required. Diff, remote, notebooks and exact character
occlusion are unsupported. `visibleTextEditors` is qualified API evidence, not
physical display verification. An open background tab alone gets no display
credit. Dwell is interval union per exact source/line so mirrored panes do not
double counts. Current unknown counts mean insufficient evidence, never "unread".

Load both receiver and extension once when ready. Desktop acceptance checks will
cover passive split panes, background tabs, visibility exclusion while the panel
is maximized, dirty saved-source differences, and recorded connection diagnostics.
Passing synthetic/API mocks will not be described as desktop validation.

## Completion record

All six implementation steps are built. Validation: 115 Python checks, 34 Node
checks, extension/browser syntax checks, real SQL receiver recovery, exact import
and reopen of a temporary copy of the original 1,933-event journal, and an updated
synthetic SQL benchmark. No original state migration or source edits were needed.
See [results, precise measurement choices, and the remaining desktop gate](observer-03.md).
The manual gate is pending; no broader phase or desktop accuracy claim is made.
