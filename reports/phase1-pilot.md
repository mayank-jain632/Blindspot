# Phase 1 Claude Code pilot

This is a controlled experiment in a real Claude Code session. It supplements
the historical repository audits; it does not establish coverage of a third
long-lived repository or complete the Phase 1 gate by itself.

The local repository is `sandbox/phase1-pilot/`, on branch `main`, with three
committed Python files and no dependencies. It is ignored by the outer Blindspot
repository. Codex created the starter files; **pre-Claude baseline does not mean
human-authored**. Blindspot currently parses Claude Code records, so those initial
Codex changes are outside its supported agent evidence.

## Start a fresh session in the pilot checkout

From a normal terminal:

```sh
cd /Users/mayankjain/Projects/blindspot/sandbox/phase1-pilot
git rev-parse --show-toplevel
git status --short
claude
```

The root must end in `/blindspot/sandbox/phase1-pilot`, and the working tree
should be clean before starting. Use a fresh session launched here, rather than
an existing session whose working directory is Blindspot. Complete the exercises
in order. Keep `baseline.py` unchanged and avoid creating extra source files,
renaming paths, resetting history, or delegating to subagents.

## Prompt 1: direct edit

Paste this into Claude Code:

```text
This checkout is a small invoice calculator and a controlled Blindspot validation
pilot. Work only in this checkout and do not delegate to subagents.

Implement subtotal_cents in calculator.py. Accept a list of nonnegative integer
cent amounts, return their sum, and return 0 for an empty list. Reject booleans
and non-integers with TypeError; reject negative integers with ValueError.

Make the source change using your direct Edit or Write tool, not Bash, shell
redirection, a script, or another tool that writes files. Do not change baseline.py
or shell_summary.py, create any other files, or commit anything.

After editing, use Bash only to run Python with -B and inline assertions for an
empty list, [125, 250, 0], and the invalid inputs [-1], [True], [1.5], and ["100"].
Do not write a test file. Run git diff -- calculator.py and report which tool
actually made the source change and whether the assertions passed.
```

Inspect the tool activity: the mutation should be an `Edit` or `Write` call.
The tests may run in Bash without affecting this distinction. If Claude uses a
different mutation tool, record that deviation rather than treating the intended
tool as evidence. Keep going only after the function and checks are correct.

## Prompt 2: shell edit

Paste this in the **same Claude Code session**:

```text
Now implement summarize_invoices in shell_summary.py. Import subtotal_cents from
calculator and return {"invoice_count": len(amounts), "total_cents":
subtotal_cents(amounts)}. Preserve the validation behavior from subtotal_cents.

For this exercise, make the source change only through your Bash tool, using a
shell heredoc or a Python script launched from Bash to write shell_summary.py.
Do not use Edit, Write, apply_patch, or a subagent to make this change. Do not
change calculator.py or baseline.py, create any other files, or commit anything.

Use python with -B and inline assertions to check an empty summary, a summary of
[125, 250, 0] with count 3 and total 375, and rejection of a negative amount.
Also print format_cents(summarize_invoices([125, 250, 0])["total_cents"]) using
baseline.format_cents; it should print $3.75. Run git diff -- shell_summary.py.
Report the actual tool that wrote the file and the check results.
```

This deliberately tests a coverage limit: the prototype records Bash activity,
but does not attribute a shell command's mutations to specific files.

## Review and commit in your terminal

Leave Claude Code with `/exit`, then run:

```sh
cd /Users/mayankjain/Projects/blindspot/sandbox/phase1-pilot
git status --short
git diff -- baseline.py
git diff -- calculator.py shell_summary.py
```

Expect only `calculator.py` and `shell_summary.py` to be modified and no diff for
`baseline.py`. Review the implementations, then commit them normally:

```sh
git add calculator.py shell_summary.py
git commit -m "Implement invoice subtotal and shell summary"
```

Do this promptly after the session (within the default 24-hour grace). Commit
both files so they are present in the captured HEAD used by Blindspot. The
baseline commit happened before this Claude session; do not amend it or use
backdated commits. Record any unexpected tool choices or failed operations when
interpreting results.

## Run Blindspot and save the evidence

From the outer Blindspot checkout:

```sh
cd /Users/mayankjain/Projects/blindspot
BLINDSPOT_PHASE1_REPO="$PWD/sandbox/phase1-pilot"
BLINDSPOT_PHASE1_STATE="$PWD/reports/local/phase1-pilot-state"
BLINDSPOT_PHASE1_AS_OF="$(.venv/bin/python -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')"
mkdir -p reports/local

.venv/bin/blindspot identity "$BLINDSPOT_PHASE1_REPO" \
  --state-dir "$BLINDSPOT_PHASE1_STATE"

.venv/bin/blindspot doctor "$BLINDSPOT_PHASE1_REPO" \
  --state-dir "$BLINDSPOT_PHASE1_STATE" \
  --now "$BLINDSPOT_PHASE1_AS_OF" \
  | tee reports/local/phase1-pilot-doctor.txt

.venv/bin/blindspot doctor "$BLINDSPOT_PHASE1_REPO" \
  --state-dir "$BLINDSPOT_PHASE1_STATE" \
  --now "$BLINDSPOT_PHASE1_AS_OF" --json \
  > reports/local/phase1-pilot-doctor.json

.venv/bin/blindspot brief "$BLINDSPOT_PHASE1_REPO/shell_summary.py" \
  --state-dir "$BLINDSPOT_PHASE1_STATE" \
  --now "$BLINDSPOT_PHASE1_AS_OF"
```

This state directory is outside the inspected pilot repository and persists in
the outer checkout's ignored local reports directory. The fresh timestamp must
be captured after the new work. Confirm that the identity command recognizes
your actual commit identity; do not add unrelated identities to change outcomes.

Expected results, assuming matching identity, a complete supported transcript,
and the tool choices above:

| File | Expected state | Evidence interpretation |
|---|---|---|
| `baseline.py` | `no_agent_observed` | No recorded Claude edit; its commit predates the session. This does not prove human authorship. |
| `calculator.py` | `agent_observed` | Successful direct Edit/Write pair at this path. |
| `shell_summary.py` | `unknown` | No direct edit pair; its new commit overlaps the session plus grace. Expect `unexplained_session_overlap`. |

The checkout should show three eligible files and at least one supported source.
The calculator may show `outside_commit` timing context because its starter
commit predates the session. That is historical timing context, not proof that
you reviewed the new implementation.

If the source count is zero, check the actual Claude session directory and root
before linking anything. If the states differ, inspect tool choices, source
diagnostics, identity, and commit times before changing the classifier. Save the
actual outcomes and deviations alongside the historical validation report.
