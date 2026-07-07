#!/usr/bin/env python3
"""
process_drop.py — Pick up a PDF dropped into incoming/ and regenerate the schedule.

Usage:
  python3 process_drop.py            # stage PDF + regenerate schedule (web upload path)
  python3 process_drop.py --no-regen # stage PDF only; caller handles regeneration (cron path)
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DROP_DIR = os.path.join(BASE_DIR, 'incoming')
PROCESSED = os.path.join(BASE_DIR, 'processed')   # outside incoming/ — not visible in SMB share
_PDF_FILENAME = os.path.basename(os.environ.get('PDF_FILENAME', '').strip()) or 'last_report.pdf'
PDF_PATH = os.path.join(BASE_DIR, _PDF_FILENAME)
MAIN_SCRIPT = os.path.join(BASE_DIR, 'update_schedule.py')


def _cleanup_junk():
    """Remove non-PDF files and any subdirectories from incoming/."""
    for name in os.listdir(DROP_DIR):
        path = os.path.join(DROP_DIR, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif not name.lower().endswith('.pdf'):
            try:
                os.remove(path)
            except OSError:
                pass


def main(regen=True):
    """Move the newest PDF from incoming/ to PDF_PATH and optionally regenerate the schedule."""
    if not os.path.isdir(DROP_DIR):
        print("No incoming/ directory found.", file=sys.stderr)
        sys.exit(1)

    _cleanup_junk()

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
        dest = os.path.join(PROCESSED, fname)
        if os.path.exists(dest):
            base, ext = os.path.splitext(fname)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            dest = os.path.join(PROCESSED, f"{base}_{ts}{ext}")
        shutil.move(pdf, dest)

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Drop-dir: picked up {os.path.basename(newest)}")

    if regen:
        env = {**os.environ, 'GMAIL_USER': ''}
        subprocess.run([sys.executable, MAIN_SCRIPT], env=env, check=True)


if __name__ == '__main__':
    main(regen='--no-regen' not in sys.argv)
