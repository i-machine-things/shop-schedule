#!/bin/bash
# Run once from the cloned repo directory to set everything up.
set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -eq 0 ]; then
    echo "Do not run as root. Run as your regular user — the script uses sudo internally."
    exit 1
fi

echo "=== Shop Schedule Installer ==="
echo "Install directory: $INSTALL_DIR"
echo ""

# Dependencies
sudo apt-get update -q
sudo apt-get install -y python3-venv
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet pdfplumber reportlab

# Create .env from example if not present
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
fi

# Read a single key from .env (strips surrounding quotes)
_get_env() { grep -m1 "^$1=" "$2" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"; }

# Write or replace a key='value' line in .env (safe for & | " \ $ and backticks)
_set_env() {
    local key="$1" val="$2" file="$3"
    local q="'" dq='"'
    local escaped="${val//$q/${q}${dq}${q}${dq}${q}}"
    local line="${key}='${escaped}'"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        local tmp
        tmp="$(mktemp)"
        while IFS= read -r l; do
            if [[ "$l" == "${key}="* ]]; then
                printf '%s\n' "$line"
            else
                printf '%s\n' "$l"
            fi
        done < "$file" > "$tmp"
        mv "$tmp" "$file"
    else
        printf '%s\n' "$line" >> "$file"
    fi
}

echo ""
echo "=== Configure .env ==="

_v=$(_get_env SHOP_NAME "$INSTALL_DIR/.env")
if [ -z "$_v" ] || [ "$_v" = "Your Shop Name" ]; then
    read -rp "  Shop name (shown in schedule header): " _v || true
    [ -n "$_v" ] && _set_env SHOP_NAME "$_v" "$INSTALL_DIR/.env"
fi

_v=$(_get_env GMAIL_USER "$INSTALL_DIR/.env")
if [ -z "$_v" ] || [ "$_v" = "your@gmail.com" ]; then
    read -rp "  Gmail address: " _v || true
    [ -n "$_v" ] && _set_env GMAIL_USER "$_v" "$INSTALL_DIR/.env"
fi

_v=$(_get_env GMAIL_PASS "$INSTALL_DIR/.env")
if [ -z "$_v" ] || [ "$_v" = "xxxx-xxxx-xxxx-xxxx" ]; then
    echo "  (App Password — generate at https://myaccount.google.com/apppasswords)"
    read -rsp "  Gmail App Password: " _v || true; echo
    [ -n "$_v" ] && _set_env GMAIL_PASS "$_v" "$INSTALL_DIR/.env"
fi

_v=$(_get_env PDF_COMPANY_NAME "$INSTALL_DIR/.env")
if [ -z "$_v" ] || [ "$_v" = "Your Company Name" ]; then
    read -rp "  Company name as it appears in the PDF header (optional, Enter to skip): " _v || true
    [ -n "$_v" ] && _set_env PDF_COMPANY_NAME "$_v" "$INSTALL_DIR/.env"
fi

# Placeholder schedule
mkdir -p "$INSTALL_DIR/public"
if [ ! -f "$INSTALL_DIR/public/schedule.html" ]; then
    cat > "$INSTALL_DIR/public/schedule.html" << 'EOF'
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta http-equiv="refresh" content="60">
<style>body{background:#07070f;color:#4af;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;font-size:24px}</style>
</head><body>Waiting for Foreman's Report PDF...</body></html>
EOF
fi

# Create page-rotation config from example if not present
if [ ! -f "$INSTALL_DIR/public/pages.json" ]; then
    cp "$INSTALL_DIR/pages.json.example" "$INSTALL_DIR/public/pages.json"
fi

# Create raw PDF directory for display uploads
mkdir -p "$INSTALL_DIR/public/raw"

# Install & start HTTP server
sed "s|__USER__|$USER|g; s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    "$INSTALL_DIR/foreman-server.service" \
    | sudo tee /etc/systemd/system/foreman-server.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable foreman-server
sudo systemctl restart foreman-server

# Add cron job (every 15 minutes)
CRON="*/15 * * * * $INSTALL_DIR/run_update.sh >> /tmp/shop-schedule.log 2>&1"
( crontab -l 2>/dev/null | grep -v shop-schedule; echo "$CRON" ) | crontab -

echo ""
echo "=== Done ==="
echo "1. Review/edit $INSTALL_DIR/.env if any credentials need updating"
echo "2. Drop a PDF into $INSTALL_DIR/incoming/ to test, or email it directly"
echo "3. View at:    http://$(hostname -I | awk '{print $1}'):8080/"
echo "4. Upload at:  http://$(hostname -I | awk '{print $1}'):8080/upload.html"
echo "5. Edit $INSTALL_DIR/public/pages.json to manually add URLs to the kiosk rotation"
