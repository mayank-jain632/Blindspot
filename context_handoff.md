# Blindspot context handoff

## Goal

Build a small local presentation MVP that shows which code files and lines have
appeared in VS Code. Display evidence is not proof of reading or understanding.
Keep the project simple; quiz generation is paused.

## Current state

- VS Code collector, localhost receiver, SQLite storage, and React dashboard are
  implemented.
- Dashboard: Map landing view, file detail/source shading, existing quiz review,
  directory Map, Timeline, Insights, and PNG Share card.
- Latest UI pass: pure black background; percentage-not-seen headline; concise copy and
  plain-language states; optional empty columns/panels hidden; Timeline counts
  distinct files per week; monospace metrics; shared “How this is measured” panel.
- The extension has connection recovery and event batching. Pause/resume has
  been manually confirmed previously.
- Dashboard build, frontend/backend unit checks, and browser checks passed in the
  preceding work session. The current dashboard files may be uncommitted; do not
  reset or overwrite work.

## Since the manual demo (branch `claude/ecstatic-darwin-rrrnol`)

- Serif/sun theme (Cormorant + EB Garamond, amber/orange gap states) and a restyled quiz review.
- Study guide per file: side panel plus a full page (`#guide?path=...`). Built from Python AST
  or patterns plus `git blame` (`blindspot/observer/guide.py`); no model.
- Optional Ollama explanations (`blindspot/observer/explain.py`): loopback endpoint only, cached in
  the observer state folder, labelled as generated. Needs a manual try with a real model.
  Rollback point before it: commit `f21ab92` (local tag `pre-ollama`; the tag could not be pushed).
- `scripts/seed_demo.py` builds a repeatable sample project with activity and one quiz;
  `scripts/demo.sh` rebuilds the dashboard (its build output is gitignored) and serves it.
- Quiz generation, paste-in path (`blindspot/observer/quizgen.py`): guide card -> prompt -> paste reply -> quiz
  in the existing review store; results screen has "report wrong" (removes the set). Rollback tag before
  it: local `pre-quizgen`. Next planned step: let Ollama produce the same JSON automatically, plus a blind
  second pass that re-answers each question to catch bad keys.
- Fixed: the Map phone-width flake (the treemap rendered a 900px default before measuring).

## Next step: manual end-to-end demo

From the repository root:

```sh
npm --prefix dashboard run build
.venv/bin/python -B -m blindspot observer serve \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state \
  --port 7777
```

Open <http://127.0.0.1:7777>. Stop an older receiver in its own terminal with
Ctrl+C before starting this one. In VS Code, open `sandbox/observer-pilot`, start
recording, view/scroll one source file, leave another untouched, and check Risk,
Map, and File detail. Also try pause/resume and a visible split pane. Report
anything confusing or inconsistent with what you did; fix only concrete demo
blockers.

The receiver state path is local and may contain existing pilot observations;
preserve it. Do not add quiz generation, cloud features, agent attribution, or
production architecture without a concrete need or an explicit request.

## Useful references

- [README and run commands](README.md)
- [Product scope](DESIGN.md)
- [Simplified roadmap](reports/roadmap-proposal.md)
- [Dashboard data contract and design decisions](reports/dashboard-contract.md)
- [Observer pilot instructions](reports/observer-pilot.md)

## Important limits

Only this VS Code editor's recorded activity is visible. Background tabs do not
count as on-screen evidence. Missing evidence does not prove a file was never
viewed. Quiz accuracy compares answers with a generated key that may be wrong.
Everything is local; no analytics or telemetry are intended.

## Dashboard polish (2026-10-06)

- Header combines project, recording status and refresh; session details are collapsed.
- Map has search, directory filtering and Export PNG; mobile retains the legend and filters.
- File detail has sticky actions, source, compact evidence and direct unseen-section lesson links.
- Learning uses a compact file list; lessons prioritize Code and Quiz, with optional Explain.
- Guide metadata/export and correct quiz explanations are collapsed; quiz results link back to the file.
- Mobile uses More navigation and a section selector. Coverage colors/hatching remain; chrome glow is reduced.
- Existing collector, storage and grading behavior remain intact. No new automatic quiz generation.
