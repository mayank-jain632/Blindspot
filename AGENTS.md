# Working preferences

- Default to simple, pragmatic implementations for side projects, prototypes and
  presentation MVPs. Build the smallest useful end-to-end experience.
- Do not add production architecture, speculative optimizations, abstractions,
  extensive edge-case handling or elaborate planning/documentation without a
  concrete need at the current milestone.
- Increase complexity when the user explicitly requests it or when actual
  corporate/production requirements justify it. Scale the solution to those
  requirements rather than assuming enterprise needs.
- Keep correctness and basic privacy safeguards. Fix real defects and verify the
  affected behavior with proportionate checks.
- Reuse working code; simplify scope and user experience before replacing
  infrastructure. Prioritize a usable demo over a growing feature list.

## Blindspot

The current scope is the presentation MVP in DESIGN.md. The localhost dashboard
is the main demo surface; the extension collects observations and offers basic
controls. Quiz generation and further production hardening are deferred. Older
reports and the archived design describe past work, not mandatory new scope.
