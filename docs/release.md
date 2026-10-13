# Local release setup

Preview supports macOS/Linux, VS Code 1.95+, Python 3.11+ and Git. Use one trusted
local Git checkout per receiver. Windows and remote workspaces are unsupported.

## Build the release artifacts (maintainer)

Requires Node 22+ in addition to Python and Git. From the repository root:

```sh
python3 -m venv .release-venv
.release-venv/bin/python -m pip install build
.release-venv/bin/python scripts/build_release.py
```

Packages use [VS Code’s vsce tooling](https://code.visualstudio.com/api/working-with-extensions/publishing-extension).

This produces `dist/blindspot_local-0.4.0-py3-none-any.whl` (receiver, built
dashboard and fonts) and `dist/blindspot-observer-0.4.0.vsix` (extension and its
bundled receiver, dashboard and fonts). The wheel is optional for manual hosting.
It inspects package contents and publishes nothing. The extension uses
the `mayank-jain` Marketplace publisher. Confirm ownership before publishing.

After building, run the isolated receiver smoke check and regenerate screenshots:

```sh
.release-venv/bin/python scripts/check_release.py
npm --prefix dashboard run screenshots
```

Screenshot capture expects a development `.venv/bin/python` and Chrome. It creates
and disposes its own seeded project. The sidebar screenshot is a webview preview,
not evidence of a native VS Code walkthrough.

## Install and launch (user)

1. Install the Marketplace extension or the locally built VSIX.
2. Open one trusted local Git checkout in VS Code, with Python 3.11+ and Git installed.
3. Open the Blindspot sidebar. Its bundled server starts automatically. Click Start
   recording, then Open full dashboard. No terminal server command is required.

The extension stores each project's history in its VS Code global storage,
outside the project. Closing the window stops its server; Stop recording leaves
the dashboard available. It reuses matching external receivers without owning
their lifetime. A manual Connection File setting takes priority; clear it for
automatic operation. The output channel prints the server URL and state path.

### Optional manual hosting

The separate wheel remains available for terminal-driven development or hosting.
Node and this repository are not needed after obtaining the artifacts.

```sh
python3 -m venv "$HOME/.local/share/blindspot/venv"
"$HOME/.local/share/blindspot/venv/bin/python" -m pip install /absolute/path/to/blindspot_local-0.4.0-py3-none-any.whl
"$HOME/.local/share/blindspot/venv/bin/blindspot" observer serve \
  --workspace /absolute/path/to/your-git-project \
  --state-dir "$HOME/.local/share/blindspot/state/my-project" \
  --port 7777
```

Leave that terminal running. Open `http://127.0.0.1:7777`.

In VS Code, install the VSIX using **Extensions → … → Install from VSIX**. Open
the same Git checkout; the extension automatically discovers its running receiver.
Then open Coverage from the Blindspot
activity-bar icon and start recording. No F5 configuration is needed.

Use a separate state directory and port for another checkout. Stop with Ctrl+C;
restart the same command to keep your history. To update, stop the receiver,
install the new wheel with `pip install --upgrade /path/to/new.whl`, restart it,
install the new VSIX and reload VS Code.

Recording captures supported source snapshots, including unopened files, locally.
Only displayed lines gain visibility credit. State retains source contents and
activity until you delete it. Stop recording and the receiver before deleting
the chosen state directory. Pasting quiz prompts into a third-party chat shares
the selected code; keys and local-model explanations are unverified.

## Final installed-package walkthrough

Use a clean VS Code profile with only the packaged extension, not F5:

From the repository root, the verification profile can be opened with:

```sh
code --new-window \
  --user-data-dir "$PWD/reports/local/release-vscode/profile" \
  --extensions-dir "$PWD/reports/local/release-vscode/extensions" \
  /absolute/path/to/your-git-project
```

The local verification installed `dist/blindspot-observer-0.4.0.vsix` in this
profile. Install the freshly rebuilt VSIX before checking the automatic server;
stop any manual receiver for this test and leave **Blindspot: Connection File**
empty in Settings. Receivers advertise locally in `~/.local/share/blindspot/receivers`;
stale entries are ignored and multiple matches require manual selection.

1. Follow the user setup above from outside the Blindspot repository. Confirm Map
   loads and first-run says **No display recorded**.
2. Start recording; open and scroll a supported file. Refresh Map and its guide.
   Seen lines should increase and guide gaps should shrink without source edits.
3. Open two files in a split pane. Both visible panes should receive coverage;
   a background tab should not.
4. Pause, scroll, resume and stop. Coverage should change only while recording.
5. Start a second recording. Edit a closed file with a coding agent; inspect its
   changed unseen lines, then open them and check that the gap shrinks.
6. Close and reopen the test window. Verify automatic server startup, saved
   coverage, sidebar and full dashboard. Start recording again; recording does not
   resume automatically on window reopen. Test **Show Codebase Overview** too.
7. Optional practice: copy a quiz prompt, paste JSON, take it, report a wrong key,
   and confirm the completed result remains readable as rejected. Change its
   source and confirm results become historical, without current credit.

Desktop interaction requires manual confirmation. The packaged receiver smoke
passed on Linux ARM64 in Docker with Python 3.11. Browser/HTTP tests and package
inspection do not establish native Linux VS Code behavior. See
[verification details](../reports/release-readiness.md).
