# Blindspot

See which lines appeared in VS Code while recording, then revisit the gaps in a
local dashboard. Works alongside any coding agent. Display does not prove reading
or understanding; Blindspot does not identify who wrote a change.

**Preview release: macOS and Linux, local trusted Git workspaces only.** Requires
VS Code 1.95+, Python 3.11+ and Git. Windows, SSH, WSL and Codespaces are unsupported.
The receiver and dashboard are bundled. No account or model is required.

## Install and connect

1. Install Blindspot from Marketplace or install the VSIX with
   **Extensions → … → Install from VSIX**. Python 3.11+ and Git must be installed.
2. Open one trusted local Git checkout in VS Code.
3. Open the Blindspot eye icon in the activity bar. Choose **Start recording**,
   open or scroll a source file, then choose **Open full dashboard**.

Blindspot starts its bundled local server automatically on a free port. No
terminal command, pip install, or connection file selection is needed. The server
stops when the extension shuts down; reopening the sidebar starts it again with
your saved history. Stopping recording leaves the dashboard available.

The dashboard refreshes every ten seconds and has a Refresh button. Pause, Resume
and Stop are available in Coverage or the command palette.
Manual connection settings take priority. Clear **Blindspot: Connection File**
in VS Code Settings to return to automatic discovery. Older receivers still need
manual connection. Manually running a companion receiver remains an advanced
option; a matching running receiver is reused and is not stopped by the extension.

## What is retained

Starting recording saves source snapshots for supported files, including unopened
files, plus paths, timestamps and visible ranges. It considers up to 500 candidate
files, skips files over 256 KiB and excludes generated/vendor folders, lockfiles,
environment files and symlinks. These exclusions are not a secret detector.

Everything is kept in VS Code's extension global storage, in a separate directory
per project, outside the observed project. A manually managed receiver uses its
chosen state directory. No telemetry is sent. Close the VS Code window before
deleting managed data. The **Blindspot Observer** output channel shows its state
directory. Earlier work outside recording is not visible.

Study guides work without a model. Optional quizzes use generated, unverified
answer keys. Copying a quiz prompt into another service shares the selected code
with that service. Quiz passes do not grant visibility credit or lower a whole
file's priority. Optional Ollama explanations are local and unverified.

## Troubleshooting

- **Cannot start:** install Python 3.11+ and Git, then reload VS Code. Check the
  **Blindspot Observer** output channel for startup errors.
- **Old manual connection:** clear **Blindspot: Connection File** in Settings to
  use the automatic server.
- **Unknown file:** resume recording, save the file and refresh.
- **No display recorded:** start recording and open or scroll supported files.
- **Receiver restarted:** allow reconnection, or run **Blindspot: Reconnect Now**.
- **Old dashboard:** update the extension, reload VS Code and reopen the dashboard.

MIT licensed. Source and issues: [GitHub](https://github.com/mayank-jain632/Blindspot).

## Preview

![Local coverage dashboard](https://raw.githubusercontent.com/mayank-jain632/Blindspot/main/docs/screenshots/map.png)

![Coverage sidebar webview preview](https://raw.githubusercontent.com/mayank-jain632/Blindspot/main/docs/screenshots/sidebar.png)
