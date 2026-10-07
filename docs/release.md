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
assets). It inspects package contents and publishes nothing. The current
`blindspot-local` publisher is a development ID; replace it with the confirmed
Marketplace publisher before the final package. No public release URL exists yet.

After building, run the isolated receiver smoke check and regenerate screenshots:

```sh
.release-venv/bin/python scripts/check_release.py
npm --prefix dashboard run screenshots
```

Screenshot capture expects a development `.venv/bin/python` and Chrome. It creates
and disposes its own seeded project. The sidebar screenshot is a webview preview,
not evidence of a native VS Code walkthrough.

## Install and launch (user)

Download both artifacts from the eventual release, or use the locally built files.
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
the same Git checkout, run **Blindspot: Connect to Receiver**, and select the
`connection.json` printed by the receiver. Then open Coverage from the Blindspot
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
profile. Start the packaged receiver as shown above and select its connection
file in this window.

1. Follow the user setup above from outside the Blindspot repository. Confirm Map
   loads and first-run says **No display recorded**.
2. Start recording; open and scroll a supported file. Refresh Map and its guide.
   Seen lines should increase and guide gaps should shrink without source edits.
3. Open two files in a split pane. Both visible panes should receive coverage;
   a background tab should not.
4. Pause, scroll, resume and stop. Coverage should change only while recording.
5. Start a second recording. Edit a closed file with a coding agent; inspect its
   changed unseen lines, then open them and check that the gap shrinks.
6. Restart the receiver with the same state directory. Verify recovery, saved
   coverage, sidebar and full dashboard. Test **Show Codebase Overview** too.
7. Optional practice: copy a quiz prompt, paste JSON, take it, report a wrong key,
   and confirm the completed result remains readable as rejected. Change its
   source and confirm results become historical, without current credit.

Desktop interaction requires manual confirmation. Browser/HTTP tests and package
inspection do not establish native VS Code behavior or Linux compatibility.
