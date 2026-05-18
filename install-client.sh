#!/bin/bash
# install-client.sh — Set up a dumb display kiosk pointing at the schedule server.
# Usage:  bash install-client.sh http://SERVER_IP:8080
#   or:   curl http://SERVER_IP:8080/install | bash
set -euo pipefail

SERVER_URL="${1:-__SERVER_URL__}"

if [ "$EUID" -eq 0 ]; then
    echo "Do not run as root. Run as your regular user." >&2
    exit 1
fi
if [ -z "$SERVER_URL" ]; then
    echo "Usage: $0 http://SERVER_IP:8080" >&2
    exit 1
fi

echo "=== Shop Schedule Client Kiosk ==="
echo "Server: $SERVER_URL"
echo ""

# Install dependencies
sudo apt-get update -q
if apt-cache show chromium-browser &>/dev/null 2>&1; then
    CHROMIUM_PKG=chromium-browser
else
    CHROMIUM_PKG=chromium
fi
sudo apt-get install -y "$CHROMIUM_PKG" unclutter curl

# Resolve actual binary name (varies by distro/arch)
if command -v chromium-browser &>/dev/null; then
    CHROMIUM_BIN=chromium-browser
elif command -v chromium &>/dev/null; then
    CHROMIUM_BIN=chromium
else
    echo "Error: Chromium not found after install." >&2
    exit 1
fi

# Disable screen blanking (Pi-specific; silently skipped elsewhere)
sudo raspi-config nonint do_blanking 1 2>/dev/null || true

# Launcher: waits for server to be reachable before opening Chromium.
# This handles the case where the client boots before the server is ready
# (e.g. after a power outage where boot order is unpredictable).
sudo tee /usr/local/bin/shop-kiosk > /dev/null << LAUNCHER
#!/bin/bash
until curl -sf "$SERVER_URL" > /dev/null 2>&1; do
    sleep 5
done
exec $CHROMIUM_BIN \\
  --kiosk \\
  --noerrdialogs \\
  --disable-infobars \\
  --no-first-run \\
  --disable-session-crashed-bubble \\
  --disable-restore-session-state \\
  "$SERVER_URL/kiosk.html"
LAUNCHER
sudo chmod +x /usr/local/bin/shop-kiosk

# Systemd service — Restart=always handles crash/power-cycle recovery
sudo tee /etc/systemd/system/shop-kiosk.service > /dev/null << SERVICE
[Unit]
Description=Shop Schedule Client Kiosk
After=graphical.target

[Service]
User=$USER
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority
ExecStart=/usr/local/bin/shop-kiosk
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable shop-kiosk
sudo systemctl start shop-kiosk

# Hide cursor when idle (LXDE-Pi autostart)
AUTOSTART="/etc/xdg/lxsession/LXDE-pi/autostart"
if [ -f "$AUTOSTART" ] && ! grep -q 'unclutter' "$AUTOSTART"; then
    echo "@unclutter -idle 0.1 -root" | sudo tee -a "$AUTOSTART"
fi

echo ""
echo "=== Done ==="
echo "Displaying: $SERVER_URL/kiosk.html"
echo "Check status: sudo systemctl status shop-kiosk"
