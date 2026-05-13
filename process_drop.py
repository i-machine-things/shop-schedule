#!/usr/bin/env python3
"""
process_drop.py — Pick up a PDF dropped into incoming/ and regenerate the schedule.

Run manually or via cron alongside update_schedule.py:
  python3 process_drop.py
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DROP_DIR     = os.path.join(BASE_DIR, 'incoming')
PROCESSED    = os.path.join(DROP_DIR, 'processed')
PDF_PATH     = os.path.join(BASE_DIR, 'last_report.pdf')
MAIN_SCRIPT  = os.path.join(BASE_DIR, 'update_schedule.py')


def main():
    if not os.path.isdir(DROP_DIR):
        print("No incoming/ directory found.", file=sys.stderr)
        sys.exit(1)

    pdfs = [
        os.path.join(DROP_DIR, f)
        for f in os.listdir(DROP_DIR)
        if f.lower().endswith('.pdf') and os.path.isfile(os.path.join(DROP_DIR, f))
    ]

    if not pdfs:
        print("No PDFs in incoming/. Nothing to do.")
        sys.exit(0)

    newest = max(pdfs, key=os.path.getmtime)
    shutil.copy2(newest, PDF_PATH)

    os.makedirs(PROCESSED, exist_ok=True)
    for pdf in pdfs:
        fname = os.path.basename(pdf)
        dest  = os.path.join(PROCESSED, fname)
        if os.path.exists(dest):
            base, ext = os.path.splitext(fname)
            ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
            dest = os.path.join(PROCESSED, f"{base}_{ts}{ext}")
        shutil.move(pdf, dest)

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Drop-dir: picked up {os.path.basename(newest)}")

    env = {**os.environ, 'GMAIL_USER': ''}
    subprocess.run([sys.executable, MAIN_SCRIPT], env=env, check=True)


if __name__ == '__main__':
    main()
