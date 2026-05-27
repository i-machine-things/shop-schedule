#!/bin/sh
set -e

# Write .env from environment variables so run_update.sh can source it
cat > /app/.env <<EOF
GMAIL_USER="${GMAIL_USER:-}"
GMAIL_PASS="${GMAIL_PASS:-}"
SHOP_NAME="${SHOP_NAME:-My Shop}"
PDF_COMPANY_NAME="${PDF_COMPANY_NAME:-}"
PDF_FILENAME="${PDF_FILENAME:-last_report.pdf}"
EOF
chmod 600 /app/.env

# Seed public/ with static files from the image on first start (won't overwrite)
for f in /app/_static/*; do
    name=$(basename "$f")
    [ -f "/app/public/$name" ] || cp "$f" "/app/public/$name"
done

# Seed pages.json from example if not present
[ -f /app/public/pages.json ] || cp /app/pages.json.example /app/public/pages.json

# Ensure runtime directories exist on the host-mounted volumes
mkdir -p /app/public/raw /app/incoming /app/processed

# Start cron daemon (runs run_update.sh every 15 minutes)
if ! cron; then
    echo "ERROR: Failed to start cron daemon" >&2
    exit 1
fi

# Run the HTTP server in the foreground
exec python3 /app/server.py
