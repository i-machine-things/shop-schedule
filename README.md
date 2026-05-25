# Shop Schedule

Single Board Computer kiosk display for a machine shop floor. Polls a Gmail inbox every 15 minutes for the Foreman's Report PDF, parses it, and serves an auto-scrolling HTML schedule on a wall-mounted screen.

> Works off the **Foreman's Report** exported from JobBoss. The report is emailed as a PDF attachment and picked up automatically — or you can drop a PDF directly into the `incoming/` folder.

## Screenshots

| Landing page | Options | Schedule |
|---|---|---|
| ![Landing page — live clock and navigation](screenshots/index.png) | ![Options page — rotation config, upload, and department colors](screenshots/options.png) | ![Schedule — dark-theme table grouped by work centre](screenshots/schedule.png) |

## How it works

1. `run_update.sh` is called by cron every 15 minutes
2. It loads credentials from `.env` and runs `update_schedule.py`
3. The script checks Gmail for an unread email with a PDF attachment
4. If found, the PDF is saved as `last_report.pdf` and parsed
5. `schedule.html` is regenerated and picked up live by Chromium in kiosk mode

## Requirements

- Single Board Computer (tested on BananaPi M4 zero) running Armbian v26.2.1
- Python 3 with `pdfplumber` (`pip3 install pdfplumber`)
- Chromium browser
- A Gmail account with IMAP enabled and an [App Password](https://myaccount.google.com/apppasswords)

## Setup

```bash
# Clone on the Pi
git clone https://github.com/i-machine-things/shop-schedule.git ~/shop-schedule
cd ~/shop-schedule

# Run the installer (installs deps, sets up cron, starts kiosk service)
bash install.sh
```

The installer creates `.env` from the example — edit it with your credentials before the first run:

```dotenv
GMAIL_USER=your@gmail.com
GMAIL_PASS=xxxx-xxxx-xxxx-xxxx   # Gmail App Password
SHOP_NAME="Your Shop Name"        # Shown in the page header and browser title
```

## Remote access

Once the installer runs, the kiosk and schedule are served over HTTP on port 8080:

```text
http://<pi-ip>:8080/              ← landing page
http://<pi-ip>:8080/kiosk.html    ← kiosk display with page rotation
http://<pi-ip>:8080/schedule.html ← raw schedule table (no rotation)
http://<pi-ip>:8080/options.html  ← rotation config, uploads, and department colors
```

The schedule polls for updates every 60 seconds and swaps in new content without reloading.

## Client kiosks

Any number of display-only screens can be set up as clients pointing at the server. On a fresh Armbian/Debian machine on the same network:

```bash
curl http://<server-ip>:8080/install | bash
```

Or navigate to `http://<server-ip>:8080/install.html` for a copyable one-liner with management commands. The script installs a minimal X11 + Chromium session and a systemd service (`shop-kiosk.service`) that polls the server on boot until it is reachable before opening the browser — so the display recovers automatically after power outages regardless of which device boots first.

> **Note:** `curl | bash` over plain HTTP is only safe on a trusted local network. To verify the script before running it, download it first (`curl -O http://<server-ip>:8080/install`), inspect it, then execute it manually.

## Uploading files

Navigate to `http://<pi-ip>:8080/options.html` from any device on the same network (Upload section).

- **Foreman's Report** — drop the PDF exported from JobBoss. The schedule regenerates automatically within a few seconds (same as dropping it in `incoming/`).
- **Display PDFs** — drop any PDF to add it to the kiosk rotation. It appears immediately in the list and will show as a slide the next time the kiosk loops. Remove it from the list to delete it from the rotation.

Uploaded display PDFs are stored in `public/raw/` and their entries are managed automatically in `public/pages.json`.

## SMB file drop (Windows / Mac)

The installer sets up a password-protected Samba share pointing at `incoming/`. From any machine on the same network:

- **Windows:** `\\<device-ip>\schedule-drop` — map as a network drive if desired
- **Mac:** `smb://<device-ip>/schedule-drop` in Finder → Go → Connect to Server

Log in with the device username and the SMB password set during `install.sh`. Drop a PDF and the schedule regenerates within seconds.

## Work center filter

The schedule page has a fixed sidebar listing every work center in the current report. Tapping a WC solos it (first tap); subsequent taps toggle additional WCs in or out. Tapping the sole active WC resets to showing all. The **All** button at the top also resets to the full view.

## Page rotation

The kiosk can rotate through additional web pages between schedule views. After the schedule has scrolled a configurable number of times, it fades to the next page, holds it, then fades back.

Edit `public/pages.json` on the Pi to configure:

```json
{
  "scroll_cycles": 2,
  "page_duration": 60,
  "transition_ms": 800,
  "after_page": "schedule",
  "pages": [
    "https://example.com/safety-notice",
    { "url": "https://example.com/dashboard", "duration": 30 }
  ]
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `scroll_cycles` | `2` | Full scrolls through the schedule before switching |
| `page_duration` | `60` | Seconds to show each page (overridable per page) |
| `transition_ms` | `800` | Crossfade duration in milliseconds |
| `after_page` | `"schedule"` | `"schedule"` — return to schedule after each page, cycling through the list one at a time; `"next"` — play all pages in sequence before returning |

The schedule scroll is paused while a page is displayed and resumes from the same position on return. Leave `pages` as an empty array to disable rotation.

## Manual test

```bash
# Regenerate schedule.html from the existing last_report.pdf (skips email):
GMAIL_USER='' python3 update_schedule.py

# Or drop a PDF into incoming/ and let process_drop.py handle it:
cp /path/to/report.pdf incoming/
python3 process_drop.py
```

`process_drop.py` picks the newest PDF in `incoming/`, copies it to `last_report.pdf`, moves all processed files to `incoming/processed/`, then calls `update_schedule.py` to regenerate the HTML.

## Files

| File | Purpose |
|------|---------|
| `update_schedule.py` | Email fetch, PDF parse, HTML generation |
| `process_drop.py` | Drop-dir handler — picks up PDFs from `incoming/` and regenerates the schedule |
| `server.py` | HTTP server — serves `public/` and handles file-upload API (`/api/upload/*`, `/api/raw/*`) |
| `run_update.sh` | Cron wrapper — loads `.env` and calls the script |
| `install.sh` | One-time server setup: deps, cron job, kiosk and HTTP server services |
| `install-client.sh` | Client kiosk installer — served pre-filled via `GET /install`; creates `shop-kiosk.service` on the client |
| `foreman-kiosk.service` | systemd service (server) — opens Chromium in kiosk mode pointing at `kiosk.html` |
| `foreman-server.service` | systemd service — runs `server.py` on port 8080 |
| `public/install.html` | Web UI showing the copyable client install one-liner |
| `public/options.html` | Admin UI — page rotation config, uploads, and department color pickers |
| `public/kiosk.html` | Rotation shell — wraps the schedule and fades to configured pages |
| `pages.json.example` | Template for `public/pages.json` (the page rotation config) |
| `.env.example` | Credential template (copy to `.env` and fill in) |
| `incoming/` | Drop PDFs here; run `process_drop.py` to ingest them |
| `public/raw/` | Display PDFs uploaded via the web UI (gitignored) |

## Display

The generated `schedule.html` is a full-screen dark-theme table grouped by work centre. It auto-scrolls continuously and polls for new content every 60 seconds, swapping in updates without a page reload. Overdue promised dates are highlighted in red.
