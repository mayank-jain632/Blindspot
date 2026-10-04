# Historical design — superseded for presentation v1

This preserves the earlier detailed design and implemented contracts.
The current scope is [DESIGN.md](../DESIGN.md). These historical plans are not
requirements or prerequisites for the presentation MVP.

# Blindspot — design and validation plan

> A local tool that shows which versions and regions of your codebase have
> observably appeared in your editor, with optional understanding checks.

Revision 6. This is a product direction and an implementation contract for the
first prototype. It is not evidence that the product assumptions have been
validated. The previous revision's absolute authorship claims are withdrawn.

**Current status: observer 0.3 implemented; focused desktop validation next.**
The [approved roadmap](roadmap-proposal.md) is the authoritative product
direction and delivery order. Quiz generation stays paused. The new
[0.3 build and measurement contract](observer-03.md) implements recording
diagnostics, all reported visible eligible plain-text panes, SQLite observation
storage, current-version derivation, and a shared localhost/VS Code overview.
Background tabs are context only. Unique unchanged blocks at the same path can
carry evidence across versions; changed and ambiguous lines receive no inferred
credit. Brief, dwell and unknown lines are distinct, with a disclosed configurable
filter. None proves reading or understanding. Uncertain unsaved documents are
excluded from line totals.

115 Python and 34 Node checks pass, including real SQL receiver recovery and an
exact import of a temporary copy of the 1,933-event pilot journal. No live pilot
migration was performed during development. Previous desktop Stop/Start and
Pause/Resume are confirmed; the new multi-pane, mapping and shared-view behavior
requires the linked manual acceptance pass. Durable observation storage and the
first visibility MVP prototype now exist. Agent hooks, retention, packaging,
larger-history incrementality and on-demand quizzes remain ahead.

The earlier logs-first sections below describe the existing CLI's contract and
historical plans, not the current product scope or phase order. Their proposed
full application SQL schema has not been implemented; 0.3 has a separate versioned
observation schema that preserves existing evidence and quiz stores.

**Earlier milestone: terminal review experiment (§12, Phase 2).**
The earlier evidence implementation and repository checks are complete for the
supported scope. Their historical phase numbers differ from the approved
roadmap. The existing terminal workflow remains available; it does not establish
viewing coverage. Collector validation now takes priority over further quizzes.

Implementation status: evidence reports and the terminal review lifecycle now
exist. See [Phase 1 validation](phase1-validation.md) for Saphire,
Portfolio, Collatz, and controlled-pilot evidence checks, and
[Phase 2 validation](phase2-validation.md) for lifecycle tests and a
scripted Collatz smoke run. One workflow test and one understanding review are
recorded. The latter scored 2/3 against the key and felt too hard to the user;
independent, on-demand quiz generation is deferred until after the visibility MVP,
with difficulty tuning still later. Quiz usefulness remains unestablished.

---

## 0. Why the scope changed

The original idea was to find agent-written lines a developer had never seen.
Retrospective session logs do not establish that. File-level history is a useful
starting point, but it also does not establish exclusive authorship, reading, or
understanding.

A previous audit reported 22 Claude Code sessions, 39,087 entries, 413 Edit/Write
calls, and 616 Bash calls. It motivated this design; it did not validate the new
classifier. The audit's sampling procedure and sanitized fixtures are not yet
included in this project. Treat those counts as historical context, not product
benchmarks or representative estimates of other developers' workflows.

The practical constraints are:

- Permission mode records policy, not whether a particular diff was displayed.
- Edit/Write calls identify paths. They do not establish ownership of the current
  file contents, and the audit found no explicit line-number fields.
- Checkpoints capture state before turns and have finite retention. They are not
  a complete per-edit history.
- Shell changes are outside checkpoint tracking. External changes and subagent
  activity introduce additional coverage gaps.
- Git author identity and commit time do not establish who typed the code or
  when it was written.

Claude's documented checkpoint and permission behavior supports these limits.
See [checkpointing](https://code.claude.com/docs/en/checkpointing) and
[permissions](https://code.claude.com/docs/en/permissions). Transcript formats are
an observed integration surface, not a schema this project controls; recheck
behavior against fixtures when the adapter changes.

Moving to files reduces implementation complexity. It does not remove uncertainty.
The product must make that uncertainty inspectable.

---

## 1. Product thesis

### The user and the job

Start with an individual developer using Claude Code on local Git repositories.
After shipping agent-assisted changes, they want to decide where to invest their
own attention and discover whether their mental model of that code is accurate.

The core workflow is:

1. Scan a checkout.
2. Inspect an explainable queue of files worth reviewing.
3. Open the recorded evidence and committed source.
4. Answer questions about a specific target, recording confidence first.
5. Inspect explanations, challenge bad questions, and choose the next review.

A useful outcome is: **"These three files deserve your attention today, and here
is what caused them to appear."** The tool should help the developer decide; it
should not assert that a file is safe, unsafe, understood, or neglected.

### The governing rule

**Report what the evidence establishes. Label inference. Name missing coverage.**

Keep observed facts, coverage limitations, user assertions, and quiz performance
separate. Positive evidence survives incomplete history. Missing evidence never
becomes proof of human authorship or proof that a developer did not read code.

### Example of a supportable report

> 31 of 94 eligible files have successful agent edits recorded against their paths
> in this checkout. Of those, 18 have no commit by your confirmed identity outside
> the inferred session windows. Seven changed in the last two weeks. None has a
> current passing quiz sample recorded in Blindspot.

Every clause names its scope. "No quiz recorded" does not mean the developer has
never tested themselves elsewhere. Session-window results are inferences, not
independent observations of human editing.

### Non-goals for the first release

- Line or symbol authorship attribution, reading detection, or comprehension scores.
- Session replay, CI gates, merge blocking, PR integrations, or team dashboards.
- Hosted accounts, analytics, or a backend outside the local machine.
- Automatic inspection of other agents' private logs. Claude Code is the first adapter.
- Streaks, badges, praise, scolding, or notifications that pressure the user.
- Treemaps, timelines, share cards, and an editor extension before validation.

---

## 2. Evidence model

### Unit and scope

The scan unit is a text file at the checkout's committed `HEAD`. Historical events
are associated with an exact path in that checkout. This is **path activity**, not
proof of the provenance of the current bytes (§5.3).

Each file has four independent components:

| Component | Contents | What it establishes |
|---|---|---|
| Observations | Successful, failed, and unresolved tool calls; Git commits and identities | Activity actually present in the available records |
| Coverage | Parse problems, missing results, path ambiguity, unavailable history | Specific reasons the available records are limited |
| Commit context | Commits inside or outside inferred session windows | A disclosed timing heuristic |
| Review record | User priority/familiarity and revision-bound quiz attempts | User assertions and performance on particular questions |

### File evidence states

Every eligible file has one summary state. The evidence and limitations remain
visible regardless of state.

| Internal state | Display label | Decision |
|---|---|---|
| `agent_observed` | Agent edits recorded | At least one successful edit names this exact path, with no known path-association ambiguity |
| `no_agent_observed` | No agent edits recorded | No successful edits or relevant unresolved signals; at least one commit has a confirmed identity |
| `inherited` | Other identities only | No successful edits or relevant unresolved signals; touching commits exist and all have unconfirmed identities, while an identity set is configured |
| `unknown` | Evidence unresolved | Known ambiguity prevents the above summary, including unavailable identity where it is needed |

`no_agent_observed` is not "yours". `inherited` is a convenience label for recorded
commit identities, not a claim of exclusive authorship. A file with positive
agent evidence stays `agent_observed` when mode data is missing or history is
partial, unless the association to the current path is itself ambiguous.

These names replace `agent_only`, `shared`, and `yours` as provenance states.
There is no `exact` authorship confidence. Individual observed facts can be exact
within their source without establishing complete historical attribution.

### Commit context is a separate inference

For `agent_observed` paths, report one of:

- `outside_commit`: a commit by a confirmed identity falls outside all relevant
  observed session windows.
- `inside_only`: all such commits fall inside those windows.
- `no_confirmed_commits`: no touching commits have a confirmed identity.
- `unavailable`: identity, timing, or association gaps prevent the comparison.

Always show the grace period and the count of commits being compared. None of
these values means "human edited" or "agent edited everything".

### Permission modes

Keep counts of successful edits by **raw recorded mode**, including absent and
unrecognized values. Optionally group them for display:

| Recorded value | Display group |
|---|---|
| `auto`, `acceptEdits`, `dontAsk`, `bypassPermissions` | Automatic approval policies |
| `default` | Default policy |
| `plan` | Plan policy; editing event requires inspection |
| absent or unrecognized | Unrecorded or unsupported policy |

These groups describe recorded policy only. Exceptions and configured rules may
change actual prompting behavior. Never display "unseen", "auto-accepted", or
"reviewed" as a conclusion from mode. A successful edit recorded in `plan` mode
is retained with a diagnostic, rather than discarded as impossible.

### Metrics and denominators

`eligible` means files remaining after the exclusions in §5.3. Report all four
states, including inherited, by default; hiding inherited is an explicit filter.
Counts sum to the eligible total, and rates sum to one when that total is nonzero.
For a zero denominator, show "not available", never 0%.

Every snapshot records the revision, exclusions, identity configuration digest,
classifier version, grace period, filter policy, and measurement mode. Compare
snapshots only when these policies match, or label the change in methodology.

Quiz metrics are separate: files attempted, files with a current passing sample,
targets passed, stale results, and unresolved confidently-wrong answers. None is a
percentage of the codebase understood. A target pass does not verify a whole file.

---

## 3. Data sources and parsing contract

### 3.1 Discovery

Discover main transcripts under
`~/.claude/projects/<encoded-project-path>/<session-uuid>.jsonl`. On Windows,
start with `%USERPROFILE%\.claude\projects\`.

Read `cwd` from transcript metadata. Never reverse the directory encoding to
recover a path. Metadata may occur after leading entries. Missing or nonexistent
checkouts produce orphan diagnostics and can be linked explicitly.

Inventory nested transcript locations during Phase 1. Parse nested/subagent logs
only when the adapter understands their format, checkout association, and result
pairing. Discovered but unsupported sources are coverage diagnostics; do not
silently advertise complete session coverage.

A session may change directories. Resolve each event against its recorded or
most recently known `cwd`; split checkout-specific activity when roots differ.
An event without a resolvable context remains unresolved.

### 3.2 Stream parsing

The adapter reads metadata and structured blocks from `user`, `assistant`, and
`permission-mode` entries. Unknown entry types are skipped with counts. Use a
streaming reader; do not retain the transcript in memory.

Malformed lines produce diagnostics containing source location and error category,
never the raw line, prompt, tool input contents, or assistant prose. Continue
parsing complete later lines. An incomplete final line is deferred until complete.
Do not filter records based on arbitrary substrings inside their message content.

### 3.3 Mode resolution

Scan forward in physical file order, maintaining the nearest preceding mode:

- `permissionMode` on a `user` entry.
- A dedicated `permission-mode` entry with `permissionMode`.

Mode declarations without timestamps still take effect in file order. A later
mode declaration does not retroactively fill an earlier missing mode. Keep raw
unknown values. Mode absence is a mode limitation, not a failed edit or unknown
agent identity.

### 3.4 Tool calls and results

Extract paths from `Edit.file_path`, `Write.file_path`, and
`NotebookEdit.notebook_path`. Pair results by `tool_use_id` within the source
stream; do not match IDs globally across sessions.

| Result | Normalized outcome | Effect |
|---|---|---|
| Successful paired result | `ok` | Recorded agent edit |
| Paired result with `is_error` | `error` | Recorded failed attempt; does not count as a successful edit |
| No result, conflicting results, or unsupported result shape | `unknown` | Unresolved attempted edit; never treated as success or silently discarded |

Multiple tool blocks in one entry are distinct operations. Repeated copies of an
operation are deduplicated by source and tool ID when consistent; conflicting
copies produce a diagnostic. Preserve call and result source references.

After pairing results locally, consistent copies across sources may be coalesced
only when tool ID, timestamp, cwd, tool name, and mutation-input fingerprint match.
Missing timestamps prevent cross-source coalescing. Preserve every source's
call/result references and include every contributing source window in timing
inference. Never use another source to complete a missing result. Contradictory
copied outcomes stay unresolved, and differing policy metadata prevents silent
merging. Report recorded entries separately from coalesced operation observations;
neither is a guaranteed census of unique real-world edits.

### 3.5 Shell and coverage limits

Record that a shell tool ran, its time, and source reference. Do not persist shell
command text or infer mutation targets from redirections or path substrings.
A Bash mention alone does not establish an edit to that file.

When a Git commit touches a path during an observed checkout session window and
no successful direct edit names that path, mark an **unexplained session overlap**.
This can produce `unknown` even with no direct edit event. It does not establish
that Bash caused the change. Human edits can occur in the same window.

A period without transcripts is not proof that transcripts were pruned: the
user may simply have worked without an agent. Report the observed time span and
lack of coverage; do not manufacture missing sessions. If previously inventoried
transcripts disappear, record that known loss and degrade affected comparisons.

Unsupported agents and unobserved shell changes are global limitations. The
classifier cannot detect every file affected by them. An absence category is
explicitly scoped to available supported records.

Checkpoint files are not inputs to classification. Measuring their retention is
optional research, not a dependency of the first prototype.

### 3.6 Git and identity

Read committed objects and touching history; record both author and committer
metadata. Use author timestamps for the disclosed window comparison, but never
interpret either timestamp as edit time. Rewrites and delayed commits limit it.

Start with the configured Git identity, canonicalized through `.mailmap`.
Present same-name aliases and other plausible aliases as candidates; do not confirm
an identity merely because its name or co-author relationship matches. Persist
user-confirmed identities. Recompute classifications when they or `.mailmap` change.

No identity configured means identity-dependent classification is unavailable.
Successful agent edits still count. Other files become `unknown` with an
`identity_unavailable` reason until an identity is established. A configured
identity belonging to a collaborator should be corrected through the identity flow.

### 3.7 What is retained

Retain paths, source references, tool names and outcomes, timestamps, mode values,
Git metadata, derived summaries, user preferences, and generated quiz content.
Do not copy transcript prose, edit strings, whole Write contents, or shell command
text into the database, exports, diagnostics, fixtures, or debug logs.

---

## 4. Architecture

Python 3.11+ is the proposed core. SQLite and FastAPI arrive after the prototype
passes its evidence checks. The UI is a bundled local web application. Select its
framework when building the UI; the evidence layer must not depend on that choice.

```text
blindspot/
  adapters/
    base.py             # normalized records and adapter protocol
    claude_code.py      # Claude-specific paths, modes, and transcript shapes
  scan/
    sessions.py         # discovery and streaming coordination
    repo.py             # Git objects, path history, identities
    classify.py         # evidence states and timing inference
    queue.py            # transparent review ordering
    report.py           # CLI output and doctor diagnostics
  store/                # Phase 3
  review/               # target export, validation, attempts; Phase 2
  server/               # Phase 4
  ui/                   # Phase 4
  cli.py
```

Only the adapter knows Claude-specific schema. New adapters may also require
capability handling and new fixtures; adding a file is not a guarantee that every
agent offers equivalent evidence.

```python
@dataclass(frozen=True)
class Event:
    source_key: str          # identifies an adapter/source stream
    session_id: str
    seq: int                # physical line position, including skipped entries
    block_index: int
    kind: str               # mode_change | file_edit | shell_activity
    tool_use_id: str | None
    ts: datetime | None
    cwd: str | None
    source_ref: str
    result_ref: str | None = None
    path: str | None = None
    mode_raw: str | None = None
    outcome: str = "unknown" # ok | error | unknown
    op: str = "none"         # edit | write | notebook | none
    raw_tool: str | None = None
```

Ordering is established only within a source stream by `(seq, block_index)`.
Timestamps enable heuristic cross-stream comparisons, not a guaranteed causal
ordering. Source generation fingerprints distinguish a replaced transcript from
an earlier file at the same location.

---

## 5. Algorithms and edge cases

### 5.1 Discovery and explicit linking

Resolve each event context to a Git checkout. Show the resolved root to the user,
particularly when the supplied path is nested inside a larger repository.
Orphan sources can be manually linked; links are persistent user data, carry
an explicit/manual label, and survive rescans. Never silently merge clones.

### 5.2 Repository, checkout, and revision identity

- A repository group uses sorted reachable root SHAs plus a normalized remote
  identity. Keep all roots for multi-root histories. Strip URL credentials and
  canonicalize known transport forms conservatively; no remote is an explicit
  value, not SQL `NULL` in a uniqueness key.
- A checkout has a stable ID, canonical absolute path, and repository group.
  `HEAD` is mutable scan metadata, not part of checkout identity.
- A scan revision records `HEAD` and its policy digests. Reads during a scan use
  the captured SHA; if `HEAD` moves, finish that snapshot and mark it superseded.

Remote changes, rewritten roots, moved checkouts, and a new repository occupying an
old path require explicit reconciliation. Never drop or silently reattach user
data. Repository grouping is a convenience, not universal proof of repo identity.

Keep worktrees and clones separate in metrics and user review records. Refuse
shallow history for classification with an explanation. An unborn repository
reports that a first commit is required.

### 5.3 Scope and path association

Enumerate regular text files from captured `HEAD`; fetch displayed and quizzed
bytes from Git objects, never the working tree. Exclude binaries, symlinks,
submodules, and configured generated/vendor patterns. Initial defaults include
`node_modules/`, `vendor/`, `dist/`, `build/`, `*.lock`, `*.min.*`, and
`*.generated.*`. Show exclusions and allow overrides outside the repository.
Empty files are eligible but cannot be quiz targets.

Match transcript activity to exact normalized relative paths in the checkout.
Reject path escapes and retain out-of-checkout activity as diagnostics. Respect
filesystem case semantics without blindly lowercasing paths.

**An event at a path does not prove its changes survived into `HEAD`.** It may
belong to another branch, have been reverted, or remain uncommitted. Display
"historical activity at this path; current-content attribution unavailable".
Keep available branch metadata as context, without treating it as a commit link.

Renames and delete/recreate history are association limitations. Inspect Git path
history to flag known cases; do not automatically transfer events from an old path
as proven edits to the new one. Git rename detection itself is heuristic. Surface
uncertain lineage and keep original observations. Current-content attribution and
full lineage reconciliation are deferred.

Uncommitted source is not displayed or quizzed. Observed activity may include
uncommitted edits; say so separately. The tool never equates activity counts with
a count of current agent-written files.

### 5.4 Classification

For every eligible path, retain all evidence first, then compute:

```text
successful_edits = supported, paired successful edits at the exact checkout path
confirmed_commits = touching HEAD-history commits by confirmed identities
unresolved = known path ambiguity, unresolved edit outcomes at this path,
             unexplained session overlap, or known lost source coverage

if path_association_ambiguous:                   -> unknown
elif successful_edits:                          -> agent_observed
elif unresolved or identity_unavailable:         -> unknown
elif confirmed_commits:                         -> no_agent_observed
elif touching_commits:                          -> inherited
else:                                           -> unknown
```

Positive agent evidence does not disappear because another attempted edit lacks
a result. Preserve the unresolved count alongside the successful count. Missing
mode information does not alter successful edit classification.

A checkout with no associated supported transcripts has **analysis unavailable**
status. It may show Git-only inventory, but does not present provenance rates as a
successful Blindspot analysis. Offer explicit linking or demo data.

### 5.5 Timing inference

An observed session window uses the first and last available timestamps for that
checkout fragment, extended after the last timestamp by a configurable grace.
These are observation bounds, not proof of when an agent session actually ended.
Missing timestamps make the relevant window comparison unavailable; report live
or incomplete sources separately and avoid definitive inside/outside summaries.

Default grace is provisionally 24 hours. Phase 1 compares 0, 2, 24, and 72 hours,
reporting category changes and queue overlap. Wider windows include more delayed
commits and can also swallow genuinely independent human work. Neither direction
is universally more conservative.

For agent-observed paths, compare confirmed commits to windows for sources with
successful edits to that path. Unexplained-overlap detection uses all observed
checkout windows, including shell activity. Missing timestamps, known lost logs,
or unresolved source association make commit context `unavailable`.

Use the same configured grace for overlap detection, and disclose this in the
report. If an untimed or malformed source prevents locating relevant activity,
record that limitation at checkout scope; do not claim that every affected path
has been identified. `no_agent_observed` remains an absence of supported records,
not a guarantee that unknown channels were ruled out.

Do not label an outside commit "independent human edit". Do not equate a commit
outside every known window with missing logs. Both are possible explanations.

### 5.6 Required classification examples

These are implementation fixtures, not claims that controlled history can be
recovered from all real logs.

| Scenario | Expected report |
|---|---|
| Successful Edit with matched result | `agent_observed`; call and result refs |
| Edit fails; no other signals or session-overlapping commits | No successful edit; identity/history determine the absence category |
| Write lacks its result, with no successful edits | `unknown`; unresolved attempted edit |
| Successful Write and missing mode | `agent_observed`; mode unrecorded |
| Successful edit plus another missing result | `agent_observed`; successful and unresolved counts both visible |
| Shell-written file committed during a checkout session, with no direct edit | `unknown`; unexplained session overlap; shell authorship unproven |
| Human-written file committed during a checkout session, with no direct edit | Same observable classification as the preceding case |
| Human changes a file during an agent session that also edits it | `agent_observed`; cannot exclude human contributions |
| Agent work committed after grace | `agent_observed`; `outside_commit` inference, not human authorship |
| Confirmed commit outside sessions, with no agent events or known relevant problems | `no_agent_observed`; supported-record scope stated |
| Successful edit on another branch or later reverted | Historical path activity only; survival into HEAD unproven |
| Known rename or delete/recreate association | `unknown`; retain observed events with lineage limitation |
| No identity configured | Agent observations remain; identity-dependent paths `unknown` |
| No supported transcripts | Analysis unavailable; no provenance headline |
| Previously inventoried source disappears | Known coverage loss; retain diagnostic and degrade affected comparisons |

Controlled experiments include ground truth from the operator, but output remains
limited to what the tool can observe. Identical observations must receive identical
reports even when the hidden ground truth differs.

### 5.7 Review queue

Call this **review priority**, not operational risk. Churn is touching commits in
HEAD history over the last 90 days. It measures activity, not severity or failure
probability. Recompute the moving boundary on each scan.

Default candidates are `agent_observed` and `unknown`, plus any file explicitly
prioritized by the user or carrying unresolved confidently-wrong answers. Other
files remain accessible and can be added. Sort candidates by:

1. Explicit user priority, highest first.
2. Presence of unresolved confidently-wrong answers.
3. No current passing quiz sample before a current passing sample.
4. 90-day churn, descending.
5. Relative path as a deterministic tie-breaker.

Passing questions lowers priority within this ordering. It never sets risk to
zero, removes a large file as fully understood, or changes provenance. Show the
reason for each candidate and an expandable view of passing samples. A user
familiarity mark is a separate assertion and does not count as quiz evidence.

A zero-candidate queue says why it is empty and offers all eligible files. Missing
analysis is a different state from having no current candidates.

---

## 6. Storage direction

SQLite at `~/.blindspot/db.sqlite`, WAL mode and foreign keys enabled. Phase 1 uses
only lightweight local identity/link configuration and report artifacts. Adopt
this storage model in Phase 3 after the evidence contract is validated.

### Three zones

| Zone | Proposed records | Rescan behavior |
|---|---|---|
| Stable identities and configuration | Repository groups, checkouts, confirmed identities, manual source links | Preserve; reconcile explicitly |
| Derived scan data | Source cursors, sessions, events, Git observations, file summaries, diagnostics | Replace transactionally for the affected checkout/source |
| Persistent user and review data | Priority/familiarity marks, quiz sets, attempts, answers, pass records, policy-bound snapshots | Preserve; append or explicitly revoke |

Persistent records reference stable checkout IDs and paths, never disposable scan
file IDs. Manual source links reference stable source keys rather than derived
session rows. This avoids accidental cascades when rebuilding the scan zone.

### Minimum record contracts

- `source`: adapter, stable source key, source generation, transcript path,
  size, nanosecond mtime, processed byte offset, physical line cursor, content
  fingerprints, parser version, discovery status, and checkout association.
- `edit_event`: source key/generation, session ID, sequence, block index, tool ID,
  timestamp, checkout/path, operation, outcome, raw mode, call/result references.
- `file_summary`: scan ID, path, content hash, evidence state, commit context,
  edit outcome counts, raw mode counts, touching commit counts, churn, limitations.
- `file_preference`: checkout/path, explicit priority, familiarity assertion,
  timestamps. Neither field overrides evidence.
- `quiz_set`: stable ID, checkout/path, source SHA, whole-file hash, target key,
  target span/hash, context manifest, generator, content fingerprint, status,
  validation version, and rejection reason/time.
- `quiz_question`: set ID, ordinal, prompt, four options, correct index,
  explanation, and source rationale. Immutable after validation.
- `quiz_attempt`: application-issued ID and ordinal, set ID, start/completion time,
  whether eligible for a first-attempt pass, pass result, and reveal time.
- `quiz_answer`: attempt/question IDs, chosen index, confidence, submission time,
  server-computed correctness. Unique per attempt/question; never overwritten.
- `pass_record`: checkout/path, set and attempt IDs, target scope, source SHA and
  hashes, pass time, revoked time/cause, and causing set ID if applicable.
- `coverage_snapshot`: checkout, source SHA, time, evidence and quiz counts,
  denominator/exclusion/identity policy, classifier version, grace, measurement mode.

Use constraints for enum values, ordinal uniqueness, index range, and foreign
keys. Repository grouping needs a non-null canonical key: SQLite treats nulls as
distinct in a UNIQUE constraint, so `UNIQUE(root_commit, nullable_remote)` would
not deduplicate local repositories reliably.
[SQLite constraint documentation](https://www.sqlite.org/lang_createtable.html)

This section defines required fields and lifecycles, not a frozen migration.
Confirm indexes and exact SQL against the prototype's access patterns.

### Incrementality and invalidation

Cache validity includes the source inventory, metadata and generation fingerprints,
captured HEAD, repository association, identity and mailmap digests, exclusion
config, manual links, parser/classifier versions, grace, and churn time boundary.
Do not reread an entire transcript merely to discover its last sequence number.

Resume appends from the last complete byte offset, retaining unresolved operations
so later results can complete them. A partial final line remains before the cursor.
Size reduction or replacement fingerprints trigger reparse. Metadata alone cannot
prove unchanged bytes; an explicit full rescan verifies contents and can discover
same-size replacements. Document that limitation rather than promise perfect
incrementality. A disappeared source becomes a coverage-loss diagnostic.

Stage recomputed data and publish it transactionally. A forced rescan must preserve
identities, manual links, user preferences, quiz history, pass records, and stored
snapshots. Recompute effective quiz status and queue ordering after relevant changes.

---

## 7. CLI and first-run behavior

### Phase 1 commands

```text
blindspot scan [PATH]          # defaults to cwd; print evidence inventory and exit
blindspot doctor [PATH]        # quality, limitations, window sensitivity, queue
blindspot brief <FILE>         # observed facts and inference for one path
blindspot identity [PATH]      # inspect and confirm identities
blindspot link <SOURCE> <PATH> # persist an explicit source-to-checkout link
```

### Phase 2 commands (implemented)

```text
blindspot target export <FILE> # explicit revision-bound source/context export
blindspot quiz import <JSON>   # stage and validate a generated set
blindspot quiz review <SET_ID> # open-book loop; resumable first attempt
blindspot quiz start <SET_ID>  # issue/resume an attempt; --practice for later tries
blindspot quiz show <ATTEMPT>  # source/questions without keys
blindspot quiz answer <ATTEMPT> <QUESTION> --choice 1 --confidence solid
blindspot quiz complete <ATTEMPT> # reveal results after every answer is recorded
blindspot quiz results <ATTEMPT>  # completed results, including stale history
blindspot quiz reject <SET_ID> --reason "..."
blindspot quiz feedback <ATTEMPT> --purpose understanding-review --useful yes
blindspot quiz status [PATH]   # effective target samples; evidence unchanged
```

### Commands added later

```text
blindspot serve [--port 7777]
blindspot demo                 # isolated synthetic data
blindspot export [--json] [--paths]
blindspot                      # after MVP: scan selected known checkouts and serve
```

Proposed distribution: a Python wheel, usable through `uvx` or `pipx`. Package
name availability and install commands must be verified before publication.
Bundle UI assets and fonts; normal analysis does not fetch runtime assets.

### Doctor output

Report per checkout:

- Captured Git root, HEAD, eligible/excluded counts, and identity status.
- Evidence-state counts with explicit denominator.
- Successful, failed, unresolved, unsupported, and deduplicated operation counts.
- Mode distribution, including absent/unrecognized values.
- Parse diagnostics, unknown record types, unsupported nested sources, orphans,
  missing-source diagnostics, and observed transcript time span.
- Commit-context counts and sensitivity at 0, 2, 24, and 72 hours.
- Proposed review queue with reasons, plus overlap with a churn-only top ten.
- Adapter versions, source generations, and scan policy/version identifiers.

Example, with synthetic values:

```text
checkout: acme-api
revision: 4f91c2a
94 eligible files; 11 excluded

31 agent edits recorded
38 no agent edits recorded
12 evidence unresolved
13 other identities only

18 of the 31 have no confirmed commit outside observed windows (24h grace).
This is timing inference, not proof of exclusive authorship.
0 files have a current passing quiz sample.

Review next:
  src/payments.py   6 recent commits; agent edits recorded; no quiz sample
  src/auth.py       prioritized by you; evidence unresolved

Scope: committed source, historical path activity, available Claude Code records.
Shell mutations and unsupported agent history may be absent.
```

### Degraded states

No transcripts means analysis unavailable, not 0% agent involvement. Missing Git
identity leaves identity-based classification unresolved. Orphans require linking.
An unborn repository needs a first commit. A shallow repository needs full history.
A supplied path outside a repository exits with a clear diagnostic; CLI failures
use nonzero exit codes suitable for scripts. High unknown counts carry explanations,
not moral judgments. Demo data must never appear as a real checkout's history.

---

## 8. Local server contract

Add the server in Phase 4. Bind to `127.0.0.1`. Validate Host on all requests,
including source-reading GETs. Allow only `127.0.0.1:<configured-port>` and
`localhost:<configured-port>`; reject other hosts. Require exact same-origin
Origin on mutations, rejecting `null` and missing origins. A missing Origin is
accepted for read-only local navigation. No wildcard CORS. All mutations use POST.
CLI import uses the shared application service directly, not an unauthenticated
browser endpoint.

```text
GET  /api/checkouts
GET  /api/checkouts/{id}
GET  /api/checkouts/{id}/queue
GET  /api/checkouts/{id}/files
GET  /api/files/{id}
GET  /api/files/{id}/evidence
POST /api/files/{id}/preference
POST /api/quiz/start
POST /api/quiz/answer
POST /api/quiz/complete
POST /api/quiz/reject
```

Derived file IDs are local to the current scan. Mutations resolve them to stable
checkout/path/revision keys and reject stale scan references. Source reads use Git
objects from that revision; never accept arbitrary filesystem paths from the client.

The answer API accepts attempt ID, question ID, chosen index, and confidence.
The server owns correctness, attempt eligibility, revision checks, and pass status.
Never include correct indices, explanations, or answer-key rationale in question
responses before the attempt is completed. Submitted first answers are immutable;
repeated requests are idempotent, while conflicting replacements are rejected.
Answer responses acknowledge receipt only; correctness is withheld until completion.

Source content is displayed as escaped text. Generated quiz content cannot execute
HTML or scripts. Host/Origin behavior and answer-key exposure require meaningful
integration checks before release.

---

## 9. Minimum UI

Four views only for the first usable release:

1. **Checkouts:** revision, counts, scope, identity, and analysis availability.
2. **Review queue:** path, evidence state, timing inference, churn, quiz sample
   status, priority, and an explanation of ordering.
3. **File detail:** committed content, source references, limitations, review
   targets, priority, and optional familiarity assertion.
4. **Review:** target and permitted context, confidence choices, questions,
   results, explanations, and a question-dispute action.

Hide provenance labels, commit context, and queue reasons during answering. Explain
that quiz results are scored against a generated key. Do not describe state hiding
as a fully blind experiment: the developer may already know the file's history.

Dark first is acceptable. Retain the restrained visual direction:

```text
agent_observed     #E8703A
unknown            #8A6A55
no_agent_observed  #38505A
inherited          #2A2F36

ground #0C0E11   panel #0F1215   inset #0A0C0E   control #1C2127
border #242A31   text #E4E8EC    secondary #959DA6   accent #6FA8D6
```

Use text labels and symbols alongside color, and check actual contrast during UI
implementation. Provenance color and quiz badges are separate; a pass badge never
recolors an entire file as understood. State names are categorical, not a scale of
moral quality or understanding.

IBM Plex Mono for measurements, IBM Plex Sans for prose, both bundled if selected.
Tone is factual and calm. No mascot, congratulation, scolding, or invented certainty.
Each number can explain its source and denominator.

Map, Timeline, Insights, and share cards are deferred until user observations show
what they would help people decide.

---

## 10. Quiz contract

### What a quiz establishes

A quiz records answers and confidence about a specific source target at a specific
revision. A pass means first-attempt agreement with the stored key on that sample.
It is not a safety certificate, complete comprehension test, or file ownership.

### Targets and context

Start with small whole files and explicit ranges selected for larger files. As a
provisional bound, whole-file targets must be at most 300 lines and 16 KiB. Targets
under 10 lines are skipped. These bounds are tunable after the review experiment.

A target records its key, line span, target hash, whole-file hash, source SHA, and
any provided context. Even a whole-file set samples behavior through its questions.
For larger files, passing one function is always a **target sample pass**. Display
the target names/counts; do not invent a percentage of semantic understanding.

Question generation needs enough context for caller assumptions and error paths.
Include explicitly selected declarations or dependencies when required; record
those revision-bound hashes in a context manifest and disclose what is exported.
Do not silently send the whole repository. If required context is unavailable,
reject or narrow the question. Tree-sitter selection and bundled grammars are
later improvements, not dependencies of the first quiz experiment.

### Import before integrations

Phase 2 exports a revision-bound target manifest and source explicitly. The user
can generate questions through their chosen model session or author them manually.
Import JSON through `blindspot quiz import`; use the same validator later for all
generation integrations. No plugin writes directly to SQLite.

In the current pilot, the assistant authors source-grounded question JSON outside
the application and imports it. "Manually authored" here means no application
generation integration; it does not mean independently human-certified keys.
Blindspot currently makes no model calls. Generation should receive the target
and required context, return the same import contract, and pass the existing
validator before any set is served.

Import stages a set as `pending` in memory. Validate target/revision/context binding, 3–5
questions, exactly four distinct options per question, answer indices, explanations,
and source rationale. Promote atomically to `validated` or retain it as `rejected`
with a reason. Shape validation is not proof that the answer key is correct.

The next generation step should work on demand without an always-running Claude
Code session. Explore a one-shot model/API request using explicitly selected
source/context and the existing import validator. Provider choice and credentials
are not yet decided; no generation integration exists today. A Claude Code
command remains an optional later authoring path. Difficulty tuning follows
independent generation, per the user's priority. Code sent to a remote model
leaves the machine for that provider.

### Revision and attempt lifecycle

Serve only validated sets whose file and context hashes match the current captured
HEAD content and whose source revision remains reachable. Validate again before
accepting answers and recording a pass. A changed file/context makes the old sample
stale. An unreachable source revision makes it orphaned. Identical bytes at a later
revision may retain a pass if its source revision remains reachable.

A set is immutable after validation. The shared grading service creates an attempt
and owns its ordinal; the terminal and web interfaces use the same rules. The
first attempt is resumable, and its submitted answers cannot change.
Practice attempts can show explanations but cannot create a first-attempt pass.
Complete an attempt before revealing any keys, so one explanation cannot teach a
later question within that same scored attempt. An incomplete attempt is not a pass.

Pass when every question in the eligible first attempt is correct. Confidence
never gates passing. A pass revoked by valid later evidence requires a new set;
replaying an old set cannot restore it. A revocation caused by a subsequently
rejected key is removed when effective status is recomputed. Deduplicate identical
imported content, including copies with new IDs, using a fingerprint bound to
source/context hashes and normalized question content.
This prevents trivial replay under a new UUID, not intentional answer memorization.

### Effective review status

At target scope, show unattempted, attempted, sample passed, stale, or revoked.
At file scope, show counts and target names, such as "1 current passing sample;
2 targets attempted". Passing never changes the file evidence state.

A confidently-wrong answer means `solid` confidence plus an incorrect answer
against a valid generated key. Show current and historical counts separately.
A fresh passing set for the same target and source/context binding can resolve
that target's flag. A pass on an unrelated function cannot clear it. Changed code
makes the old result historical/stale; it does not resolve it through a new result
on unrelated content. A new confidently-wrong result revokes current passes for
that target and binding, recording the causing set.

Use literal labels in the confidence table:

| Confidence | Correct against key | Incorrect against key |
|---|---|---|
| solid | Confident and correct | Confidently wrong |
| shaky / guessed | Uncertain and correct | Uncertain and wrong |

"Uncertain and correct" does not prove luck, and confidence alone does not prove
knowledge. These are observations against the key, not psychological diagnoses.

### Question quality and disputes

Test consequences and reasoning: removing a guard, changing a dependency,
following an error path, or violating a caller assumption. Avoid syntax trivia
and questions answered by copying a single line. Permit committed source/context
while answering; label the exercise as open-book and keep conditions consistent
when comparing results.

Offer "this question is wrong". Reject the set, preserve attempt history, exclude
its answers from effective calibration, and revoke passes it created. Recompute
flags and revocations caused by that set so a disputed key cannot continue to
penalize the user. Rejected sets are never served again; corrections create a new
validated set with a documented relationship to the old one.

Record experiment feedback separately from answer correctness. A completed
attempt can be annotated as a workflow test or an understanding review, with
usefulness, prior familiarity, active time, and notes. Corrections append a new
annotation; they do not rewrite answers or grades. Unclassified attempts remain
unclassified until the user supplies a purpose. Missing usefulness remains
unreported. Report these groups separately so deliberately varied test answers
are not presented as actual knowledge gaps.

---

## 11. Privacy and local behavior

- Analysis is local. No telemetry or network calls during scanning or browsing.
- Importing a quiz is local. Generating with a model can send the selected code
  and context to that provider; disclose the payload at the point of use.
- Store generated question text and answers deliberately. Never store transcript
  prose or mutation payloads in diagnostics or database records.
- Application-managed state lives under `~/.blindspot/`. An explicit state-directory
  override supports tests. Explicit exports can write to a user-selected destination.
- Scanning and serving never modify the scanned repository or `~/.claude/`.
  Target export is a separate explicit command; generation integrations must not
  silently create repository files, configuration, or CI workflows.
- Default summary exports omit file paths, checkout paths, identities, remotes,
  source references, and quiz/code content. `--paths` opts into file-path output;
  code/target export is a separate operation.
- Normalize remote identities without retaining credentials. Keep code-rendering
  and API path handling within the scan's captured Git object scope.

---

## 12. Delivery phases and decision gates

Historical logs-first delivery plan. Follow the approved roadmap linked at the
top for new work; the completed reports retain their original phase numbering.

### Phase 0 — Project boundary and evidence contract

This revision supplies the evidence contract. Blindspot's dedicated Git repository
has now been initialized; the original directory resolved to the parent Projects
repository. Keep commits scoped to this checkout.

Create the Python package scaffold, a concise README linking this document, and
sanitized fixtures for §5.6. Pin the classifier semantics in those examples before
optimizing. Avoid scaffolding the server, UI, or extension yet.

**Done when:** project root and commit scope are clear, the package can run, and
fixture expectations distinguish observations from inference.

### Phase 1 — CLI evidence prototype

Build the Claude adapter, Git reader, explicit identity/link configuration,
classification, timing comparison, churn, and `scan`, `brief`, and `doctor`.
Use streaming parsing and terminal output. No dashboard or full SQLite schema.

**Current status:** implemented, including copied-history handling, read-only
queries, and temporary mappings for moved checkouts. Evidence has been checked on
Saphire, Portfolio, and Collatz, plus a controlled real Claude Code pilot. See
`reports/phase1-validation.md` for distributions, audits, and remaining research
questions. Phase 2's implementation is ready for the terminal review experiment;
cold-cache performance and ranking usefulness remain unproven.

**Done when:**

- `blindspot doctor /path/to/repo` runs on three real repositories with different
  histories or workflows, including one known to contain shell edits.
- Fifteen files are manually audited across positive, absence, unresolved, and
  identity cases. Every reported fact and timing inference traces to its input.
- Controlled experiments cover manual, agent, mixed, delayed-commit, missing-result,
  rename, and branch/revert scenarios. Ambiguous observations stay ambiguous.
- Repeat scans produce deterministic output at a fixed revision/time/policy.
- Reports include per-repo distributions and window sensitivity. A pooled summary
  cannot hide a repository with poor coverage.

Record cold timing and memory on a representative corpus. The previous target of
50 sessions / 200 MB in 30 seconds is an aspiration to measure, not an assumed fact.

**Hard gate:** fix unsupported claims, incorrect extraction, lost operations, or
misleading unavailable states before continuing. If supported records cannot
produce useful candidates, reconsider the product framing.

**Diagnostics, not automatic cancellation:** a state above 85%, unknown share
above 50%, or large changes across grace periods. Report each per repo. A dominant
state can still support a valuable review workflow; it cannot justify strong
provenance claims. Do not rescue a failed evidence model by renaming uncertainty.

### Phase 2 — Small review-loop experiment

Implement revision-bound target export, JSON import/validation, and a minimal
terminal review loop. Lightweight review records can be stored under the app
state directory before the full database. The later migration must preserve them.
Use explicit target selection and manual/model-generated imported sets.

**Current status:** implemented under `blindspot/review/`, with atomic,
POSIX-locked `reviews.json` stored separately from scan inventories. Lifecycle
tests and a real-checkout scripted smoke run pass. Reports expose review samples
separately from evidence; queue ordering remains the Phase 1 churn baseline until
Phase 3. Two user-run Collatz attempts are recorded: one workflow test (1/5),
and one understanding review (2/3). The user has prioritized independent quiz
generation ahead of difficulty tuning. An on-demand generation path is proposed,
not implemented; one further cache-test-design set is ready. See
`reports/phase2-validation.md` and `reports/phase2-pilot.md`. The human experiment
below is still required; scripted answers establish workflow behavior only.

Review roughly 10–15 targets across different evidence states. Record question
disputes, useful corrections to the developer's mental model, time spent, and
whether the suggested next review was worth doing. Compare the top ten suggested
files with churn-only ordering; record preference rather than invent a precise
quality score.

**Done when:** target/context staleness, immutable first answers, withheld keys,
replay limits, and disputed-key recomputation work; results expose useful issues
and the developer voluntarily wants another review session. If questions mostly
test trivia or contain faulty keys, improve them before building integrations.

### Phase 3 — Storage and incrementality

Implement the three zones, migrate early review records, transactional scan
publication, durable links/preferences, resumable parsing, and policy-bound
snapshots. Add queue ordering based on effective review data.

**Done when:** a forced rescan preserves all persistent records; partial appends,
late results, replacement and removal of sources behave as documented; an unchanged
200 MB corpus has a measured rescan target under two seconds on stated hardware.
Correctness takes precedence over the timing target.

### Phase 4 — Minimum usable web release

Add FastAPI and the four views in §9. Use the shared validator and grading service.
Bundle assets. Ship useful degraded states, isolated demo data, and a README that
quotes real doctor results with their scope and methodology.

**Done when:** installation to a rendered queue has a measured target under 60
seconds, and a user can complete scan → evidence → review → results without
repository modifications. Local-server checks and quiz lifecycle checks pass.

This is the first public MVP. Plugin generation, BYOK, tree-sitter, maps, and the
extension are not release requirements.

### Phase 5 — Improvements based on use

Choose additions from observed friction: generation integration, target selection,
more adapters, or a visualization that improves a decision. Improve portability
and packaging based on actual installs. Do not build every deferred view by default.

### Personal calibration experiment

After question quality stabilizes, review 30–40 targets across evidence categories.
Predefine question selection, open-book conditions, scoring, context, and comparison
before collecting. Include the churn-only baseline and report missing coverage,
question disputes, target size, language, and prior familiarity.

A possible exploratory criterion is a 20-percentage-point difference in first
attempt accuracy between paths with and without recorded agent edits. These are
observed categories, not agent-versus-human ground truth; there is no required
outcome. State labels are hidden during questions, but prior knowledge remains.
N=1 and selected targets cannot establish a general causal relationship. Publish
negative or inconclusive results with the same limitations as positive results.

### Immediate implementation checklist

1. Design independent, on-demand quiz generation without an always-running
   Claude Code session; decide provider/credentials and reuse the import contract.
2. Implement generation with explicit target/context export and validation,
   preserving existing sets, attempts, disputes, and feedback.
3. Then tune difficulty and pilot the flow on suitable targets. Identify guided
   conditions explicitly and collect usefulness before expanding to roughly 10–15.
4. Audit ambiguous keys and compare suggested reviews with the churn baseline.
5. Once usefulness is demonstrated, implement Phase 3 storage and incrementality
   while preserving all answers, sets, disputes, and feedback history.
6. Build the Phase 4 web workflow on the shared validator/grading service.

---

## 13. Limitations and open decisions

### Known limitations

1. Historical path activity does not establish the origin of current bytes.
2. No supported edit record does not establish human authorship.
3. Commit identity is not keystroke identity, and commit time is not edit time.
4. Missing transcripts cannot generally be distinguished from agent-free work.
5. Shell, unsupported agents, and unsupported nested sources create partial coverage.
6. Mode records policy, not actual prompts, visibility, or reading.
7. Renames, recreation, branch switches, reverts, and history rewrites complicate
   path association; uncertain cases remain explicit.
8. Current source comes from HEAD; uncommitted content is not reviewed.
9. File-level activity cannot indicate which functions were agent-written.
10. Generated keys may be wrong. Passing sampled questions does not establish
    complete understanding, operational safety, or freedom from bugs.
11. The queue is a heuristic about where to spend attention, not a defect predictor.
12. The first adapter is Claude Code only; transcript formats can drift.

### Open decisions with owners in the roadmap

- Grace period and useful timing categories: decide from Phase 1 sensitivity results.
- Whether timing inference helps choose reviews at all: compare during Phase 2.
- Target bounds, context size, and question generation prompts: Phase 2 findings.
- UI framework and packaging: Phase 4 implementation and installation measurements.
- Tree-sitter grammars, additional adapters, BYOK, and plugin generation: Phase 5 demand.
- Shell logs and hook formats: research separately; hook exit codes describe hooks,
  and command mentions alone do not prove file mutation.
- Map, Timeline, Insights, light theme, and share cards: defer until useful to a
  demonstrated workflow. No historical chart reconstructs observations never made.

---

## 14. Editor observation experiment

**Observer 0.3 now spans collector, observation storage and a visibility MVP
prototype in the approved roadmap.** The local extension and shared overview
collect prospective changes and reported editor ranges. Follow the
[implemented contract and desktop gate](observer-03.md); the remainder
of this section records the broader experiment and future requirements. The experiment cannot make retrospective logs complete or prove
that a person read or understood code.

### What it could observe

The initial target is VS Code. Test compatibility and distribution separately
before promising support for its forks.

Relevant APIs include:

```text
workspace.onDidChangeTextDocument
workspace.createFileSystemWatcher
window.visibleTextEditors
window.onDidChangeVisibleTextEditors
window.tabGroups
window.onDidChangeActiveTextEditor
window.onDidChangeWindowState
window.onDidChangeTextEditorVisibleRanges
TextEditor.visibleRanges
```

Document changes can provide ranges. Filesystem watchers provide change
notifications, not authorship or a complete sequence of intermediate contents.
Visible ranges describe editor visibility, not eye movement or comprehension.
See the [VS Code API reference](https://code.visualstudio.com/api/references/vscode-api).
Do not confuse workspace edit-operation events with filesystem watcher guarantees.

### Verification spike before commitment

Experiment with closed/open files, shell edits, atomic replacements, large writes,
renames, ignored paths, split editors, background windows, extension restarts,
remote workspaces, and concurrent agents. Measure dropped/coalesced notifications,
content recovery, typing latency, and memory cost.

A snapshot/diff store can recover differences between captured contents, but not
intermediate changes that happened between snapshots. Recording gaps must be
first-class evidence, including time spent outside the observed editor.

### Conditional observation labels

| Label | Required evidence |
|---|---|
| `not_observed_visible` | Changed range did not intersect recorded focused-editor ranges during a stated interval with adequate recording coverage |
| `briefly_visible` | Recorded intersection shorter than a disclosed dwell threshold |
| `visible_with_dwell` | Recorded intersection meeting the threshold |
| `visibility_unknown` | Recording gaps, ambiguous range tracking, or unsupported editor context |

Do not use `read`, `never_seen`, or `human_authored` based on dwell, selections, or
change events. Horizontal clipping, folded content, other apps, and unrecorded
editor sessions limit visibility claims. Track the version of content observed;
line numbers alone do not remain stable as code changes.

### Attribution and storage

The extension observes byte changes. Agent attribution requires positive tool
records plus sufficiently specific path/content/time correlation; simultaneous
edits can remain ambiguous. Human paste and agent insertion can look identical.
File timestamps alone do not establish causality.

Keep the Python parser and local app. Add observation tables and content snapshots
only after the spike establishes their cost and useful claims. Store measurement
mode and coverage per observation; never average logs-only and editor-assisted
metrics into an unlabeled number. Existing quiz and user records survive.

Use a defined ingestion service or shared schema protocol rather than letting two
independent processes mutate arbitrary SQLite tables. Concurrent writers, schema
versioning, and crash recovery are design work to settle during the spike.

### Privacy and adoption

Observation is explicit opt-in per workspace, with a visible recording indicator,
a pause control, retention settings, and plain explanations of what is retained.
Keep collection lightweight. The MVP will offer both an extension interface and
an interactive localhost site backed by the same observations and summaries.

Historical path evidence can seed a useful first run. Prospective observations
accumulate only while recording is active. The research question is whether that
extra evidence improves review choices enough to justify continuous recording and
its performance/privacy costs. There is no assumed answer or promised final form.
