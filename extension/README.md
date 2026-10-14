# Blindspot

**Know which parts of your codebase you have actually had on screen.**

AI coding agents can change a project faster than you can inspect it. Blindspot
makes that visibility gap concrete. It tracks the source lines displayed in VS
Code during opt-in recording, maps the parts you have and have not seen, and
helps you work through the gaps with file details and structured study guides.

Blindspot works alongside any coding agent. It observes editor activity rather
than depending on a particular agent's conversation logs.

![Directory coverage map](https://raw.githubusercontent.com/mayank-jain632/Blindspot/main/docs/screenshots/map.png)

*Screenshots use sample data. Colors represent display coverage, not authorship.*

## Get started

1. Install **Blindspot** by **mayank-jain** from the VS Code Marketplace.
2. Open one local Git project in VS Code and trust the workspace.
3. Click the Blindspot eye icon in the activity bar, then **Start recording**.
4. Open and scroll through your code. Choose **Full dashboard** to explore coverage.

Requires **VS Code 1.95+ and Git** on macOS or glibc-based Linux, with an ARM64 or
x64 processor. **Python is included.** There is no account, API key, pip install,
Node installation, terminal server command, or connection-file setup.

For a downloaded release package, use **Extensions → … → Install from VSIX** and
choose the package matching your operating system and processor. Marketplace
selects the matching package automatically.

The local server starts when you open Blindspot and uses an available loopback
port. First launch unpacks the included runtime locally; it downloads nothing.
Closing the VS Code window stops the server it started. Your project history
persists, but recording does not automatically resume when you reopen the window.
Pause, Resume and Stop are available in the sidebar and command palette. Stopping
recording keeps the dashboard available.

## Explore the codebase

| View | What it provides |
| --- | --- |
| **Map** | Directory tiles sized by source lines and colored by coverage. Meaningful subdirectories such as `src/catalog` and `src/billing` appear separately. Drill into groups, return with breadcrumbs, or search for a file. |
| **Risk** | A working queue of files with unseen lines and recent Git activity, so you can choose where to inspect next. |
| **File detail** | Coverage counts, source, changed unseen lines when available, and evidence behind a file's status. |
| **Learning** | Study guides that organize unseen code into sections and connect it with recent changes. Core guides work without a model. |
| **Insights** | Optional quiz results and confidence calibration, including files with unresolved confidently wrong answers. |
| **Sidebar** | Coverage summary, recording controls, file shortcuts and access to the full dashboard inside your normal editor workflow. |
| **Export PNG** | A locally rendered snapshot you can save or share. |

The headline reports the percentage of tracked lines **not seen** and shows its
underlying line counts. Red indicates no display coverage; partial coverage moves
through yellow; blue means all counted lines have display coverage. Unknown data
is neutral. Hatching indicates untested code; a directory can contain both tested
and untested files. Visibility and quiz results remain separate measures.

## How tracking works

While recording, the extension captures supported source snapshots and the line
ranges VS Code reports as visible. Split editors contribute their visible ranges;
an open background tab does not earn coverage just by being open. Recording
pauses when requested and does not fill in activity from before it started.

The bundled local companion keeps observations in SQLite and compares them with
saved source and Git history. After a file changes, it reassesses coverage for
the changed content rather than treating the entire file as permanently seen.
Unchanged, unambiguous regions may retain credit; changed or ambiguous regions
can require another look. File changes can be detected regardless of which agent
or external tool made them, within the supported tracking scope.

The React dashboard reads this local data and refreshes periodically. Its counts
are about what appeared in this editor, not whether you read or understood it.
Blindspot reports gaps; it never blocks commits, builds, or other work.

## Optional learning tools

Study guides are available without an AI service. You can also copy a scoped quiz
prompt into a chat model, import its JSON response, and answer questions with a
confidence rating. Optional explanations can use a separately installed local
Ollama model. Neither is required to use tracking or study guides.

Quiz accuracy means agreement with a generated answer key, which can be wrong.
Disputed keys can be reported and excluded from current credit. Results from
older source versions remain readable as historical practice. A quiz pass does
not mark source as seen or remove a whole file's review priority.

## Privacy and retained data

- Observations, source snapshots, paths, timestamps and quiz history remain on
  your machine. Blindspot has no telemetry, account system, or hosted backend.
- Starting recording captures supported source snapshots, **including unopened
  files**. Only displayed lines receive visibility credit.
- Data is stored per project in VS Code's extension global storage, outside your
  Git checkout. Source content remains there until you delete that project's
  data. Close the VS Code window first; the **Blindspot Observer** output channel
  shows the state path.
- The dashboard binds to `127.0.0.1`. Host validation and checks on browser mutation
  origins protect the local HTTP boundary. Fonts, dashboard assets and Python are
  bundled; starting Blindspot makes no external download.
- Copying a quiz prompt into another service shares that selected code with the
  service. Exporting a PNG can expose filenames and project information. These
  are explicit actions you control.

## Limitations

- **Visibility is not comprehension.** A line appearing on screen does not prove
  attention, review, ownership, or understanding.
- **No authorship detection.** Colors do not distinguish human-written code from
  agent-written code. Blindspot does not reconstruct an agent's reasoning.
- **This editor and recording window only.** Work in another editor, earlier
  sessions without recording, or unsupported tools is outside the visibility
  history. Disconnections and uncertain evidence can leave gaps.
- **Bounded inventory.** Tracking considers up to 500 candidate files and skips
  files larger than 256 KiB. Generated/vendor directories, environment files,
  lockfiles and symlinks are excluded. Exclusions are not a secret detector.
- **Local Git workspaces.** One checkout per VS Code window is supported. Windows,
  WSL, SSH, Codespaces, multi-root workspaces, and Alpine/musl Linux are unsupported.
- **Language boundaries vary.** Python guides use syntax-aware sections; other
  languages use conservative blocks when reliable boundaries are unavailable.
- **Generated learning material needs judgment.** Quiz keys and model explanations
  can be incorrect. They are practice aids, not validated educational scores.

## Troubleshooting

- **Nothing is tracked:** open one trusted local Git checkout and click Start
  recording. Open or scroll a supported source file, then refresh the dashboard.
- **Old connection setting:** clear **Blindspot: Connection File** in Settings to
  use the bundled server. This setting is only for advanced manual connections.
- **Startup problem:** check **View → Output → Blindspot Observer**. Reinstall the
  correct platform package if its bundled runtime is missing or fails verification.
- **After an update:** run **Developer: Reload Window**, close the old browser tab,
  then use Full dashboard again. Saved coverage stays in extension storage.

## Source and license

Blindspot is MIT licensed. The bundled Python runtime is distributed by
[Astral's Python Standalone Builds](https://github.com/astral-sh/python-build-standalone)
and retains its upstream license notices. Bundled fonts retain their licenses.

[Source](https://github.com/mayank-jain632/Blindspot) ·
[Report an issue](https://github.com/mayank-jain632/Blindspot/issues)
