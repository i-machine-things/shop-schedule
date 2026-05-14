#!/bin/bash
# Run this once on the Raspberry Pi to set everything up.
set -e

INSTALL_DIR="$HOME/foreman-schedule"

echo "=== Foreman Schedule Installer ==="
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

# Copy files
sudo mkdir -p "$INSTALL_DIR"
sudo cp update_schedule.py run_update.sh "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/run_update.sh"
sudo chown -R "$USER:$USER" "$INSTALL_DIR"

# Create .env from example if not present
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp .env.example "$INSTALL_DIR/.env"
    echo ""
    echo ">>> Edit $INSTALL_DIR/.env with your Gmail credentials before continuing <<<"
    echo "    Use a Gmail App Password (not your regular password)."
    echo "    Generate one at: https://myaccount.google.com/apppasswords"
    echo ""
fi

# Placeholder schedule (served from public/ so .env is never exposed over HTTP)
sudo mkdir -p "$INSTALL_DIR/public"
sudo chown "$USER:$USER" "$INSTALL_DIR/public"
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
    sudo cp foreman-kiosk.service /etc/systemd/system/
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
sudo cp foreman-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable foreman-server
sudo systemctl start foreman-server

# Add cron job (every 15 minutes)
CRON="*/15 * * * * $INSTALL_DIR/run_update.sh >> /tmp/foreman-schedule.log 2>&1"
( crontab -l 2>/dev/null | grep -v foreman-schedule; echo "$CRON" ) | crontab -

echo ""
echo "=== Done ==="
echo "1. Edit $INSTALL_DIR/.env with your Gmail credentials"
echo "2. Run: python3 $INSTALL_DIR/update_schedule.py"
echo "   (point it at an existing PDF first to test the display)"
echo "3. Email any Foreman's Report PDF — it will appear within 15 min"
echo "4. View at: http://$(hostname -I | awk '{print $1}'):8080/kiosk.html"
echo "   (or /schedule.html for the raw table without page rotation)"
echo "5. Edit $INSTALL_DIR/public/pages.json to add URLs to the rotation"
