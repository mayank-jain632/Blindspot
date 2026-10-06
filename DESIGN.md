# Blindspot v1 — presentation MVP

Blindspot helps a developer see which parts of a codebase have appeared in their
editor and choose something to revisit. Display evidence is a practical starting
point for awareness; it does not prove reading or understanding.

This is a small local side project. The immediate goal is a clear working demo,
not a production platform. This scope supersedes the earlier broad roadmap.

## The demo

1. Open a small project in VS Code and start recording.
2. Open or scroll through a few source files. Visible split panes count too.
3. Open a localhost dashboard to see files and their recorded display evidence.
4. Select a file, see highlighted observed regions, and choose what to revisit.

The extension collects observations and provides simple recording controls.
The localhost dashboard is the main presentation surface. The existing extension
overview may remain available, but matching two elaborate interfaces is not a v1
requirement. Background tabs alone do not establish display.

## What v1 needs

- Start, pause and stop recording with a visible status.
- One small local Git project with a basic eligible source inventory.
- A file list with simple labels such as **Display recorded** and
  **No display recorded**, plus a count of files with evidence.
- Basic source highlighting and a click to inspect a file.
- A short explanation that displaying some lines does not mean the whole file
  was viewed, and missing evidence does not mean it was never viewed.
- Local persistence using the SQLite storage already built.

Advanced dwell filters, provenance details, timelines and diagnostic records can
remain available behind a secondary inspector; they should not dominate the demo.
V1 does not need a configurable scoring model. Existing version checks can remain
in the backend; further cross-version mapping refinements are deferred. For a
simple presentation, use stable demo files and show changed/uncertain evidence
plainly instead of promising complete historical tracking.

## Where we are

The extension, receiver, SQLite store and React localhost dashboard are implemented.
The dashboard uses the supplied design exports for a Risk landing view, file
detail, existing-quiz Review, a directory treemap, recorded activity, calibration
and PNG export. Unsupported comprehension and authorship metrics are omitted.
See [the dashboard contract](reports/dashboard-contract.md) for the actual fields
and design adaptations. Quiz generation remains paused.
The earlier collector pilot worked, and automated checks cover the new build.
The new desktop behavior has not yet been manually confirmed. We already have
most of the infrastructure needed for a demo; further infrastructure is not the
next milestone. Existing source, observations and quiz records remain intact.

A per-file study guide (code units, unseen lines, last-changing commits) is part of file
detail and a full page. It is deterministic and local. An optional Ollama button adds
clearly labelled plain-English explanations from a model on the same machine.

Quizzes are authored outside the app: the guide produces a prompt, any chat model writes the
questions, and Blindspot validates and serves them. Keys are unverified and labelled so.

## The next step

Run one short dashboard demonstration: record a file, leave
another unobserved, and confirm the dashboard explains the difference. Also check
pause/stop and a visible split pane. Fix defects that block that demonstration.

V1 is ready to present when this flow is easy to launch, understandable without
an explanation of the architecture, and repeatable on the demo project.

## Deferred

Quiz generation stays paused. Agent attribution and hooks, all-day recording
hardening, extensive performance tuning, retention tools, larger-history
incremental processing, comprehensive editor support, cloud/accounts, team
features and distribution polish are outside this presentation MVP. Revisit a
feature when the demo or actual use exposes a need, or when explicitly requested.

Existing hardening can stay; removing working code simply to replace it with a
less capable version would add work. Simplification means a smaller product
promise, a simpler default experience and fewer new requirements.

The [roadmap](reports/roadmap-proposal.md) is deliberately short.
[Earlier design details](reports/design-history.md) and
[the 0.3 implementation report](reports/observer-03.md) remain historical context,
not a checklist of prerequisites for presenting v1.
