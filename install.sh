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
read -rp "Install kiosk display (requires a monitor connected)? [y/N] " _kiosk
KIOSK_MODE=false
[[ "${_kiosk,,}" == "y" ]] && KIOSK_MODE=true

# Dependencies
sudo apt-get update -q
if $KIOSK_MODE; then
    sudo apt-get install -y python3-venv chromium-browser unclutter
else
    sudo apt-get install -y python3-venv
fi
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet pdfplumber

# Create .env from example if not present
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo ">>> Edit $INSTALL_DIR/.env with your Gmail credentials before continuing <<<"
    echo "    Use a Gmail App Password (not your regular password)."
    echo "    Generate one at: https://myaccount.google.com/apppasswords"
    echo ""
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

# Install & start kiosk service (display mode only)
if $KIOSK_MODE; then
    sed "s|User=pi|User=$USER|g; s|/home/pi/foreman-schedule|$INSTALL_DIR|g; s|/home/pi|$HOME|g" \
        "$INSTALL_DIR/foreman-kiosk.service" \
        | sudo tee /etc/systemd/system/foreman-kiosk.service > /dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable foreman-kiosk
    sudo systemctl start foreman-kiosk

    # Hide mouse cursor on idle
    AUTOSTART="/etc/xdg/lxsession/LXDE-pi/autostart"
    if [ -f "$AUTOSTART" ] && ! grep -q 'unclutter' "$AUTOSTART"; then
        echo "@unclutter -idle 0.1 -root" | sudo tee -a "$AUTOSTART"
    fi
fi

# Install & start HTTP server (always — enables remote viewing)
sed "s|User=pi|User=$USER|g; s|/home/pi/foreman-schedule|$INSTALL_DIR|g" \
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
echo "1. Edit $INSTALL_DIR/.env with your Gmail credentials"
echo "2. Drop a PDF into $INSTALL_DIR/incoming/ to test, or email it directly"
echo "3. View at: http://$(hostname -I | awk '{print $1}'):8080/schedule.html"
echo "4. Edit $INSTALL_DIR/public/pages.json to add URLs to the kiosk rotation"
