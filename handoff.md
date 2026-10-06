# Blindspot handoff (for Codex)

Written 2026-10-06 at the end of a long Claude Code session. Read `AGENTS.md` first; it still governs
scope. This file says where things stand and what to do next. `context_handoff.md` is the earlier,
shorter handoff and has a "Since the manual demo" section that overlaps with this one.

## What this is

Blindspot is a small local tool for a developer working with coding agents. A VS Code extension
records which source lines were on screen, a localhost receiver stores that in SQLite, and a React
dashboard shows what is still a "blind spot" (unseen code), with a per-file study guide and optional
quizzes. The primary purpose is a LinkedIn/resume project, so **keep it a simple, polished MVP**. Do not
add production architecture, accounts, cloud features or agent attribution. Display evidence is not proof
of reading or understanding; the UI says so and any new copy must too.

## Repo state

- Branch: `claude/ecstatic-darwin-rrrnol`, pushed, clean at `91a11da` when this was written.
- No pull request has been opened (the user has not asked for one). Do not open one unprompted.
- Base for all of the work below: `21580f9` ("Data reading ready, moving onto dashboard dev").
- Rollback tags exist **locally only** in the Claude session's checkout, because the session's git
  proxy refused tag pushes: `pre-ollama` = `f21ab92`, `pre-quizgen` = `002f61e`. They may not exist in
  your checkout. Recreate with `git tag pre-ollama f21ab92 && git tag pre-quizgen 002f61e` (and push if
  you want them on GitHub). The user asked for a tag right before each model-related feature; keep doing
  that (tag the commit just before you start the Ollama quiz-generation work).

## Run it

Python 3.11+, Node 22+, Git. No Python runtime dependencies.

```sh
scripts/demo.sh   # npm ci, rebuild the dashboard, serve sandbox/observer-pilot on :7777
```

or the repeatable sample project (no VS Code needed):

```sh
npm --prefix dashboard ci && npm --prefix dashboard run build
python3 scripts/seed_demo.py                       # sandbox/demo (gitignored); --force to rebuild
.venv/bin/python -B -m blindspot observer serve \
  --workspace sandbox/demo/project --state-dir sandbox/demo/state --port 7777
```

**Gotcha that cost real time:** the built dashboard (`blindspot/observer/dashboard_dist/`) is gitignored
and the server serves it from disk. After any `git pull` or branch switch you must rebuild or the old UI
keeps serving. A hard refresh does not help.

Optional: `--ollama-url` (loopback only) and `--ollama-model` on `observer serve`.

## Tests

```sh
.venv/bin/python -B -m unittest discover -s tests -t .      # 159 tests, ~45 s, all passing
npm --prefix dashboard test                                  # 7 unit tests
npm --prefix dashboard run test:browser                      # Playwright against a disposable fixture
node --test extension/test/*.test.js                         # extension tests (unchanged this session)
```

- `test:browser` expects Google Chrome at `/opt/google/chrome/chrome` (the repo's test uses
  `channel: 'chrome'`) and a `.venv/bin/python`. On a machine with stock Chrome it just works. In the
  Claude cloud sandbox we symlinked Playwright's Chromium to that path and `.venv/bin/python` to
  `python3`.
- The browser test previously failed about 40% of runs on a phone-width Map assertion. Fixed (the treemap
  rendered a 900px default before measuring). 6 of 6 runs passed afterwards.
- `dashboard/test/data.test.js` forbids hex colors outside `:root` in `style.css`. Use CSS variables or
  named colors (`white`, `black`, `gray`) elsewhere.

## Architecture map

Backend (`blindspot/observer/`):
- `store.py`, `sqlite_store.py`, `visibility.py`: event journal, SQLite, line-range derivation
  (`derive`, `file_stats`, `current_files`, `current_source`). Pre-existing, hardened; avoid rewriting.
- `server.py`: stdlib `ThreadingHTTPServer`. Dashboard routes under `/api/dashboard/*`. GET routes read;
  POST routes require an explicit loopback `Origin` header.
- `dashboard.py`: read models and actions (`Dashboard` class): overview, evidence, review, and the new
  guide / explain / quiz methods.
- `guide.py` (new): per-file study guide. Python via `ast`; JS/TS/Go/Rust/Java/Kotlin/C-like/Ruby/shell/SQL
  via line patterns; Markdown via headings; anything else as 40-line blocks. `git blame --porcelain -w`
  gives the last commit per line. Pure `build(text, path, reported_ranges, history)`; no model.
- `explain.py` (new): optional Ollama client (loopback only), prompts, on-disk cache
  (`<state-dir>/explanations.json`).
- `quizgen.py` (new): picks a quiz range for a guide unit, writes a prompt for any chat model, parses and
  normalizes a pasted JSON reply, flags identifiers the explanation names that are not in the code.
- Review/quiz store and rules live in `blindspot/review/` (pre-existing): `targets.py` (manifest, 10-300
  lines / 16 KiB, bound to committed HEAD content), `service.py` (`validate_questions` requires 3-5
  questions, 4 distinct options, rationale lines inside target; `reject`, attempts, grading).

Frontend (`dashboard/`, Vite + React 19, no router library, hash routes):
- `src/main.jsx` holds all views: Risk, Map, Timeline, Insights, Share, FileDetail (side panel),
  `#guide?path=...` full guide page (`GuidePage`/`GuideBody`), `QuizBox`, `ExplainBox`, `Review`
  (`#review?set_id=...`), `ReportQuestion`.
- `src/data.js`: API helpers (`api` hides server messages; `explainApi` surfaces them), layout, guide
  helpers, Markdown export. `src/charts.jsx`: treemap, weekly chart, Share-card canvas.
- `src/style.css`: all styles; theme tokens in `:root`.
- Built output goes to `blindspot/observer/dashboard_dist/` (gitignored).

Other: `extension/` (VS Code collector, unchanged), `scripts/seed_demo.py`, `scripts/demo.sh`,
`docs/screenshots/` (committed PNGs used by the README), `ui_templates/` (original design exports).

## What changed this session (all on the branch)

1. **Theme.** Cormorant Garamond (headings) + EB Garamond (body) + IBM Plex Mono (code/metrics). Pure black,
   amber/orange "sun" accent, corona glow, sunspot logo. State scale: gaps are loud orange, seen is
   charcoal. Share-card canvas matches. Quiz review restyled to the supplied template.
2. **Study guide.** Side-panel section in file detail plus a full page, with an Unseen code / Whole file
   toggle, outline, expandable code, "changes you haven't seen" (from blame), Markdown copy and print.
   Deterministic and labelled "no AI".
3. **Ollama explanations** (optional): Explain per unit and Summarize this file on the guide page. Only the
   selected unit's own lines, unseen ranges, signature, calls and last commit message are sent; the file
   summary sends an outline, not code. Loopback endpoint enforced; no proxy. Output is labelled
   "Generated by <model> on this machine. Unverified, may be wrong."
4. **Quizzes, paste-in path.** "Make a quiz" on a guide unit gives a prompt to paste into any chat model;
   pasting the JSON reply back validates it and stores it in the existing review store; "Take quiz" then
   uses the existing review screen. Results screen has "This answer key looks wrong" (two-step), which
   rejects the whole set via the existing `reject` (history kept, results stop counting).
5. **Demo and docs.** `scripts/seed_demo.py` (sample "Shelfmark" project with commits, activity and one
   quiz), README rewritten with screenshots and a two-minute try-it, `scripts/demo.sh`.
6. **Fixes.** Guide regex ReDoS on long tab-heavy lines (declarations over 400 chars are skipped);
   Map phone-width flake.

## Decisions and constraints worth knowing

- Quizzes only exist for **committed** code: the manifest binds to HEAD content and the dashboard offers a
  quiz only when the working file's hash equals it. The UI returns a clear "commit first" message.
- Quiz size: 3 questions for targets under 40 lines, 4 for longer. Units under 10 lines are grown with
  neighbouring lines; units over 300 lines/16 KiB are windowed from their first unseen lines.
- Answer keys from a model are never verified. Everything says so. The mitigation is the report-wrong
  button plus the grounding warnings. No user code is ever executed.
- The paste-in parser is forgiving about shape (fences, prose, `question`/`choices`, `A)` labels, letter
  answers) but strict about meaning (no 1-based guessing, cited lines must be in range). A failed paste
  creates nothing in the store.
- The user explicitly declined commit-based questions ("what did this change do?").
- Default Ollama model is chosen from `/api/tags` (prefers a name containing "coder"); no model name is
  hard-coded. Check Ollama's library for current names before recommending one.
- Partly seen is `#7A3A2A` (deep ember); never seen is `#EE6A2A`.

## Not verified (be honest about these)

- **No real Ollama model has been run through `explain.py`.** It is tested only against a fake Ollama
  server. Prompt quality with 7-14B models on the user's M5 is unknown.
- **No real chat model's quiz reply has been pasted in.** Only hand-written replies. Expect to loosen the
  parser if real replies show new shapes. The user said they will test.
- The VS Code extension was not touched and was not re-run in desktop VS Code after the UI changes (the
  user did a manual demo earlier and said it worked "like a charm").
- Nothing was run on the user's own machine or against `sandbox/observer-pilot`.

## Known issues and rough edges

- `api()` in `data.js` maps every non-409 error to a generic message; new code that needs server text must
  use `explainApi`.
- Guide limitations: blame shows only the last commit per line; non-Python end lines come from indentation
  heuristics; Python "calls" lists are names, not meaning.
- Timeline weekly bars are narrow in a wide panel; a test pins the bar width to 36px, so changing it means
  changing that test.
- Quiz-eligible only for committed files; a dirty tree hides the Make a quiz result with an error.
- The quiz target for a short unit includes neighbouring code, so the review screen can show more than the
  unit.

## Suggested next steps

1. **Ollama quiz generation** (the user's chosen order: paste-in first, then Ollama). Add a "Generate with
   local model" button in `QuizBox`. Reuse `quizgen.build_prompt` and `quizgen.normalize`, call
   `Ollama.chat` (consider Ollama's JSON/structured `format` option, verify against current docs), retry
   once or twice on parse failure. Then add a **blind second pass**: ask the model to answer each question
   without the key and drop or flag questions where it disagrees. Keep keys labelled unverified. Tag the
   commit first (`pre-ollama-quizgen`).
2. Have the user try real model output for both paste-in quizzes and Ollama explanations; tune
   `quizgen.build_prompt`, `explain.UNIT_TASK` and the parser from what actually comes back.
3. Record a short screen capture of Risk -> Map -> Guide -> Quiz for LinkedIn using the seeded demo.
4. Optional polish: wider Timeline chart (update the 36px test), per-question report instead of whole-set
   removal, README badges.
5. Do not start: cloud/accounts, team features, agent attribution/hooks, all-day recording hardening,
   retention tools. They are deferred in `DESIGN.md`.

## Conventions

- Match surrounding code: dense, few comments, stdlib only on the Python side (no new runtime deps), no
  new frontend libraries unless clearly justified.
- Commit messages in this repo's recent style; one logical change per commit; push to the working branch.
- Prefer the smallest change that makes the demo better. Verify with proportionate checks, and report
  failing tests plainly.
- When running Playwright locally, screenshots land in ignored `reports/local/dashboard-checks/`. Committed
  README images are in `docs/screenshots/` and were generated from the seeded demo.
