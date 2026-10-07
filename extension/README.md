# Blindspot

See which lines appeared in VS Code while recording, then revisit the gaps in a
local dashboard. Works alongside any coding agent. Display does not prove reading
or understanding; Blindspot does not identify who wrote a change.

**Preview release: macOS and Linux, local trusted Git workspaces only.** Requires
VS Code 1.95+, Python 3.11+ and Git. Windows, SSH, WSL and Codespaces are unsupported.
The extension needs the companion receiver. No account or model is required.

## Install and connect

Until a public release is published, obtain the wheel and VSIX built from this
repository. Follow the [release setup instructions](https://github.com/mayank-jain632/Blindspot/blob/main/docs/release.md).

1. Install the VSIX with **Extensions → … → Install from VSIX**.
2. Install the companion wheel into a new Python virtual environment and run its
   receiver for your Git checkout. The receiver includes the built dashboard;
   Node is not needed to run it.
3. Run **Blindspot: Connect to Receiver** from the command palette. Select the
   `connection.json` path printed in the receiver terminal.
4. Open the Blindspot eye icon in the activity bar. Choose **Start recording**,
   open or scroll a source file, then choose **Open full dashboard**.

The dashboard refreshes every ten seconds and has a Refresh button. Pause, Resume
and Stop are available in Coverage or the command palette. Keep the receiver
terminal running. Restarting it with the same state directory preserves history.

## What is retained

Starting recording saves source snapshots for supported files, including unopened
files, plus paths, timestamps and visible ranges. It considers up to 500 candidate
files, skips files over 256 KiB and excludes generated/vendor folders, lockfiles,
environment files and symlinks. These exclusions are not a secret detector.

Everything is kept in the state directory you choose, outside the observed project.
No telemetry is sent. Stop recording and stop the receiver before deleting that
directory to remove its saved data. Earlier work outside recording is not visible.

Study guides work without a model. Optional quizzes use generated, unverified
answer keys. Copying a quiz prompt into another service shares the selected code
with that service. Quiz passes do not grant visibility credit or lower a whole
file's priority. Optional Ollama explanations are local and unverified.

## Troubleshooting

- **Cannot connect:** start the receiver, select its connection file, and check
  that VS Code opened the same Git checkout printed by the receiver.
- **Unknown file:** resume recording, save the file and refresh.
- **No display recorded:** start recording and open or scroll supported files.
- **Receiver restarted:** allow reconnection, or run **Blindspot: Reconnect Now**.
- **Old dashboard:** refresh after installing the updated companion wheel.

MIT licensed. Source and issues: [GitHub](https://github.com/mayank-jain632/Blindspot).
