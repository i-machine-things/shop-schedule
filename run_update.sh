#!/bin/bash
# Wrapper used by cron — loads credentials from .env then runs the updater.
set -a
source "$(dirname "$0")/.env"
set +a
exec python3 "$(dirname "$0")/update_schedule.py" "$@"
