#!/usr/bin/env python3
"""Check GitHub for the latest tagged release and update this install's git
checkout if a newer tag exists, then restart the HTTP server service so new
Python code takes effect.

update_schedule.py needs no restart -- the 15-minute cron/Task Scheduler
cycle re-invokes it fresh every time, so it always runs whatever code is on
disk at that moment. Only server.py's long-running process needs one.

Run via a separate daily cron entry (Linux) / Scheduled Task (Windows) --
install.sh/install.ps1 set this up. Deliberately not tied to the 15-minute
schedule-data refresh: a code update is not time-sensitive the way schedule
data is, and GitHub's unauthenticated REST API is rate-limited per IP.

Tracks the latest tagged GitHub Release only (never master HEAD directly) --
an install only updates itself to a version someone deliberately cut and
reviewed. Fails safe throughout: any error (network, git, permissions) is
logged to auto_update.log and the install is left exactly as it was, never
on a half-updated checkout.
"""

import json
import logging
import os
import subprocess  # nosec B404 -- fixed argv lists below, no shell=True, no user input
import sys
import urllib.request

REPO = "i-machine-things/shop-schedule"
INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(INSTALL_DIR, 'auto_update.log')

logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


def _run(cmd):
    """A subprocess wrapper for commands with no shell involvement and no
    user-controlled input -- every argv list below is a fixed, literal
    command. Raises CalledProcessError (with stdout/stderr captured) on
    a non-zero exit so callers can log it and bail out safely.
    """
    return subprocess.run(  # nosec B603 -- see docstring
        cmd, cwd=INSTALL_DIR, check=True, capture_output=True, text=True,
    )


def latest_release_tag():
    """The newest non-draft, non-prerelease tag (e.g. "v1.4.0"), straight
    from GitHub's REST API -- never master HEAD, so an install only ever
    updates itself to a version someone deliberately tagged and released.
    """
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'shop-schedule-auto-update',
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 -- fixed https:// URL above
        data = json.load(resp)
    return data['tag_name']


def current_tag():
    """The tag HEAD currently sits on, or None if it isn't exactly at one
    (e.g. a fresh clone of master, never yet updated to a tagged release --
    any available tag is treated as newer in that case).
    """
    try:
        return _run(['git', 'describe', '--tags', '--exact-match', 'HEAD']).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def restart_server():
    """Restart the long-running HTTP server process so it picks up the new
    code. Both platforms' install already run this (and the schedule
    updater) with the privilege this needs -- systemd via a narrow,
    install.sh-provisioned sudoers rule limited to exactly this one
    command; Task Scheduler because install.ps1 registers ShopScheduleServer
    to run as SYSTEM, so a same-box script can freely stop/start it.
    """
    if sys.platform == 'win32':
        _run([
            'powershell.exe', '-NoProfile', '-Command',
            'Stop-ScheduledTask -TaskName ShopScheduleServer; '
            'Start-ScheduledTask -TaskName ShopScheduleServer',
        ])
    else:
        _run(['sudo', 'systemctl', 'restart', 'foreman-server'])


def main():
    try:
        latest = latest_release_tag()
    except Exception as exc:
        logging.error("Could not check latest release: %s", exc)
        return

    current = current_tag()
    if current == latest:
        logging.info("Already on latest (%s).", latest)
        return

    logging.info("Updating %s -> %s", current or '(untagged)', latest)
    try:
        _run(['git', 'fetch', '--tags', 'origin'])
        _run(['git', 'checkout', latest])
    except subprocess.CalledProcessError as exc:
        logging.error(
            "git update to %s failed, leaving existing checkout in place: %s\n%s",
            latest, exc, exc.stderr,
        )
        return

    try:
        restart_server()
    except subprocess.CalledProcessError as exc:
        logging.error(
            "Updated checkout to %s but server restart failed -- restart it "
            "manually: %s\n%s", latest, exc, exc.stderr,
        )
        return

    logging.info("Updated to %s and restarted the server successfully.", latest)


if __name__ == '__main__':
    main()
