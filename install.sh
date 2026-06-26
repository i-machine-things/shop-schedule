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
sudo apt-get install -y python3-venv samba
# wsdd enables WSD discovery for Windows clients — package name varies by distro
sudo apt-get install -y wsdd 2>/dev/null || sudo apt-get install -y wsdd2 2>/dev/null || true
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet pdfplumber reportlab
chmod +x "$INSTALL_DIR/run_update.sh"

# Create .env from example if not present
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
fi

# Read a single key from .env; handles single-quoted values written by _set_env.
_get_env() {
    local raw
    raw=$(grep -m1 "^$1=" "$2" 2>/dev/null | cut -d= -f2-) || true
    [ -z "$raw" ] && return 0
    eval "printf '%s' $raw" 2>/dev/null || true
}

# Prompt for a password, echoing * per character; outputs the value on stdout
_read_masked() {
    local prompt="$1" pass="" char
    printf '%s' "$prompt" > /dev/tty
    while IFS= read -r -s -n1 char; do
        case "$char" in
            '') break ;;
            $'\x7f') [[ -n "$pass" ]] && { pass="${pass%?}"; printf '\b \b' > /dev/tty; } ;;
            *) pass+="$char"; printf '*' > /dev/tty ;;
        esac
    done
    printf '\n' > /dev/tty
    printf '%s' "$pass"
}

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
    chmod 600 "$file"
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
    _v=$(_read_masked "  Gmail App Password: ") || true
    [ -n "$_v" ] && _set_env GMAIL_PASS "$_v" "$INSTALL_DIR/.env"
fi

_v=$(_get_env PDF_COMPANY_NAME "$INSTALL_DIR/.env")
if [ -z "$_v" ] || [ "$_v" = "Your Company Name" ]; then
    read -rp "  Company name as it appears in the PDF header (optional, Enter to skip): " _v || true
    [ -n "$_v" ] && _set_env PDF_COMPANY_NAME "$_v" "$INSTALL_DIR/.env"
fi

# Placeholder pages (schedule + kiosk) shown before first PDF arrives
mkdir -p "$INSTALL_DIR/public"
_waiting_html='<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta http-equiv="refresh" content="60">
<style>body{background:#07070f;color:#4af;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;font-size:24px}</style>
</head><body>Waiting for Foreman'"'"'s Report PDF...</body></html>'
if [ ! -f "$INSTALL_DIR/public/schedule.html" ]; then
    printf '%s\n' "$_waiting_html" > "$INSTALL_DIR/public/schedule.html"
fi
if [ ! -f "$INSTALL_DIR/public/kiosk.html" ]; then
    printf '%s\n' "$_waiting_html" > "$INSTALL_DIR/public/kiosk.html"
fi

# Process any PDFs in incoming/ and regenerate schedule.html so the sidebar
# is populated on first boot rather than waiting for the first cron run.
GMAIL_USER='' "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/process_drop.py" --no-regen 2>&1 || true
if [ -f "$INSTALL_DIR/last_report.pdf" ]; then
    echo "Regenerating schedule from existing PDF..."
    ( set -a; source "$INSTALL_DIR/.env" 2>/dev/null; set +a
      GMAIL_USER='' "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/update_schedule.py" ) || true
fi

# Create page-rotation config from example if not present
if [ ! -f "$INSTALL_DIR/public/pages.json" ]; then
    cp "$INSTALL_DIR/pages.json.example" "$INSTALL_DIR/public/pages.json"
fi

# Create raw PDF directory for display uploads
mkdir -p "$INSTALL_DIR/public/raw"

# Create PDF drop-in directory
mkdir -p "$INSTALL_DIR/incoming"

# Install & start HTTP server
sed "s|__USER__|$USER|g; s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    "$INSTALL_DIR/foreman-server.service" \
    | sudo tee /etc/systemd/system/foreman-server.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable foreman-server
sudo systemctl restart foreman-server

# Allow guest connections for the drop share; patch any legacy 'map to guest = never'
sudo sed -i 's/^\s*map to guest\s*=.*/   map to guest = bad user/' /etc/samba/smb.conf
if ! grep -q 'map to guest' /etc/samba/smb.conf 2>/dev/null; then
    tmp=$(mktemp)
    awk '/^\[global\]/{print; print "   map to guest = bad user"; next}1' \
        /etc/samba/smb.conf > "$tmp"
    sudo mv "$tmp" /etc/samba/smb.conf
fi

# Remove [homes] share so the user home directory is not exposed via SMB
if grep -q '^\[homes\]' /etc/samba/smb.conf 2>/dev/null; then
    tmp=$(mktemp)
    awk '/^\[homes\]/{skip=1;next} /^\[/{skip=0} !skip{print}' \
        /etc/samba/smb.conf > "$tmp"
    sudo mv "$tmp" /etc/samba/smb.conf
fi

# Migrate legacy incoming/processed/ to BASE_DIR/processed/ if it exists
if [ -d "$INSTALL_DIR/incoming/processed" ]; then
    mkdir -p "$INSTALL_DIR/processed"
    find "$INSTALL_DIR/incoming/processed" -name "*.pdf" \
        -exec mv {} "$INSTALL_DIR/processed/" \; 2>/dev/null || true
    rmdir "$INSTALL_DIR/incoming/processed" 2>/dev/null || true
fi

# Configure SMB share for incoming/ drop folder
if ! grep -q '\[schedule-drop\]' /etc/samba/smb.conf 2>/dev/null; then
    sudo tee -a /etc/samba/smb.conf > /dev/null << EOF

[schedule-drop]
   comment = Shop Schedule PDF Drop
   path = $INSTALL_DIR/incoming
   guest ok = yes
   force user = $USER
   writable = yes
   browseable = yes
   create mask = 0664
   directory mask = 0775
   veto files = /processed/
EOF
fi

# Patch existing installs: add veto files and migrate to guest access
if grep -q '\[schedule-drop\]' /etc/samba/smb.conf 2>/dev/null; then
    if ! grep -A10 '\[schedule-drop\]' /etc/samba/smb.conf | grep -q 'veto files'; then
        sudo sed -i '/\[schedule-drop\]/a\   veto files = \/processed\/' /etc/samba/smb.conf
    fi
    sudo sed -i '/^\[schedule-drop\]/,/^\[/{/valid users/d}' /etc/samba/smb.conf
    if ! grep -A10 '\[schedule-drop\]' /etc/samba/smb.conf | grep -q 'guest ok'; then
        sudo sed -i '/\[schedule-drop\]/a\   guest ok = yes' /etc/samba/smb.conf
    fi
    if ! grep -A10 '\[schedule-drop\]' /etc/samba/smb.conf | grep -q 'force user'; then
        sudo sed -i "/\[schedule-drop\]/a\\   force user = $USER" /etc/samba/smb.conf
    fi
fi
sudo systemctl enable smbd nmbd
sudo systemctl restart smbd nmbd
# Enable wsdd/wsdd2 if either was installed
for svc in wsdd wsdd2; do
    systemctl list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}.service" \
        && sudo systemctl enable "$svc" && sudo systemctl restart "$svc" || true
done

# Add cron job (every 15 minutes)
CRON="*/15 * * * * \"$INSTALL_DIR/run_update.sh\" >> /tmp/shop-schedule.log 2>&1"
( crontab -l 2>/dev/null || true ) | grep -v shop-schedule | { cat; echo "$CRON"; } | crontab -

echo ""
echo "=== Done ==="
echo "1. Review/edit $INSTALL_DIR/.env if any credentials need updating"
echo "2. Drop a PDF into $INSTALL_DIR/incoming/ to test, or email it directly"
echo "3. View at:    http://$(hostname -I | awk '{print $1}'):8080/"
echo "4. Upload at:  http://$(hostname -I | awk '{print $1}'):8080/upload.html"
echo "5. Edit $INSTALL_DIR/public/pages.json to manually add URLs to the kiosk rotation"
echo "6. Drop PDFs via SMB: \\\\$(hostname -I | awk '{print $1}')\\schedule-drop  (no password needed)"
