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
sudo apt-get install -y curl xserver-xorg xinit x11-xserver-utils openbox chromium
# unclutter may be absent on minimal installs — non-fatal
sudo apt-get install -y unclutter 2>/dev/null \
    || echo "Note: unclutter unavailable — cursor will remain visible"

# Grant display and input device access (takes effect at next login)
sudo usermod -aG video,input "$USER" 2>/dev/null || true

USER_HOME=$(getent passwd "$USER" | cut -d: -f6)

# X session: wait for server, then launch Chromium full-screen.
# If Chromium exits, startx exits, getty respawns and auto-logs in again — self-recovering.
cat > "$USER_HOME/.xinitrc" << XINITRC
#!/bin/bash
xset s off s noblank -dpms
xrandr --auto
unclutter -idle 0.1 -root &>/dev/null &
openbox &
sleep 0.5

until curl -sf "$SERVER_URL" > /dev/null 2>&1; do
    sleep 5
done
pkill -9 chromium 2>/dev/null; sleep 1
exec /usr/bin/chromium \\
  --kiosk \\
  --noerrdialogs \\
  --disable-infobars \\
  --no-first-run \\
  --disable-session-crashed-bubble \\
  --disable-restore-session-state \\
  --disk-cache-size=0 \\
  --media-cache-size=0 \\
  --disable-gpu-shader-disk-cache \\
  --disable-dev-shm-usage \\
  --disable-gpu-rasterization \\
  "$SERVER_URL/kiosk.html?fps=20"
XINITRC
chmod +x "$USER_HOME/.xinitrc"

# Auto-start X when this user logs in on TTY1.
# exec replaces the shell so logout = X session exit = getty respawn = auto-login again.
if ! grep -q 'shop-kiosk' "$USER_HOME/.bash_profile" 2>/dev/null; then
    cat >> "$USER_HOME/.bash_profile" << 'PROFILE'

# shop-kiosk: start X automatically on TTY1
if [[ -z $DISPLAY && $(tty) == /dev/tty1 ]]; then
    exec startx
fi
PROFILE
fi

# Configure TTY1 to auto-login this user on boot
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER --noclear %I \$TERM
EOF
sudo systemctl daemon-reload

echo ""
echo "=== Done ==="
echo "Displaying: $SERVER_URL/kiosk.html"
echo "Reboot to start the kiosk."
echo "Check status: journalctl -u getty@tty1 -f"