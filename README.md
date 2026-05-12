# Foreman Schedule

Raspberry Pi kiosk display for a machine shop floor. Polls a Gmail inbox every 15 minutes for the Foreman's Report PDF, parses it, and serves an auto-scrolling HTML schedule on a wall-mounted screen.

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
git clone https://github.com/YOUR_ORG/foreman-schedule.git /home/pi/foreman-schedule
cd /home/pi/foreman-schedule

# Run the installer (installs deps, sets up cron, starts kiosk service)
bash install.sh
```

The installer will prompt you to fill in `.env` with your Gmail credentials before the first run:

```
GMAIL_USER=your@gmail.com
GMAIL_PASS=xxxx-xxxx-xxxx-xxxx   # Gmail App Password
```

## Manual test

```bash
# Place a Foreman's Report PDF in the project directory as last_report.pdf, then:
GMAIL_USER='' python3 update_schedule.py
# Opens schedule.html from the existing PDF without checking email
```

## Files

| File | Purpose |
|------|---------|
| `update_schedule.py` | Email fetch, PDF parse, HTML generation |
| `run_update.sh` | Cron wrapper — loads `.env` and calls the script |
| `install.sh` | One-time Pi setup: deps, cron job, kiosk service |
| `foreman-kiosk.service` | systemd service — opens Chromium in kiosk mode |
| `.env.example` | Credential template (copy to `.env` and fill in) |

## Display

The generated `schedule.html` is a full-screen dark-theme table grouped by work centre. It auto-scrolls continuously and refreshes every 30 minutes via a `<meta http-equiv="refresh">` tag. Overdue promised dates are highlighted in red.
