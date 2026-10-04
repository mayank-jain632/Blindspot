# Phase 1 prototype validation

Initial validation on October 2, 2026. This records implementation checks and
local corpus observations, not a claim that provenance or product usefulness has
been established. Full reports and paths to private logs remain in ignored
`reports/local/`.

## Implemented

The Python package provides `scan`, `doctor`, `brief`, `identity`, and `link`.
It reads captured HEAD objects and path history, pairs tool calls/results within
source streams, keeps mode metadata separate, classifies recorded evidence,
reports timing sensitivity, and produces an initial churn-based review queue.
Application state is lightweight JSON with explicit identities/links and inventories
that preserve known source-loss diagnostics. Read-only queries can use existing
state without saving it; temporary source-root mappings never save links. Counts
separate recorded entries from consistent copied operations, preserving all source
references. There is no database, server, or quiz.

## Real corpus

Discovery found 18 main transcripts, four nested transcripts, and 227.6 MB of
main transcript data. Several recorded checkouts no longer exist; directory names
were not decoded or silently linked to other repositories. Nested sources remain
unsupported and are disclosed where their parent source can be associated.

At a fixed report time of `2026-10-02T12:00:00-05:00` and 24-hour grace:

| Checkout | Eligible files | Supported sources | Agent observed | No agent observed | Unknown | Inherited |
|---|---:|---:|---:|---:|---:|---:|
| saphire | 555 | 1 | 21 | 0 | 1 | 533 |
| mayank-portfolio | 20 | 1 | 12 | 8 | 0 | 0 |
| extension_hub | 95 | 0 | Unavailable | Unavailable | Unavailable | Unavailable |

The saphire source also has three unsupported nested sources. Its successful
edits cannot establish complete activity coverage. Most touching Git commits use
an identity different from the initially configured one; the inherited share is
an identity observation, not a measure of who understands the code.

Extension Hub validates the degraded path: the tool shows Git inventory and
explicitly withholds provenance counts/rates when no supported source is associated.
It does not count as a third repository with validated agent evidence.

The main-source parse took 0.516 seconds in the initial measured run on this Mac
with Python 3.14.4. Reusing those parsed sources, Git/classification took roughly
0.45–0.54 seconds per checkout. These are single-run observations with filesystem
caches; they are not an incremental-rescan or cold-install benchmark. Phase 1
still reparses all discovered main sources for each independent CLI invocation.

## Independent checks

The initial 34 tests passed on Python 3.11.14 and Python 3.14.4. The suite now has
48 passing tests in the installed Python 3.11.14 environment, including copied
history, retained references, incomplete/conflicting results, temporary mappings,
and read-only preservation of state and input files. The editable package was
installed in the project's Python 3.11 virtual environment, and its `blindspot`
entry point produced a real Portfolio doctor report. The machine's default
Python 3.14 could run the application/tests but its `ensurepip` failed due to a
local Expat library mismatch, so Python 3.11 was used for the installation check.

Fifteen files across the two supported checkouts were cross-checked using
`scripts/audit_evidence.py`, which does not import the production parser,
classifier, or Git reader. It reads raw structural records and invokes separate
Git commands, checking edit outcomes/counts, mode resolution, confirmed author
counts, outside-window counts, source hashes, and a rename-related unknown.

The sample includes nine positive paths, three absence paths, two inherited paths,
and one lineage-ambiguous path. Call/result line pairs were inspected in the
structural output. This is a spot-check of available records, not independent
ground truth about the developer's historical editing behavior. The private audit
table is `reports/local/15-file-audit.md`.

Controlled tests use disposable repositories and synthetic transcripts to exercise
the additional cases that the available historical sample cannot establish:
missing results, malformed/partial records, manual-versus-shell overlap, delayed
commits, lost sources, rename/recreation, another branch, and missing identities.
Payload privacy is checked with synthetic sentinel strings.

## Real Claude Code sandbox pilot

On October 3, 2026, the user completed the controlled exercise in
`sandbox/phase1-pilot/` using Claude Code version `2.1.282`. At committed HEAD
`ba0021f91c64feb81f99513f354a4ca1243fef0c` and fixed report time
`2026-10-03T06:09:30.724757+00:00`, all three eligible files matched expectations:

| File | Actual state | Evidence checked |
|---|---|---|
| `baseline.py` | `no_agent_observed` | Unchanged pre-Claude baseline, committed before the session. |
| `calculator.py` | `agent_observed` | One successful direct Edit, call/result at physical lines 84/99. |
| `shell_summary.py` | `unknown` | Bash file-write record at line 203; no direct edit event, with `unexplained_session_overlap`. |

The one associated source had complete observed timestamp bounds from
`06:07:57.686Z` to `06:08:31.007Z`. The implementation commit was at `06:09:13Z`,
about 42 seconds after the last observed record. At zero grace, the shell file
leaves the unresolved category; 2/24/72-hour policies agree. This demonstrates
timing sensitivity and the shell-coverage limitation, not proof of authorship.
The direct-edit file has `outside_commit` context because its initial baseline
commit predates the session. Raw `auto` policy was retained without interpreting
it as review or understanding. No parser, discovery, or quality diagnostics
were reported.

The committed invoice functions were checked with inline assertions for totals,
empty inputs, invalid amounts, and formatted output. Private JSON/text reports
are saved as `reports/local/phase1-pilot-doctor.{json,txt}`. The user's initial
timestamp-generation command failed due to an indented newline; the original
CLI fell back to current time on empty `--now`. That empty value is now rejected,
and these reports were reproduced with the explicit timestamp shown above.

This is a real agent session in a deliberately small, new repository. It
supplements the two historical audits; broader repository/workflow coverage
and evidence of queue usefulness remain open. Starter files were created by
Codex, so the absence category must not be described as human authorship.

## Dorm Decor archived-checkout check

On October 3, 2026, the user supplied `projectarchive/dorm-decor` as an existing
repository with heavy historical Claude usage. Git resolves its root to
`ProjectArchive/dorm-decor`; that casing difference does not prevent inventory.
At HEAD `ffc4e95143ccac44ccb274c988cea0b467a34db7` and fixed report time
`2026-10-03T17:14:27.610914+00:00`, Blindspot reports 33 eligible files, one binary
exclusion (`src/app/favicon.ico`), and **zero associated supported sources**.

The available corpus contains 19 main transcripts and four nested transcripts.
Checking their structured cwd/edit-path metadata found no Dorm Decor references.
The earliest observed main-source timestamp is July 20, 2026, while this
checkout's latest committed change is April 23, 2026. The current Claude history
metadata and checked supplementary session metadata also provided no matching
checkout/session references. This does not contradict the user's historical
Claude usage; its tool records are not available in the checked locations.
An incidental text mention in another repository's transcript is not evidence
that the transcript belongs to Dorm Decor, so no manual link was created.

The degraded result is correct: provenance counts/rates and the review queue
are withheld. Separate Git blob reads verified hashes and line counts for all
33 eligible files; five paths were also checked against independent Git author/
committer history queries. The editor page and two renderer files have working
copy changes, and their reports correctly use committed HEAD content. The scan
left the target's working-tree status unchanged. The fixed-time report was
reproduced exactly.

The first fresh-process scan took approximately 0.84 seconds with a peak RSS
of 41,025,536 bytes on this Mac/Python 3.11 environment. It includes discovery/
parsing of the whole available corpus and local report output. Filesystem caches
were not cleared, so this is not a measured cold-cache benchmark.

Private reports are `reports/local/dorm-decor-doctor.{json,txt}` and the separate
inventory/history audit is `reports/local/dorm-decor-audit.md`. Dorm Decor can
validate historical agent extraction only once its original supported transcripts
are located/restored or supplied through `--sessions-dir`. A moved checkout may
then need an explicit source link after confirming the source belongs to it.
This scan does not close the third historical-repository evidence gate.

Follow-up discovery located a stronger candidate: the nine recorded
`cs373_MAIN/cs373-collatz` sessions contain 95 successful direct-edit records and
75 Bash calls at that cwd (another three Bash calls use its `tests` subdirectory).
A current checkout exists at `College/Fall2026/SWE_logs/cs373-collatz`;
all nine distinct successful historical edit paths are eligible at its HEAD,
and its latest commits fall in the recorded September 7–8 session period. The
recorded root has moved, so source association needs explicit reconciliation
before a provenance report can be validated. No links were created in this check.

## Collatz evidence validation and reliability changes

The moved checkout was validated at HEAD
`c16c3b8ec00b2f80aeee09deced911ec1253f4e1`. Nine associated main transcripts use
adapter source version `2.1.263`, with no associated unsupported nested sources.
The CLI can now reproduce the analysis using `--read-only` and a temporary
`--source-root` mapping; no persistent source links were created.

| Eligible files | Agent observed | No agent observed | Unknown | Inherited |
|---:|---:|---:|---:|---:|
| 14 | 9 (64.3%) | 0 | 4 (28.6%) | 1 (7.1%) |

All 14 HEAD hashes, direct-edit outcomes, author/committer history, and timing
inference were independently checked. Positive files include `Collatz.py`,
`CollatzTest.py`, configuration, and project documentation. `Collatz.ctd.txt`
has only the professor's author identity; the configured personal identity is
the university address used by this repo. Acceptance input/output, generated
HTML, and Git-log text remain unresolved due to session/commit overlap without
direct edit records. Successful Bash records confirm documentation generation,
Git-log redirection, and copying an acceptance-output artifact; the production
classifier does not infer those mutation paths from shell text.

Copied history exposed inflated counts. Before the fix, 81 successful in-checkout
records were reported as operations. They now coalesce to 58 successful operation
observations plus one failed attempt, with 23 repeated records disclosed. All
original call/result references are retained. For example, `DESIGN.md` changes
from 46 successful records to 24 coalesced operations, and `CRITERIA.md` from 20
to 19. Fourteen successful records outside the checkout are excluded and
diagnosed. File classifications remain unchanged.

All nine positive files have `inside_only` commit context at 24-hour grace. At
zero grace, only `Makefile` changes to `outside_commit`; 2/24/72-hour policies
agree. Queue/churn-only top-ten overlap is ten. This establishes extraction and
conservative shell handling, not additional ranking value or understanding.

Two fresh CLI processes produced byte-identical JSON at fixed report time
`2026-10-03T18:58:04.437235+00:00`. Checksums and modification times for tracked
files, the Git index, and all nine transcripts remained unchanged. The selected
state directory did not exist before or after scanning. The first measured
fresh process took 0.817 seconds with peak child RSS 41,762,816 bytes. Filesystem
caches were warm; no cold-cache performance claim is made.

Private report artifacts are `reports/local/collatz-doctor.{json,txt}` and
`reports/local/collatz-audit.md`. The new independent audit also checks coalesced
counts and every retained call reference against raw structured records.

## Current milestone and follow-ups

The Phase 1 CLI implementation and three-repository evidence checks are complete
for the supported logs-only scope. The next build milestone is the small Phase 2
terminal review-loop experiment. Remaining research and scope limitations:

- Review identity candidates before interpreting state distributions as personal
  observations. Do not confirm collaborators merely to improve the distribution.
- Decide whether timing inference meaningfully improves choices over churn alone;
  current results only expose it, not establish its usefulness.
- Measure cold parsing, memory, and broader transcript-version coverage. Support
  for nested sources and full path-lineage reconciliation remains deferred.

Use the review-loop experiment to assess ranking usefulness and question quality
before building the dashboard. It does not require claiming complete agent
coverage, cold-cache performance, or exclusive authorship.
