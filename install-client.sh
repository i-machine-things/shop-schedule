#!/bin/bash
# install-client.sh — Set up a kiosk display pointing at the schedule server.
# No desktop environment required: installs minimal X11 + Chromium only.
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

# Minimal X11 stack + Chromium — no desktop environment needed
sudo apt-get update -q
sudo apt-get install -y curl xserver-xorg xinit x11-xserver-utils chromium
# unclutter may be absent on minimal installs — non-fatal
sudo apt-get install -y unclutter 2>/dev/null \
    || echo "Note: unclutter unavailable — cursor will remain visible"

# Grant display and input device access (takes effect at next login)
sudo usermod -aG video,input "$USER" 2>/dev/null || true

USER_HOME=$(getent passwd "$USER" | cut -d: -f6)

# X startup: invoked by xinit as the sole X client — no WM, no DE
sudo tee /usr/local/bin/shop-kiosk-x > /dev/null << XSTART
#!/bin/bash
xset s off s noblank -dpms
unclutter -idle 0.1 -root &>/dev/null &

until curl -sf "$SERVER_URL" > /dev/null 2>&1; do
    sleep 5
done
exec /usr/bin/chromium \\
  --kiosk \\
  --noerrdialogs \\
  --disable-infobars \\
  --no-first-run \\
  --disable-session-crashed-bubble \\
  --disable-restore-session-state \\
  "$SERVER_URL/kiosk.html"
XSTART
sudo chmod +x /usr/local/bin/shop-kiosk-x

# Launcher: starts X on VT7 with the kiosk as the only client.
# xinit exits when Chromium exits, so Restart=always in the service handles recovery.
sudo tee /usr/local/bin/shop-kiosk > /dev/null << LAUNCHER
#!/bin/bash
exec xinit /usr/local/bin/shop-kiosk-x -- :0 vt7 -keeptty -auth "$USER_HOME/.kiosk-xauth"
LAUNCHER
sudo chmod +x /usr/local/bin/shop-kiosk

# Systemd service — StandardInput=tty gives the service ownership of VT7
sudo tee /etc/systemd/system/shop-kiosk.service > /dev/null << SERVICE
[Unit]
Description=Shop Schedule Client Kiosk
After=multi-user.target

[Service]
User=$USER
Group=tty
WorkingDirectory=$USER_HOME
Environment=HOME=$USER_HOME
ExecStart=/usr/local/bin/shop-kiosk
Restart=always
RestartSec=10
StandardInput=tty
TTYPath=/dev/tty7

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable shop-kiosk
sudo systemctl start shop-kiosk

echo ""
echo "=== Done ==="
echo "Displaying: $SERVER_URL/kiosk.html"
echo "If the display stays blank, log out and back in — group changes need a new session."
echo "Check status: sudo systemctl status shop-kiosk"
