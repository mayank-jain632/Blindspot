# Packaged preview verification — 2026-10-07

Scope: public portfolio MVP, macOS/Linux targets. Nothing published.

## Installation

- Extension 0.4.0 contains its overview assets and bundled sidebar fonts. It no
  longer reads outside the installed extension directory.
- Companion `blindspot-local` 0.4.0 wheel includes the built React dashboard,
  fonts and MIT/font licenses. Runtime requires Python 3.11+ and Git; Node is
  needed only by maintainers building the packages.
- Connect to Receiver selects and validates `connection.json` without F5.
- `scripts/build_release.py` builds and inspects the wheel and VSIX without uploading.
- Publisher stays `blindspot-local`, explicitly pending a real Marketplace ID.

## Correctness

- Guides refresh when visible ranges change without source edits.
- Python uses AST boundaries. Other languages and invalid Python use conservative
  code blocks. Snippets display the exact disjoint ranges counted by each unit.
- Display/guide totals exclude the virtual line after a final newline. Existing
  event and snapshot formats remain compatible.
- First-run says No display recorded. Learning waits for recording; inventory
  truncation is surfaced in both dashboard and sidebar.
- Practice passes no longer lower whole-file priority. Historical/rejected results
  remain readable through Insights without current credit. Rejected keys are
  excluded from calibration.
- Long quiz units with near-end gaps select at least ten lines or explain the
  size limit. Explanation cache identity includes prompt gaps/history, system
  prompt, model and source identity. Local-model redirects are rejected.
- Public setup explains snapshots of unopened files, local retention/deletion,
  and external code sharing when copying quiz prompts into another service.

## Completed checks on macOS

- 165 Python tests passed; 38 extension tests and syntax checks passed.
- 8 frontend unit tests and the browser suite passed. Browser checks include
  unchanged-source guide refresh, real rejected-results reload, first-run,
  mobile layout, sidebar preview and local-only requests.
- VSIX installed successfully through VS Code CLI in a separate user-data and
  extensions directory. Listed version: `blindspot-local.blindspot-observer@0.4.0`.
- 12 wiring/overview tests passed against installed extension code/assets, using
  a mocked VS Code API. These do not verify native editor interactions.
- Wheel installed into a fresh disposable environment outside this repository.
  Its CLI served dashboard assets and first-run inventory; invalid Host and
  mutating Origin were rejected.
- Screenshots regenerated from a disposable Shelfmark demo. Sidebar image is a
  webview preview. Obsolete Timeline screenshot removed.

Local logs: ignored `reports/local/release-*.log`.

## Before publishing

1. Complete the native installed-package walkthrough in docs/release.md: scrolling,
   split panes, recording controls, closed-file changes, guide refresh and restart.
2. Confirm the Marketplace publisher ID, rebuild the VSIX, and choose companion
   wheel distribution (for example, a GitHub release asset).
3. Linux remains untested on this Mac. Optional explanations use fake-model tests;
   real model quality remains unverified.
4. Publish only after explicit approval. No Marketplace/PyPI upload has occurred.
