# Directory-map demo

Rollback checkpoint before this change: `5199622`.

`sandbox/directory-demo/Shelfmark` is a small, runnable library example with
11 tracked files. It has `src/catalog`, `src/billing`, `src/loans`, `src/web`,
tests and a CLI. Its initial observations are explicitly **synthetic demo data**,
not measured personal history or evidence of human/AI authorship. Real recording
can be added on top. No existing project or tracking history is modified.

## Try it

1. Install the rebuilt `dist/blindspot-observer-0.4.2.vsix` and reload VS Code.
   Leave **Blindspot: Connection File** empty in Settings.
2. From the Blindspot repository root, run:

   ```sh
   .release-venv311/bin/python scripts/seed_directory_demo.py --serve
   ```

   This development-only demo command prepares the project if absent and starts
   its seeded receiver on a free port. Leave it running. Ordinary extension users
   do not need this command; the extension starts its own server.
3. Open `/Users/mayankjain/Projects/blindspot/sandbox/directory-demo/Shelfmark`
   as its own VS Code folder. Open Blindspot and choose Full dashboard. It discovers
   the demo receiver automatically. Do not open the parent Blindspot checkout.
4. The overview shows meaningful directory tiles. Explore `src/catalog` and
   `src/billing`; use All directories in the breadcrumb to return. Search for
   `fines.py` to jump directly to a file. Root files are grouped separately.
5. Click Start recording. Open `src/web/cache.js` and scroll through it. Refresh
   the dashboard: its initially unseen coverage should increase. Stop recording.
6. For a live agent example, close `src/billing/fines.py` and ask your coding agent:

   > In src/billing/fines.py, add a pure function format_cents(amount) that formats
   > integer cents as dollars with two decimal places. Add boundary tests to
   > tests/test_billing.py. Keep the existing fine rules unchanged.

   Start recording before the edit. Refresh after saving, inspect the changed
   unseen lines, then open and scroll through them to show the coverage changing.
7. Stop the demo receiver with Ctrl+C when finished. Run the same demo command to
   resume its state. Without it, the extension starts its own separate history.

For a video, introduce the seed as sample data, then show directory exploration,
an agent's closed-file change, and visibility increasing as you inspect the code.
Colors show display coverage; they do not identify who authored code.

The script refuses to overwrite an existing project. To create a fresh demo,
choose a new directory with `--output sandbox/directory-demo-2 --serve` and open
that new project. Keep this additional generated folder out of Git.
