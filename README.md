# Shop Schedule

Raspberry Pi kiosk display for a machine shop floor. Polls a Gmail inbox every 15 minutes for the Foreman's Report PDF, parses it, and serves an auto-scrolling HTML schedule on a wall-mounted screen.

> Works off the **Foreman's Report** exported from JobBoss. The report is emailed as a PDF attachment and picked up automatically — or you can drop a PDF directly into the `incoming/` folder.

## How it works

1. `run_update.sh` is called by cron every 15 minutes
2. It loads credentials from `.env` and runs `update_schedule.py`
3. The script checks Gmail for an unread email with a PDF attachment
4. If found, the PDF is saved as `last_report.pdf` and parsed
5. `schedule.html` is regenerated and picked up live by Chromium in kiosk mode

## Requirements

- Raspberry Pi (tested on Pi 4) running Raspberry Pi OS
- Python 3 with `pdfplumber` (`pip3 install pdfplumber`)
- Chromium browser
- A Gmail account with IMAP enabled and an [App Password](https://myaccount.google.com/apppasswords)

## Setup

```bash
# Clone on the Pi
git clone https://github.com/i-machine-things/shop-schedule.git /home/pi/shop-schedule
cd /home/pi/shop-schedule

# Run the installer (installs deps, sets up cron, starts kiosk service)
bash install.sh
```

The installer will prompt you to fill in `.env` before the first run:

```dotenv
GMAIL_USER=your@gmail.com
GMAIL_PASS=xxxx-xxxx-xxxx-xxxx   # Gmail App Password
SHOP_NAME="Your Shop Name"        # Shown in the page header and browser title
```

## Remote access

Once the installer runs, the schedule is also served over HTTP on port 8080:

```text
http://<pi-ip>:8080/schedule.html
```

The page polls for updates every 60 seconds and swaps in new content without reloading. Any device on the same network can view it — useful for checking the schedule from a desk or phone without walking to the display.

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
| `run_update.sh` | Cron wrapper — loads `.env` and calls the script |
| `install.sh` | One-time Pi setup: deps, cron job, kiosk service |
| `foreman-kiosk.service` | systemd service — opens Chromium in kiosk mode |
| `foreman-server.service` | systemd service — serves `schedule.html` over HTTP on port 8080 |
| `.env.example` | Credential template (copy to `.env` and fill in) |
| `incoming/` | Drop PDFs here; run `process_drop.py` to ingest them |

## Display

The generated `schedule.html` is a full-screen dark-theme table grouped by work centre. It auto-scrolls continuously and polls for new content every 60 seconds, swapping in updates without a page reload. Overdue promised dates are highlighted in red.
