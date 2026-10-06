# Dashboard data contract

The dashboard reuses the SQLite observer receiver and the existing local review
service. It does not generate quizzes or infer authorship. The design references
are the combined HTML and PDF exports in `ui_templates/`.

## Stored observations and current source

An event has `schema_version`, `session_id`, `sequence`, `workspace`, `kind`,
`observed_at`, `monotonic_ms`, and a kind-specific `payload`. SQLite deduplicates
events by session/sequence and source blobs by SHA-256. Visibility payloads bind a
relative path and source hash to inclusive line ranges and timed intervals.
Interactions and filesystem events have unattributed causes; neither identifies
a human author. Session state, connection health and recording gaps are recorded.

`SQLiteStore.overview()` exposes current eligible files with path, content hash,
origin, document uncertainty, tab context, historical interaction count, line
count, reported/dwell/brief/unknown line counts and ranges. Fresh observed dirty
documents can replace saved source. Uncertain files are excluded from line totals.
Unchanged unique blocks can receive evidence from earlier versions. Dwell unions
overlapping panes within a session and takes the maximum across sessions.
These are display estimates, never claims of reading or comprehension.

The dashboard preserves the five observer reasons, labeled Unknown, Never seen,
Glimpsed, Partly seen, and Seen. File chips also show the proportion of lines with
display evidence. Coverage colors interpolate from red (0%) toward yellow for
partial coverage; exact 100% is blue. Unknown is neutral. A separate sample-passed
chip remains distinct from display coverage. No ownership state exists.

`changed_unseen_lines`, `changed_unseen_ranges`, and `change_baseline_hash` come
from a source diff against the most recently captured different snapshot with
visibility activity. Only inserted/replaced current lines outside reported
ranges count. A missing baseline, uncertain source, source changing during the
read, or a comparison above 5,000 lines leaves the count unavailable (`null`),
not zero. These are comparison estimates, not edit attribution or a complete
history of mutations. No earlier viewed version means no change badge.

## Reviews

`reviews.json` stores validated/rejected quiz sets, source manifests, attempts,
immutable answers, completion order and feedback. Set and attempt IDs are stable
UUIDs. Each set contains 3–5 four-option questions. The server withholds keys until
every question is answered and the attempt is completed. Confidence is
`guessed`, `shaky`, or `solid`; correctness means agreement with the stored key.

Only current validated, eligible first-attempt passes count as sample passes.
Later confidently-wrong answers revoke earlier passes on that binding; a later
eligible pass resolves the flag. Practice results cannot create a pass. The
dashboard additionally checks every target/context hash against current source,
including dirty buffers. Changed or uncertain source receives no current credit.
Hatching means no completed result exists for that current file/range. A result
is not necessarily a pass. Historical results remain available in calibration.

## HTTP and ranking

`GET /api/dashboard` returns the overview plus review summaries, evidence lines,
90-day Git commit counts, a verification-aware queue, confidence calibration and
weekly distinct-file counts (`files_touched`) and raw counts (`event_count`). Each
path counts once per week across visibility, interaction and filesystem events.
Timeline lanes show a bounded recent event window explicitly; weekly totals use all events.
Both charts use the same calendar axis, limited to 26 weeks, with empty weeks
retained. A blank week means no stored events, not no actual activity.
`GET /api/dashboard/source?path=…&hash=…` validates current source identity.
Review start/answer/complete are POSTs under `/api/dashboard/review/`; attempt
views and completed results are GETs. Every operation validates workspace and
current source bindings. GET does not write review state or rescan inventories.

Queue order: unresolved confidently-wrong files, uncertain documents, remaining
display gaps (90-day commits then missing lines), fully displayed files. A
current passing sample moves a file below unverified candidates, unless another
sample remains confidently wrong or current source is uncertain. This is an
explicit priority policy, not a numeric risk or comprehension score. Paths plus
hashes protect source requests across refreshes; quiz UUIDs never get reassigned.

## Mockup adaptations

Omitted: numeric comprehension/opacity/risk scores, last-read times, ownership
actions/filters, symbol counts, inherited authorship, net surviving author lines,
agent/human touch classifications, predicted-vs-measured scatter, historical repo
score and delegation ratios. Their data sources do not exist. Insights retains
confidence calibration and the confidently-wrong count; empty panels are omitted.
The Map and share card lead with missing lines, with coverage demoted below them.
The footer's methodology panel defines the short seen/unseen labels and their
scope. Review confidence
is self-graded, but answers are graded locally by the existing server. The work
order's corrected palette and accessible label token override older export colors.

## Validation

Automated checks cover Host/Origin validation, key withholding, immutable answers,
source/context changes, distinct confidently-wrong file counts, pass-driven rank
changes, computed treemap area, calendar spacing and accessible label contrast.
Browser checks cover every screen, per-region hatching, review state hiding,
rank changes, PNG dimensions, empty records, mobile layout and no external calls.
Screenshots and the exported PNG are in ignored `reports/local/dashboard-checks/`.
A disposable copy of the real observer pilot imported 1,933 events / 8 sessions
and returned 5 eligible files with 4 queued; the original JSONL hash was unchanged.
