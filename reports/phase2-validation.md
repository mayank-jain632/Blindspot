# Phase 2 implementation and experiment results

Date: 2026-10-03. **Implementation ready; human usefulness gate remains open.**
This report distinguishes automated workflow checks from user review outcomes.

## Delivered

- `target export` selects committed source and explicit context, binding paths,
  inclusive spans, whole-file/content hashes, checkout identity, and source SHA.
- `quiz import` validates 3–5 questions, four distinct options, integer keys,
  explanations, source citations, and current revision bindings. Invalid sets
  retain rejection reasons; duplicate content retains its original set identity.
- An open-book terminal loop records immutable choices and confidence, supports
  pause/resume, and withholds all keys until the entire attempt completes.
- Shared commands support starting, showing, answering, completing, viewing
  results, practice, rejecting a set, and inspecting effective review status.
- Effective target status handles staleness, unreachable source revisions,
  first-attempt passes, later confidently-wrong revocations, and recomputation
  when a causing key is rejected. Historical attempts remain intact.
- Atomic, POSIX-locked `reviews.json` is separate from `prototype.json` scan state.
  Reports and briefs expose samples without changing evidence categories or
  the existing churn-based queue order. Read-only queries create no review locks.

No model integration, automatic source upload, repository metadata folder,
SQLite migration, web server, or editor extension was added.

## Automated verification

Run from the Blindspot checkout:

```sh
.venv/bin/python -B -m unittest discover -s tests -t . -v
```

The suite covers the existing evidence behavior plus target bounds and committed
reads, context binding, malformed/tampered imports, duplicate JSON keys, hidden
keys, immutable answers and confidence, resume, first-attempt/practice limits,
content-based deduplication, source reachability, changed content before answering
and completion, target-specific revocation, disputed-key recomputation, concurrent
process starts, combined reports, state-directory guards, and scan preservation.

Final result: **74 tests passed** in 16.607 seconds on the existing Python 3.11
virtual environment: 48 evidence tests and 26 review tests. The prepared pilot
was checked afterward: one validated set, zero attempts, target unattempted.
CLI help and a read-only terminal doctor run also succeeded. A direct whitespace
check covered the changed source, tests, and documentation; the checkout's files
are currently untracked, so `git diff --check` alone cannot verify them.

## Scripted real-checkout smoke run

Inspected checkout: `/Users/mayankjain/College/Fall2026/SWE_logs/cs373-collatz`.
Captured HEAD: `c16c3b8ec00b2f80aeee09deced911ec1253f4e1`.
Target: `Collatz.py:50–101` (`cache-and-range`), with explicit context at
`11–25` and `116–137`. Five manually authored, source-audited questions concern
cache indexing, path backfill, readiness assumptions, inclusive ranges, and
caller-visible behavior. Their educational usefulness has not been measured.

The run exercised 24 CLI invocations in approximately 2.51 seconds, with warm
filesystem caches. This is a workflow smoke measurement, not a scan benchmark
or human review duration. Using isolated `reports/local/phase2-smoke-state`:

| Check | Observed result |
|---|---|
| Start/show before completion | No keys, correctness, explanations, or rationale exposed |
| Answer acknowledgments | Accepted/idempotent only; no correctness revealed |
| All-correct first completion | Current passing target sample recorded |
| Starting the same set again | Original completed first attempt returned |
| A second same-binding set with a scripted solid wrong answer | Earlier target pass revoked |
| Rejecting that causing set | Original pass restored; rejected answers excluded from effective flags |
| Read-only doctor with the smoke state | Target sample displayed separately; evidence counts unchanged |
| Input preservation | 514 input files, including repository files/Git metadata and nine associated logs, retained byte hashes and mtimes |

The deliberate wrong answer and dispute were **scripted lifecycle checks**.
They are not a discovered user misunderstanding or an actual disputed Collatz
key. Production Collatz code was read, not executed or changed. The evidence
distribution remained 9 agent-observed, 4 unresolved, 1 inherited, and 0
no-agent-observed. No scan inventory was written by the read-only doctor run.

Private artifacts in ignored `reports/local/`:

- `phase2-collatz-target.json`: explicit source/context export.
- `phase2-collatz-quiz.json`: key-bearing authoring artifact; avoid before taking the review.
- `phase2-smoke-results.json`: run time, checks, preservation counts, and pilot ID.
- `phase2-smoke-state/`: scripted attempts, separate from user calibration.
- `phase2-pilot-state/`: one validated set with **zero user attempts** at preparation.

The ready set ID is `b7727440cc1d4d4794012298d2261ba2`.
Follow [the pilot instructions](phase2-pilot.md) for the first user review and
further author/import cycles. Local artifacts are not portable fixtures: exports
are bound to the actual checkout identity, location, and commit history.

## First user-run attempt and follow-up

The first attempt, `8d17a4d309024f6f8c7e54de1f51654d`, completed on October 3,
2026 at 21:39:00 UTC. It recorded **1/5 correct against the stored key**, no
passing sample, and one solid-but-wrong answer. The target remains current and
its effective status is `attempted`, with no prior pass to revoke.

| Question | Confidence | Agreement with stored key |
|---|---|---|
| q1 | solid | correct |
| q2 | shaky | incorrect |
| q3 | guessed | incorrect |
| q4 | solid | incorrect |
| q5 | shaky | incorrect |

The user confirmed this was **mostly a workflow test**. It is not evidence of
actual knowledge gaps or demonstrated question usefulness. Elapsed
start-to-completion time was 34.706 seconds, including any pauses; active review
time is unknown. Prior familiarity, disputes, useful corrections, and willingness
to repeat an understanding review have not yet been recorded.

The follow-up adds `quiz feedback`, with explicit `workflow-test` or
`understanding-review` purpose, usefulness, optional prior familiarity, active
minutes, and a note. Annotations are appended separately from immutable answers;
updates preserve older annotations, and repeated identical submissions are
idempotent. Status/doctor distinguish annotated purposes from unclassified
completed attempts. These annotations do not change grades, passes, or evidence.
Disputing a key still requires `quiz reject`. The original attempt now has its
confirmed workflow-test purpose recorded; usefulness remains `unreported` and
familiarity/active minutes remain absent.

At preparation, two fresh source-grounded sets were imported with zero attempts:

| Target | Committed span | Questions | Set ID |
|---|---|---:|---|
| cycle-length | Collatz.py:28–47 | 3 | fac20760806b4fda8d40fcceda74d48a |
| cache-test-design | CollatzTest.py:220–250 | 3 | 1d766ed3b45b4ba2af22d96e29709bcf |

They review different target bindings. Passing them cannot clear the original
target's mechanically recorded confidently-wrong flag. Source/context exports
and key-bearing authoring files stay in ignored `reports/local/`. Preparation
preserved the original set and all original attempt data, plus the byte hashes
and mtimes of the same 514 input files and nine associated logs. Collatz source
and tests were not executed. Purpose annotations provide context for the grade;
they do not rewrite it as evidence of understanding or misunderstanding.

New regression checks cover feedback validation, classification, append history,
idempotency, read-only and legacy-state reads, state-directory guards,
preservation through scans, and purpose-only feedback without invented usefulness.
They use disposable repositories; no test answers were added to the new user
sets. Private `phase2-first-attempt-results.json` records the observed attempt
and new set IDs. The final follow-up suite passed **79 tests** (48 evidence,
31 review) in 46.711 seconds on Python 3.11. Read-only status/doctor verified
three validated sets, one completed workflow test, zero understanding reviews,
and zero unclassified completed attempts, without changing review state. The
initial 74-test and scripted-smoke results above remain historical.

## First understanding review: difficulty feedback

The cycle-length set was completed as an understanding review in attempt
`a5866f02c0b54911b9f58dde0054d0a3`. It recorded **2/3 correct against the key**:

| Question topic | Confidence | Agreement with stored key |
|---|---|---|
| Original argument versus final loop value | solid | correct |
| Independence from the cache | guessed | correct |
| Recursion, stack space, and memoization | solid | incorrect |

Elapsed time was 332.045 seconds (about 5 minutes 32 seconds), including pauses.
Active time remains unknown. The target is current; no all-correct sample pass
was recorded. The user said they did their best but had forgotten details after
working on this code a while ago. Purpose is recorded as `understanding-review`.
The user then reported that the quiz felt a little too hard and mentioned low
motivation. That difficulty feedback is recorded as an appended annotation;
useful corrections and prior-familiarity rating remain unreported. Answers,
keys, grades, and earlier annotations are preserved.

This supplies a candidate refresher topic: recursion does not automatically cache
results; a recursive walk can also consume stack space. The guessed correct
answer is uncertain agreement with the key, not proof of luck or firm knowledge.
Neither result establishes a lasting knowledge gap or a useful learning outcome.
The difficulty feedback does establish friction in the current exercise.

Current pilot totals: three validated sets, two completed attempts (one workflow
test, one understanding review), and one unattempted cache-test-design set.
The 79-test implementation check above is unchanged; this update records user
feedback and does not change application code. Private details are in
`phase2-cycle-length-results.json`.

**Difficulty proposal (deferred):** reduce effort before expanding the target count. Try a brief
plain-language refresher and three concrete input/output or change-consequence
questions, with an optional deeper challenge. Keep any guided exercise explicitly
identified; its results cannot be compared as though it had the same conditions
as the original open-book review. Recheck difficulty, usefulness, and willingness
to repeat before preparing a larger batch. This guided flow is proposed, not yet
implemented.

**Latest priority:** the user has deferred difficulty tuning until quizzes can be
generated independently of an always-open Claude Code session. Design an
on-demand generation path using selected source/context and the existing import
validator; provider choice and credentials remain open. The current application
still makes no model calls. Existing Claude evidence comes from saved local
transcripts and already needs no running Claude Code process.

## Remaining gate and roadmap

Phase 2 needs approximately 10–15 human-reviewed targets across suitable evidence
states. Record active time, prior familiarity, disputes, useful corrections to the
developer's mental model, and willingness to repeat the session. One workflow
test and one understanding review are recorded above. Difficulty feedback calls
for improving the questions/flow before scaling the trial. Useful corrections
and preference for another session have not been established. Collatz's
existing queue matches churn-only ordering; ranking benefit remains unproven.

The JSON store is a local prototype using macOS/Linux file locking. Withholding
keys is a review-interface condition, not protection against reading local state.
Shape validation does not certify answer keys. Repository/source moves need
explicit reconciliation; the prototype does not silently remap quiz identities.

After useful reviews demonstrate a reason to continue, Phase 3 migrates persistent
records to SQLite, adds incremental scanning and transactional scan publication,
and incorporates effective review data in queue ordering. Phase 4 adds the minimal
web workflow using the same validator and grading service. Generation integrations
and editor support follow observed need in Phase 5.
