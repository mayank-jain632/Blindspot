# Maintainer release procedure

This document is for development and release verification. It is not part of the
user installation path. User instructions live directly in the root and extension
README files. Version 0.4.2 bundles the runtime, companion, dashboard and fonts.

## Build

Build tools: Python 3.11+, Node 22+, npm and Git. On the current development Mac,
use the working `.release-venv311` environment. A fresh builder can create a venv
with a working Python and install `build` into it.

```sh
.release-venv311/bin/python scripts/build_release.py --all-targets
```

The script downloads the exact upstream archives pinned in
`scripts/python-runtimes.json`, verifies SHA-256, retains upstream notices and
builds four platform VSIX packages:

- `dist/blindspot-observer-0.4.2-darwin-arm64.vsix`
- `dist/blindspot-observer-0.4.2-darwin-x64.vsix`
- `dist/blindspot-observer-0.4.2-linux-arm64.vsix`
- `dist/blindspot-observer-0.4.2-linux-x64.vsix`

`dist/blindspot-observer-0.4.2.vsix` is a convenience copy for the build host,
not an additional universal Marketplace package. The wheel is an optional CLI
artifact; users of the extension do not install it. Builds publish nothing.
The runtime archive is unpacked under extension global storage on first launch.
There is no runtime download. Updating runtime pins requires verifying upstream
release metadata, updating checksums and rebuilding every target.

## Verify

Run extension tests after a build so the native bundled runtime exists:

```sh
npm --prefix extension test
npm --prefix extension run check
npm --prefix dashboard test
npm --prefix dashboard run test:browser
.release-venv311/bin/python scripts/check_release.py
```

The receiver test strips Python from PATH, supplies invalid PYTHONHOME/PYTHONPATH,
and verifies bundled startup, dashboard assets, Git inventory, local HTTP
boundaries, external-receiver reuse and owned-process shutdown. Repeat against
extracted VSIX contents with `BLINDSPOT_TEST_EXTENSION=/path/to/extracted/extension`.
Linux tests should use a container with Node, Git and unzip, but no Python.

The standalone runtime is provided by Astral's Python Standalone Builds. Keep
all notices in `extension/runtime/` and in its archive. Runtime archives and
extracted application files are generated and ignored by Git.

## Installed-package walkthrough

Install the native VSIX in a clean VS Code profile. Do not use F5, a development
venv, a manual receiver, seeded history or a Connection File setting for this
check. Python must not be needed on the machine or in PATH.

1. Open a trusted local Git project, then open the Blindspot sidebar. Confirm
   automatic startup and a first-run explanation before recording.
2. Start recording; open and scroll a file. Check coverage and study-guide refresh.
3. Check split panes, background tabs, pause, resume, stop and a second recording.
4. Explore directory tiles, nested subdirectories, breadcrumbs and file search.
5. Ask an agent to edit a closed file. Confirm changed unseen lines, then open them
   and check coverage. Do not infer authorship from the colors.
6. Close and reopen VS Code. Confirm history persists, the server starts again,
   and recording remains off until requested. Check the full dashboard and overview.
7. Try optional quiz import/results only if advertising that flow. Generated keys
   remain unverified. Neither Ollama nor another model is needed for core tracking.

## Publish

Commit the final source and README changes, then create a GitHub release tagged
`v0.4.2` at that commit. Attach the four target-specific VSIX files; the wheel is
optional for CLI users. The repository and screenshots must be publicly reachable.

Use the Marketplace publisher `mayank-jain`. Upload the platform packages as the
same extension/version, or use the local vsce CLI with `publish --packagePath`
and the four package paths after configuring publishing credentials. Marketplace
selects the platform package automatically. This repository does not publish as
part of its build script. Follow the current official publishing documentation:
https://code.visualstudio.com/api/working-with-extensions/publishing-extension

Finally, install from Marketplace in a clean profile and follow only the listing
README. Do not treat Node/browser tests as proof of native VS Code interaction on
untested platforms. Windows, remote workspaces and Alpine/musl are unsupported.
