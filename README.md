# Blindspot

A small local tool that shows which files and source regions have recorded
editor display evidence, helping developers choose what to revisit.

**Current goal: a local presentation MVP.** The extension, local receiver,
SQLite storage and React dashboard are implemented. Risk is the landing view;
Map, Timeline, Insights and PNG export use the same local records. See [the short v1 design](DESIGN.md) and
[the simplified roadmap](reports/roadmap-proposal.md).

The latest dashboard pass leads with unseen lines, uses plain-language states,
counts distinct files in the weekly timeline, and keeps measurement details in
one shared explanation. The next step is a short manual demo in VS Code: record
one file, leave another untouched, inspect the dashboard, then check pause/resume
and a visible split pane. See [the agent handoff](context_handoff.md) for current
status and a ready-to-run checklist.

The localhost site is the main demo surface; VS Code supplies observations and
recording controls. Display evidence does not prove reading or understanding.
Quiz generation remains paused.

For the existing 0.3 development build, see [setup instructions](reports/observer-03.md#load-this-build).
Its longer acceptance matrix is historical guidance, not a prerequisite for the
presentation MVP. Python 3.11+, Git and the supplied VS Code F5 launch are enough;
no runtime Python dependencies or model session are required.

The CLI documentation below describes the earlier transcript/evidence and review
workflow. Those commands and records remain available separately from the demo.

## Run the dashboard

Build once (Node 22+), then start the existing receiver (Python 3.11+):

```sh
npm --prefix dashboard ci
npm --prefix dashboard run build
.venv/bin/python -B -m blindspot observer serve \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state \
  --port 7777
```

`scripts/demo.sh` does both steps. The built dashboard (`blindspot/observer/dashboard_dist/`) is
not committed, so after `git pull` or a branch switch you must rebuild or the old UI keeps serving.

Open **http://127.0.0.1:7777**. If an older receiver is running, stop it with
Ctrl+C in its terminal before restarting. The extension reconnects using the
same `connection.json`; its existing F5 launch already points to this state.
Start recording in VS Code to add observations. The dashboard refreshes every
10 seconds and has a manual Refresh button.

The dashboard never writes observed source. State must stay outside the observed
workspace. `/inspector` retains the earlier diagnostic interface, and the VS Code
overview remains available. Fonts, scripts and assets are bundled; runtime
requests stay on localhost. The site has no account or login.

Review serves existing validated questions only. Add
`--review-state-dir /absolute/path/to/existing-review-state` to connect a separate
`reviews.json` store for the **same workspace**. Otherwise it reads review state
in the observer state directory. No matching unanswered quiz means the Review
action is unavailable; quiz generation remains paused. Passing a current eligible
sample reduces dashboard queue priority without changing display percentages.

**Study guide.** File detail includes a guide for the selected file, built only from the
code's structure (Python AST, patterns for other languages) and `git blame`. It lists each
function, class or section with how many of its lines were never on screen, what it calls,
and the commit that last changed it. **Unseen code** shows only units with gaps, largest
first; **Whole file** lists everything in order. Open it from the **Guide** button on a Risk row, or
"Open full guide" in file detail, for a full page with an outline, expandable code, Markdown copy and print. No model is used and the code never
leaves the machine. It describes display evidence, not understanding.

**Optional local explanations.** If [Ollama](https://ollama.com) is running, the full guide page
gets an **Explain** button on each code unit and **Summarize this file**. Install a model once
(for example `ollama pull qwen2.5-coder:7b`; any chat model works) and pick it in the sidebar.
Only the selected unit's code, its unseen line ranges and its last commit message are sent, to
a loopback endpoint only (`--ollama-url` rejects anything off this machine). Answers are cached
in the observer state folder, labelled as generated and unverified, and the guide works
the same without them. To go back to the version before this feature, check out the commit
`f21ab92` (tagged `pre-ollama` where the tag could be pushed).

The [data contract and design adaptations](reports/dashboard-contract.md) explain
what is measured, inferred, and unavailable. Check the implementation with:

```sh
npm --prefix dashboard test
npm --prefix dashboard run test:browser
.venv/bin/python -B -m unittest tests.test_dashboard -v
```

The browser check uses installed Google Chrome and disposable fixture data.
It saves screenshots and a PNG under ignored `reports/local/dashboard-checks/`.

## Run from this checkout

```sh
python3 -m blindspot doctor /path/to/repository
python3 -m blindspot scan /path/to/repository
python3 -m blindspot brief /path/to/repository/src/example.py
```

Evidence commands read Claude Code transcripts from `~/.claude/projects/`. Application
configuration and source inventories go to `~/.blindspot/prototype.json`.
Scanning never changes the inspected repository or Claude's files. Reports read
file contents from captured Git HEAD, including when the working tree is dirty.

Use `--read-only` with `scan`, `doctor`, `brief`, or an identity listing to read
existing configuration without creating/updating application state. It rejects
`link` and identity changes. Python's `-B` also suppresses interpreter bytecode
cache writes:

```sh
python3 -B -m blindspot doctor /path/to/repository --read-only
```

State stays outside the inspected checkout. A dot-prefixed folder is hidden in
some file browsers but is not automatically ignored by Git; creating one would
also be a write. Blindspot does not create a metadata folder in scanned repos.

For an isolated state directory or a fixture corpus:

```sh
python3 -m blindspot doctor /path/to/repository \
  --state-dir /tmp/blindspot-state \
  --sessions-dir /path/to/claude/projects \
  --json \
  --now 2026-10-02T12:00:00-05:00
```

Evidence `--json` includes local paths, Git identities, and evidence references.
Keep these reports private when sharing a checkout. Transcript prose, edit
payloads, and shell commands are not retained. Evidence reports do not include
source code; `target export` explicitly exports selected code, and imported
questions, answer keys, source rationales, and answers are stored in `reviews.json`.

The package also defines a `blindspot` entry point for editable installation:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/blindspot doctor /path/to/repository
```

Installation needs setuptools as a build dependency. Run module commands without
installing when offline. The distribution is named `blindspot-local`; it is not
published to a package index.

## Evidence and configuration

`doctor` shows four file evidence categories, separate commit timing inference,
raw mode counts, unresolved operations, coverage diagnostics, a review queue,
and sensitivity to 0/2/24/72-hour grace periods. Results describe activity at a
path, even if the edit was reverted or came from another branch. A passed tool
result establishes a recorded edit; missing results remain unresolved.

Doctor distinguishes recorded edit entries from operation counts after consistent
copies are coalesced. Cross-source copies must match the tool ID, timestamp, cwd,
tool, and hashed mutation input, with agreeing results and policy metadata. Every
call/result reference remains in the event's `observations`. Result pairing always
happens within each source. Missing results are never filled from another source;
contradictory copied results stay unresolved. Different inputs, missing timestamps,
and differing policy metadata prevent silent merging. Counts are conservative
observations, not a guaranteed census of unique real-world operations.

No supported associated transcripts means **analysis unavailable**, with no
provenance rates. No configured/confirmed Git identity leaves identity-dependent
files unresolved. Renames and delete/recreate histories have ambiguous lineage.
Nested/subagent sources are inventoried but currently unsupported; their results
are not paired with tool calls from unrelated main sources.

The initial review queue orders agent-observed/unresolved paths by 90-day churn,
then path. Reports now show current passing target samples alongside evidence;
review data does not change the earlier CLI queue ordering. The React dashboard
uses its own verification-aware priority policy. Churn is activity, not operational risk.

```sh
python3 -m blindspot identity /path/to/repository
python3 -m blindspot identity /path/to/repository --confirm alias@example.com
python3 -m blindspot identity /path/to/repository --remove wrong@example.com
python3 -m blindspot link /path/to/session.jsonl /path/to/repository
```

The configured identity is accepted initially. Other historical identities are
listed for explicit confirmation; names do not automatically confirm colleagues.
Removing an incorrectly configured identity is persistent until confirmed again.
Explicit links survive rescans and are identified in reports. A manual link maps
paths relative to the transcript's first recorded cwd to the selected checkout;
use it only when that origin is the intended checkout root. General moved-checkout
and nested-origin reconciliation remains future work.

For a moved checkout, `--source-root OLD_PATH` temporarily maps all main
transcripts whose first recorded cwd matches that old root. It accepts only
sources whose other cwd contexts stay within that origin, is repeatable, and
never saves links. No source directory names are decoded into checkout identities.
For the validated Collatz checkout:

```sh
.venv/bin/python -B -m blindspot doctor \
  /Users/mayankjain/College/Fall2026/SWE_logs/cs373-collatz \
  --read-only \
  --state-dir reports/local/collatz-read-only-state \
  --source-root /Users/mayankjain/College/Fall2026/cs373_MAIN/cs373-collatz
```

Temporary mappings are also available to `scan` and `brief`. Default scans still
save inventories and identity configuration; add `--read-only` to suppress those
writes. A read-only run cannot establish a new saved inventory for future
source-loss detection, but it can compare against an existing one.

Exclusions can be extended with `--exclude PATTERN`; `--include PATTERN` overrides
a matching path exclusion. `--no-default-exclusions` replaces built-in patterns.
Binary/non-UTF-8 blobs, symlinks, and submodules remain excluded. Built-in patterns
are listed in the report policy, so a denominator can be checked.

Phase 1 reparses transcripts on every scan. It retains source inventories to
report known source disappearance. It does not silently forget missing sources
on subsequent scans. Rewritten repository identity requires explicit reconciliation
or a separate state directory; no user identity/link records are dropped.

## Terminal review experiment

Start the prepared Collatz exercise with the command in
[the Phase 2 pilot](reports/phase2-pilot.md). The original five-question exercise
has one completed workflow-test attempt; the cycle-length follow-up has one
completed understanding review, and the cache-test-design set remains ready.
Quiz generation is paused while the approved visibility roadmap is implemented.
The pilot also
provides the JSON contract and an authoring prompt.

For another target, export committed source explicitly to a location outside the
inspected checkout, author a set, and import it:

```sh
python3 -B -m blindspot target export /path/to/repository/src/example.py \
  --start 20 --end 80 --name example-function --output /tmp/target.json
python3 -B -m blindspot quiz import /tmp/quiz.json --state-dir /tmp/blindspot-review
python3 -B -m blindspot quiz review SET_ID --state-dir /tmp/blindspot-review
python3 -B -m blindspot quiz status /path/to/repository \
  --state-dir /tmp/blindspot-review --read-only
```

Targets contain at least 10 lines; each exported target/context block is limited
to 300 lines and 16 KiB. `--context FILE` exports a bounded whole context file;
repeat `--context-range FILE START END` to select context spans. No model calls
are made automatically. Import checks shape, citations, and revision bindings;
it cannot prove the generated key is correct.

For this pilot, the assistant authored the question JSON from selected committed
source, then imported it. Blindspot itself does not call an LLM. Further sets can
be authored manually or in a chosen model session using the pilot prompt. An
independent, on-demand model/API generation path remains proposed, with provider
choice still open. Generation is paused. The revised roadmap places it after
collection/storage/visibility validation; difficulty tuning follows generation.

Review is open-book. Submit an option and `solid`, `shaky`, or `guessed` confidence
for each question. Keys and explanations appear after the whole attempt completes.
Enter `q` at the choice prompt or press Ctrl-C to pause; rerunning the same command
resumes the first attempt with submitted answers preserved. `--practice` creates
another attempt after the first completes, but cannot earn a first-attempt pass.

Reject a faulty set with `quiz reject SET_ID --reason "..."`. History remains;
effective passes and confidently-wrong flags are recomputed without that set.
Corrections are new imports, with `supersedes` naming the rejected set.

Record why you took a review and whether it helped using
`quiz feedback ATTEMPT_ID --purpose understanding-review --useful yes`.
Use `workflow-test` for deliberately varied test answers. Optional
`--familiarity`, `--active-minutes`, and `--note` record experiment context.
Omitting usefulness leaves it `unreported`. Feedback preserves answer history and
does not change grades; status/doctor show purpose counts and unclassified attempts.

For scripted clients, use `quiz start`, `quiz show`, `quiz answer`, `quiz complete`,
and `quiz results`. CLI `--choice` and terminal options are **1–4**; JSON
`chosen_index` and `correct_index` are **0–3**. `--read-only` supports status,
show, results, and target export to stdout; it rejects review mutations and
`target export --output`.

Keep using the same `--state-dir` for reviews and reports. Reviews live in
`reviews.json`, separate from the scan inventory in `prototype.json`, so rescans
preserve them. The local store contains keys; withholding in the review interface
is an experiment condition, not protection against inspecting your own files.
Any committed change to the target or a context file makes the binding stale,
including changes outside a selected range. An unreachable source revision is
orphaned. Dirty working-tree edits are not reviewed.

## Validation

```sh
.venv/bin/python -B -m unittest discover -v
node --test extension/test/*.test.js
```

Tests create disposable Git repositories and synthetic transcripts outside the
project. They cover tool pairing, mode order, payload privacy, incomplete logs,
delayed commits, shell/human overlap, identity/mailmap behavior, HEAD-only reads,
renames, recreation, branch changes, loss of sources, deterministic rescans,
copied history with preserved evidence, read-only state/file preservation,
temporary moved-checkout mappings, degraded CLI behavior, revision-bound quizzes,
immutable answers, hidden keys, replay/practice limits, disputes, concurrent review
writes, and review preservation through scans. They do not modify real repositories
or Claude logs.

Collector tests additionally use temporary localhost listeners, real Node-to-Python
ingestion, and a mocked VS Code API. They check source/version/time binding,
focus/pause handling, interval gaps, batch validation and idempotent retry,
heartbeat expiry, automatic receiver restart/token recovery, loopback authentication, writer locks,
CLI lifecycle, and source-free metadata exports. The real desktop editor still
requires [the manual pilot](reports/observer-pilot.md). See
[collector validation](reports/observer-validation.md) for results and limits.

Initial real-corpus results and remaining release gates are recorded in
[the validation report](reports/phase1-validation.md). Full local JSON reports
are stored in ignored `reports/local/`, not committed fixtures.

Phase 2 implementation checks and the separate scripted Collatz smoke run are
recorded in [the Phase 2 validation report](reports/phase2-validation.md).
The 10–15-target human usefulness trial remains open.

For the controlled Claude Code sandbox exercise, follow
[the pilot instructions](reports/phase1-pilot.md). They include prompts for direct
and shell edits, commit/report commands, and expected evidence states.
