#!/bin/bash
# Wrapper used by cron — loads credentials from .env then runs the updater.
set -a
source "$(dirname "$0")/.env"
set +a
SCRIPT_DIR="$(dirname "$0")"
if [ -x "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
else
    PYTHON="${FOREMAN_PYTHON:-python3}"
fi
exec "$PYTHON" "$(dirname "$0")/update_schedule.py" "$@"
