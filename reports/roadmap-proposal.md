# Blindspot v1: simplified roadmap

Recalibrated on 2026-10-04 for a bare-bones presentation MVP. This supersedes the
previous broader phase plan. The product scope is [DESIGN.md](../DESIGN.md).

## Goal

Show a developer which files or regions have recorded display evidence, then
make it easy to inspect one and choose what to revisit. Keep the explanation
honest: display is not reading, and no record is not proof of never viewing.

## Already built

The local VS Code collector, receiver, SQLite persistence, source highlighting
and localhost/extension overviews exist. We can reuse them. Further infrastructure
is not required before presenting the idea.

## Next

1. Simplify the default localhost dashboard: a small summary, file list and
   source highlighting. Move diagnostic and advanced measurement details out of
   the main presentation flow.
2. Run a short demo on the small pilot: show a file with display evidence, one
   without it, pause/stop and a visible split pane. Fix anything that breaks it.
3. Present the flow and gather feedback about whether it is understandable and
   useful. Improve the demo based on those concrete findings.

The existing extension view can remain available. A second polished UI and the
previous full desktop acceptance matrix are not prerequisites for this demo.

## Later, only when needed

Optional quizzes, richer change/agent context, longer-session reliability,
performance tuning, retention, larger repositories and standalone distribution.
None is an automatic next phase. Do not start these until actual use or an
explicit request justifies the extra scope.
