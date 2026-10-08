# Blindspot context handoff

## Goal

Build a small local presentation MVP that shows which code files and lines have
appeared in VS Code. Display evidence is not proof of reading or understanding.
Keep the project simple; quiz generation is paused.

## Current state

- VS Code collector, localhost receiver, SQLite storage, and React dashboard are
  implemented.
- Dashboard: Map landing view, file detail/source shading, existing quiz review,
  directory Map, Learning, Insights, and PNG Share card.
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

## Sidebar and activity chart (2026-10-06)

- Extension 0.3.1 contributes a Blindspot activity-bar Coverage webview: unseen percentage, tracked files, changed unseen lines, file shortcuts, recording controls and full-dashboard link. Token stays in the extension host; workspace checks precede reads. Uses existing receiver configuration.
- Timeline now uses animated weekly line series: distinct files with visibility events vs distinct files with filesystem events. These are not human/agent authorship. Reduced-motion disables the reveal. Python receiver must restart for new weekly fields.
- Learning returns to compact two-column cards with a small overview, coverage bars and direct guide/quiz shortcuts.
- Actual VS Code sidebar appearance and controls require manual confirmation after restarting the Extension Development Host.

## Timeline removed (2026-10-06)

User approved removing Timeline from desktop/mobile navigation. Its dashboard view is removed; old #timeline links redirect to Map. Activity storage and backend data remain intact. A future history view should track the unseen backlog rather than event volume.

## Sidebar theme and file filter (2026-10-06)

Sidebar 0.3.2 uses dashboard colors and bundled fonts, a small colored coverage grid, coverage bars and state-appropriate recording controls. Zero-gap files are omitted from its gap list. Both surfaces lead with percentage not seen. The Map search field now disables autofill and marks common password-manager ignore attributes; the screenshot's profile icon appears to be a browser-injected overlay, not application markup. A browser preview of the actual sidebar HTML checks narrow layout and fonts; native VS Code appearance still needs manual confirmation after reloading the extension host.

## Packaged portfolio preview (2026-10-07)

Current version: extension and receiver 0.4.0. MIT confirmed by the user. Build
with `.venv/bin/python scripts/build_release.py`; artifacts are in ignored `dist/`.
Public setup/native walkthrough: `docs/release.md`. Check results and limitations:
`reports/release-readiness.md`. Assets are self-contained; Connect to Receiver
replaces F5 for users. Guides refresh on visibility changes and display their own
counted ranges. Non-Python/invalid Python guides use conservative blocks. Final
newlines do not add phantom gaps. Practice passes no longer lower whole-file
priority. Historical/rejected results remain readable. Explanation cache includes
prompt inputs and local-model redirects are refused. Screenshots are current.

165 Python, 38 extension and 8 frontend unit tests passed, plus browser regressions.
VSIX CLI install passed in `reports/local/release-vscode`; 12 wiring/overview tests
ran against installed code/assets with mocked APIs. Wheel smoke passed outside the
checkout. Native installed-editor walkthrough and Linux verification remain manual.
Publisher is still development `blindspot-local`; confirm before final rebuild.
Nothing published. Next: user desktop acceptance, publisher/distribution decisions,
then explicit publication approval. Automatic quiz generation remains deferred.

## Linux receiver verified (2026-10-08)

Packaged 0.4.0 wheel smoke passed inside disposable Docker Linux ARM64
(`python:3.11-slim`, Python 3.11.15, kernel 6.12.54-linuxkit). Tested fresh install,
CLI/server, Git inventory, dashboard assets and Host/Origin rejection. No code
changes required. Log: reports/local/release-linux-smoke.log. Native Linux VS Code
walkthrough remains unverified; Windows is blocked by fcntl imports plus Unix
setup paths. Release notes now distinguish receiver smoke from desktop testing.
