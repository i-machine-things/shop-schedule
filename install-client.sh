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
sudo apt-get install -y curl
# unclutter may be absent on minimal installs — non-fatal
sudo apt-get install -y unclutter 2>/dev/null || echo "Note: unclutter unavailable — cursor will stay visible"
# Debian/Armbian uses 'chromium'; Raspberry Pi OS / Ubuntu use 'chromium-browser'
sudo apt-get install -y chromium 2>/dev/null \
    || sudo apt-get install -y chromium-browser \
    || { echo "Error: could not install Chromium — check your apt sources." >&2; exit 1; }

# Resolve actual binary path
if command -v chromium &>/dev/null; then
    CHROMIUM_BIN=chromium
elif command -v chromium-browser &>/dev/null; then
    CHROMIUM_BIN=chromium-browser
else
    echo "Error: Chromium binary not found after install." >&2
    exit 1
fi

# Launcher: disables screen blanking, hides cursor, then polls until the server
# is reachable before opening Chromium. Handles power outages where boot order
# is unpredictable — the client simply waits rather than showing an error page.
sudo tee /usr/local/bin/shop-kiosk > /dev/null << LAUNCHER
#!/bin/bash
# Disable DPMS and screen blanking for this X session
xset s off s noblank -dpms 2>/dev/null || true
# Hide mouse cursor (requires unclutter)
unclutter -idle 0.1 -root &>/dev/null &

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

echo ""
echo "=== Done ==="
echo "Displaying: $SERVER_URL/kiosk.html"
echo "Check status: sudo systemctl status shop-kiosk"
