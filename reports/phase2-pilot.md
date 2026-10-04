# Phase 2: terminal review pilot

The implementation is ready. The human experiment is still open: determine
whether the questions uncover useful gaps and whether another session feels
worthwhile. Scripted smoke answers have not used your first attempt.

## Current follow-up

The original review is complete: 1/5 answers agreed with the stored key, with one
solid-but-wrong answer. The user confirmed it was mostly a workflow test. Its
purpose is recorded, while usefulness and familiarity remain unreported. The
original first attempt is preserved; rerunning it shows its completed results.

The cycle-length follow-up is now complete: 2/3 correct against the key, with one
guessed correct answer and one solid wrong answer. It is recorded as an
understanding review. The user found it a little too hard; the next product
iteration should reduce effort before expanding the trial. A brief guided
refresher is proposed but not yet implemented.

To revisit the completed cycle-length results, use:

```sh
.venv/bin/python -B -m blindspot quiz review fac20760806b4fda8d40fcceda74d48a \
  --state-dir reports/local/phase2-pilot-state
```

The cache-test-design review remains available when useful:

```sh
.venv/bin/python -B -m blindspot quiz review 1d766ed3b45b4ba2af22d96e29709bcf \
  --state-dir reports/local/phase2-pilot-state
```

Each has three questions. Cache-test-design has no started attempt; avoid opening
its `phase2-cache-test-design-quiz.json` or `reviews.json` before completing it,
since they contain the key. Passing a different target does not resolve the
original target's recorded solid wrong answer. Completing this harder review is
optional while we improve the review format.

The sections below retain instructions for the original exercise and for
authoring further sets.

## 1. Take the prepared Collatz review

Run from the Blindspot checkout:

```sh
.venv/bin/python -B -m blindspot quiz review b7727440cc1d4d4794012298d2261ba2 \
  --state-dir reports/local/phase2-pilot-state
```

This is a five-question open-book review of `Collatz.py:50–101`, with explicit
context at `11–25` and `116–137`, bound to commit
`c16c3b8ec00b2f80aeee09deced911ec1253f4e1`. It tests cache and range behavior and
caller assumptions. The terminal displays the committed source before asking
for choices **1–4** and confidence **solid / shaky / guessed**.

Do not open `reports/local/phase2-collatz-quiz.json` or the pilot state's
`reviews.json` before finishing: those files contain the stored key. Source-only
`phase2-collatz-target.json` is safe to consult. The interface withholds keys,
correctness, explanations, and source rationales until all questions are answered.
The exercise has not been independently validated as a comprehension instrument.

Enter `q` at a choice prompt or press Ctrl-C to pause. Rerun the same command to
resume. Submitted answers and confidence cannot be changed. The command prints
the attempt ID when completed; copy it to view results later:

```sh
.venv/bin/python -B -m blindspot quiz results ATTEMPT_ID \
  --state-dir reports/local/phase2-pilot-state --read-only
```

An all-correct first attempt earns a **target sample pass against the key**.
It does not establish understanding of the whole file or change its evidence
state. Confidence never gates passing. A later practice attempt cannot earn a
new first-attempt pass. A later solid-but-wrong result for the same target and
content/context binding revokes current passes until a fresh eligible set passes
or the causing key is rejected.

## 2. Challenge questionable questions

After reviewing the explanations, reject a faulty or ambiguous set:

```sh
.venv/bin/python -B -m blindspot quiz reject b7727440cc1d4d4794012298d2261ba2 \
  --state-dir reports/local/phase2-pilot-state \
  --reason "Explain the ambiguity or incorrect key here"
```

The entire set is excluded from effective calibration and cannot be served again.
Its questions and attempt history remain. Any passes or revocations it caused
are recomputed. A corrected import must use new question content and may include
`"supersedes": "b7727440cc1d4d4794012298d2261ba2"` to record the relationship.
Simply renaming IDs, changing generator labels, or reimporting identical content
cannot reset the first attempt.

## 3. Check the combined report

```sh
.venv/bin/python -B -m blindspot doctor \
  /Users/mayankjain/College/Fall2026/SWE_logs/cs373-collatz \
  --state-dir reports/local/phase2-pilot-state --read-only \
  --source-root /Users/mayankjain/College/Fall2026/cs373_MAIN/cs373-collatz
```

Use the same state directory as the review. The temporary source mapping supplies
the moved checkout's Phase 1 evidence; quizzes themselves do not need Claude logs.
The report shows review samples alongside evidence. Queue order remains the
churn baseline. No files are added to Collatz, and Claude logs remain untouched.

## 4. Prepare another target

Choose a bounded committed target with at least 10 lines. Add explicit context
for dependencies or callers needed to answer the questions. Every block is
limited to 300 lines / 16 KiB; there can be up to eight context blocks.

```sh
.venv/bin/python -B -m blindspot target export /path/to/repo/example.py \
  --start 20 --end 70 --name example-behavior \
  --context-range /path/to/repo/caller.py 10 40 \
  --output /tmp/blindspot-next-target.json
```

Output must be outside the inspected checkout and must not already exist.
Exporting sends nothing to a model. Providing it to a model session is your
explicit code-sharing step. No transcripts or provenance labels are required.

Paste this into a separate question-authoring session, adjusting paths:

```text
Read /tmp/blindspot-next-target.json. Write /tmp/blindspot-next-quiz.json as UTF-8
JSON for a Blindspot open-book code review. Read only the exported target and
context. Do not change source files, run code, or use git write commands.

Return schema_version: 1, generator: a short author/model label, manifest: the
exported JSON object copied unchanged, and questions: 3–5 question objects.
Each question needs:
- prompt: a consequence or reasoning question about the exported behavior
- options: exactly four distinct plausible strings
- correct_index: integer 0–3
- explanation: why the key is correct and the alternatives do not follow
- rationale: {path, start_line, end_line, reason}, citing a range wholly inside
  an exported target or context block

Do not invent dependencies or rely on unexported code. Avoid syntax trivia,
line-copy questions, ambiguous keys, or one question teaching another answer.
If context is insufficient, report the missing context instead of guessing.
Write the key and explanations only into the JSON file. In your response, say
only the output path and question count; do not print answers or explanations.
```

The import shape is:

```json
{
  "schema_version": 1,
  "generator": "question-author label",
  "manifest": {},
  "questions": [
    {
      "prompt": "Consequence question",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "Source-grounded explanation",
      "rationale": {
        "path": "example.py",
        "start_line": 20,
        "end_line": 30,
        "reason": "Why this source range supports the key"
      }
    }
  ]
}
```

Replace `manifest` with the complete export and supply 3–5 complete questions;
the one-question example is illustrative and will be rejected as-is.

```sh
.venv/bin/python -B -m blindspot quiz import /tmp/blindspot-next-quiz.json \
  --state-dir reports/local/phase2-pilot-state
.venv/bin/python -B -m blindspot quiz review NEW_SET_ID \
  --state-dir reports/local/phase2-pilot-state
```

Import returns a validated set ID or a retained rejection reason. Validation
checks structure and revision/citation bindings; key truth still requires review.
Changes to any target/context file, even outside the selected span, make the set
stale. A source commit outside current HEAD ancestry makes it orphaned.

## 5. Record the usefulness experiment

Use the completed attempt ID printed by `quiz review` to record feedback:

```sh
.venv/bin/python -B -m blindspot quiz feedback ATTEMPT_ID \
  --state-dir reports/local/phase2-pilot-state \
  --purpose understanding-review --useful yes --familiarity some \
  --active-minutes 4 --note "Describe the useful correction or question issue"
```

The values above are examples, not recorded observations. `--purpose` accepts
`workflow-test` or `understanding-review`; `--useful` accepts `yes`, `no`, `unsure`,
or `unreported` (the default when omitted). Familiarity is your familiarity
**before** answering: `unfamiliar`, `some`, or `familiar`. Active minutes and a
note are optional. Do not substitute wall-clock duration for active minutes if
you paused.

The original completed attempt is `8d17a4d309024f6f8c7e54de1f51654d`; its
confirmed workflow-test purpose is already recorded. Feedback is append-only: a
corrected annotation becomes current while prior annotations remain. It does not
alter grades or reject a set. `quiz status` reports purpose counts, unclassified
attempts, and usefulness counts for understanding reviews; practice and
disputed-set feedback remain visible. No count automatically satisfies Phase 2.

Review roughly 10–15 distinct targets over several sessions, including different
evidence states. Collatz has agent-observed, unresolved, and inherited files;
another Phase 1 repository can supply no-agent-observed targets when its code is
suitable. Generated outputs and tiny fixtures may not make useful questions.
Keep the open-book conditions consistent. After each completed review, record:

| Target / set ID | Evidence state | Active minutes | Prior familiarity | Key dispute | Useful correction to mental model | Worth another session? |
|---|---|---|---|---|---|---|
| Collatz cache-and-range / b7727440cc1d4d4794012298d2261ba2 (workflow test) | agent_observed | unknown (34.706 seconds elapsed) | pending | pending | pending | pending |
| Collatz cycle-length / fac20760806b4fda8d40fcceda74d48a | agent_observed | unknown (332.045 seconds elapsed) | worked on before; some details forgotten | not reported | not reported; felt a little too hard | pending |
| CollatzTest cache-test-design / 1d766ed3b45b4ba2af22d96e29709bcf | agent_observed | unattempted | pending | pending | pending | pending |

Use active minutes; stored start/completion timestamps also include pauses.
Compare the top ten suggested files with churn-only ordering and record whether
the choice helped. Current Collatz ordering is identical to that baseline, so it
does not yet demonstrate a ranking improvement. Capture preference and examples
of corrections rather than inventing a numerical quality score.

Advance to Phase 3 after lifecycle correctness holds, questions uncover useful
issues, and you voluntarily want another session. Improve questions first if they
are mostly trivia or the keys are frequently disputed.
