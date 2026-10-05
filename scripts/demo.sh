#!/bin/sh
# Rebuild the dashboard, then serve it. dashboard_dist is gitignored, so a
# git pull alone never updates what the receiver serves.
set -e
cd "$(dirname "$0")/.."
npm --prefix dashboard ci --silent
npm --prefix dashboard run build --silent
echo "Built: $(ls blindspot/observer/dashboard_dist/assets/*.css)"
exec .venv/bin/python -B -m blindspot observer serve \
  --workspace sandbox/observer-pilot \
  --state-dir reports/local/observer-state \
  --port 7777
