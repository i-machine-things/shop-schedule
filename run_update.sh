#!/bin/bash
# Wrapper used by cron — loads credentials from .env then runs the updater.
set -a
source "$(dirname "$0")/.env"
set +a
PYTHON="${FOREMAN_PYTHON:-python3}"
exec "$PYTHON" "$(dirname "$0")/update_schedule.py" "$@"
