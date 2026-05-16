#!/usr/bin/env python3
"""Generate a dummy Foreman's Report PDF for local testing.

Run:  python3 make_test_pdf.py
Output: last_report.pdf  (then run update_schedule.py to regenerate schedule.html)
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE_DIR, 'last_report.pdf')

FONT = 'Courier'
FONT_SIZE = 9
LINE_H = 11      # points between lines
W, H = letter    # 612 × 792

# ---------------------------------------------------------------------------
# Test data — intentional mix of overdue / upcoming dates (today = 16-May-26)
# Format:  (job, rev, qty, unit, pri, sch_start, wc, ship_pri, ship_qty, promised,
#           customer, oper, sch_end, num_ops, rem_hrs, qty_run,
#           part, description)
# ---------------------------------------------------------------------------
SECTIONS = [
    {
        'dept': 'CNC', 'wc_group': 'CNC Lathe', 'wc': 'LAT-001',
        'jobs': [
            # not overdue
            ('12345', 'A', '5',  'ea', '2', '01-May-26', 'LAT-001', '1', '5',  '30-May-26',
             'ACME PARTS',         '010', '15-May-26', '3', '2.5', '0',
             'P-98765', 'Shaft Assembly'),
            # overdue
            ('12346', '',  '10', 'ea', '3', '05-Apr-26', 'LAT-001', '2', '10', '01-May-26',
             'SMITH MFG',          '020', '20-Apr-26', '2', '8.0', '5',
             'P-11111', 'Bracket Weldment'),
            # not overdue, no rev
            ('12347', '',  '25', 'ea', '5', '10-May-26', 'LAT-001', '3', '25', '15-Jun-26',
             'JONES IND',          '030', '25-May-26', '4', '1.5', '10',
             'P-22222', 'Pin Retaining'),
        ],
    },
    {
        'dept': 'CNC', 'wc_group': 'CNC Mill', 'wc': 'MIL-002',
        'jobs': [
            # overdue (promised same as sch_start — clearly late)
            ('23456', 'B', '2',  'ea', '1', '10-Apr-26', 'MIL-002', '1', '2',  '10-Apr-26',
             'APEX MACHINE',       '010', '30-Apr-26', '5', '12.0', '0',
             'P-55555', 'Housing Assembly'),
            # not overdue
            ('23457', '',  '8',  'ea', '4', '12-May-26', 'MIL-002', '2', '8',  '30-Jun-26',
             'GLOBAL PARTS',       '020', '22-May-26', '3', '6.5',  '2',
             'P-66666', 'Flange Plate'),
        ],
    },
    {
        'dept': 'Assembly', 'wc_group': 'Final Assembly', 'wc': 'ASM-001',
        'jobs': [
            # not overdue
            ('34567', '',  '3',  'ea', '2', '05-May-26', 'ASM-001', '1', '3',  '25-May-26',
             'PRECISION WORKS',    '010', '20-May-26', '2', '4.0',  '0',
             'P-77777', 'Gearbox Assembly'),
            # overdue — promised yesterday
            ('34568', 'A', '1',  'ea', '1', '01-May-26', 'ASM-001', '1', '1',  '15-May-26',
             'CENTRAL MACH',       '020', '14-May-26', '3', '8.5',  '0',
             'P-88888', 'Control Panel Complete'),
        ],
    },
    {
        'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
        'jobs': [
            # not overdue
            ('45678', '',  '6',  'ea', '3', '08-May-26', 'WLD-001', '2', '6',  '28-May-26',
             'NORTHERN MET',       '010', '23-May-26', '2', '3.0',  '0',
             'P-99999', 'Frame Weldment'),
        ],
    },
]

# Page 2 — second half of Welding (tests cross-page WC merge) + Shipping
SECTIONS_P2 = [
    {
        'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
        'jobs': [
            ('45679', '',  '4',  'ea', '4', '11-May-26', 'WLD-001', '3', '4',  '05-Jun-26',
             'EASTERN FAB',        '020', '30-May-26', '3', '5.5',  '1',
             'P-44444', 'Support Bracket'),
        ],
    },
    {
        'dept': 'Shipping', 'wc_group': 'Shipping', 'wc': 'SHP-001',
        'jobs': [
            ('56789', '',  '10', 'ea', '5', '15-May-26', 'SHP-001', '1', '10', '20-May-26',
             'RAPID LOG',          '010', '18-May-26', '1', '0.5',  '8',
             'P-33333', 'Finished Goods Kit'),
        ],
    },
]


def _job_line(j):
    job, rev, qty, unit, pri, sch_start, wc, ship_pri, ship_qty, promised = j[:10]
    rev_part = f' {rev}' if rev else ''
    return f'{job}{rev_part} {qty}/{unit} {pri} {sch_start} {wc} {ship_pri} {ship_qty} {promised}'


def _cust_line(j):
    customer, oper, sch_end, num_ops, rem_hrs, qty_run = j[10:16]
    return f'{customer} {oper} {sch_end} {num_ops} {rem_hrs} {qty_run}'


def _part_line(j):
    part, description = j[16], j[17]
    return f'{part} {description}'


def write_sections(c, sections, start_y, x=40):
    y = start_y

    def line(text=''):
        nonlocal y
        if text:
            c.drawString(x, y, text)
        y -= LINE_H

    for sec in sections:
        line(f'Department {sec["dept"]}  WC Group: {sec["wc_group"]}  WC: {sec["wc"]}')
        line()
        for j in sec['jobs']:
            line(_job_line(j))
            line(_cust_line(j))
            line(_part_line(j))
            line()

    return y


def make_pdf(path):
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont(FONT, FONT_SIZE)

    # ── Page 1 ────────────────────────────────────────────────────────────────
    y = H - 40
    x = 40

    def line(text=''):
        nonlocal y
        if text:
            c.drawString(x, y, text)
        y -= LINE_H

    # Header — contains the tokens the parser's regex searches for
    line('SCHURMAN MACHINE')
    line('Foremans Report    16-May-26 08:30AM    Released Jobs Only    Thru 5/31/2026')
    line('by Work Center')
    line()
    # Column headers — all caught by _SKIP_RE so harmless
    line('Job   Rev  Make Qty  Pri  Sch Start   Curr WC   Ship Qty  Promised')
    line('Customer              Oper  Sch End   # Ops  Rem Hrs  Qty Run')
    line('Part  Description')
    line()

    y = write_sections(c, SECTIONS, y, x)

    # ── Page 2 ────────────────────────────────────────────────────────────────
    c.showPage()
    c.setFont(FONT, FONT_SIZE)

    write_sections(c, SECTIONS_P2, H - 40, x)

    c.save()
    print(f'Created: {path}')
    print(f'Jobs: {sum(len(s["jobs"]) for s in SECTIONS + SECTIONS_P2)} across '
          f'{len(SECTIONS + SECTIONS_P2)} sections (Welding split across pages to test merge)')


if __name__ == '__main__':
    make_pdf(OUTPUT)
