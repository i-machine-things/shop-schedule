#!/usr/bin/env python3
"""Generate a dummy Foreman's Report PDF for local testing.

Run:  python3 make_test_pdf.py
Output: last_report.pdf  (then run update_schedule.py to regenerate schedule.html)
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import date, timedelta
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE_DIR, 'last_report.pdf')

FONT = 'Courier'
FONT_SIZE = 9
LINE_H = 11      # points between lines
W, H = letter    # 612 × 792

ANCHOR = date.today()


def _d(offset):
    """Return ANCHOR + offset days formatted as dd-Mon-yy (the PDF date format)."""
    return (ANCHOR + timedelta(days=offset)).strftime('%d-%b-%y')


def _thru():
    """Thru date six weeks out, formatted as m/d/yyyy."""
    d = ANCHOR + timedelta(days=42)
    return f'{d.month}/{d.day}/{d.year}'


# ---------------------------------------------------------------------------
# Test data — intentional mix of overdue / upcoming dates relative to ANCHOR.
# Format:  (job, rev, qty, unit, pri, sch_start, wc, ship_pri, ship_qty, promised,
#           customer, oper, sch_end, num_ops, rem_hrs, qty_run,
#           part, description)
# Overdue jobs: 12346 (promised ANCHOR-15), 23456 (ANCHOR-36), 34568 (ANCHOR-1)
# ---------------------------------------------------------------------------
SECTIONS = [
    {
        'dept': 'CNC', 'wc_group': 'CNC Lathe', 'wc': 'LAT-001',
        'jobs': [
            # not overdue
            ('12345', 'A', '5',  'ea', '2', _d(-15), 'LAT-001', '1', '5',  _d(+14),
             'ACME PARTS',         '010', _d(-1),  '3', '2.5', '0',
             'P-98765', 'Shaft Assembly'),
            # overdue
            ('12346', '',  '10', 'ea', '3', _d(-41), 'LAT-001', '2', '10', _d(-15),
             'SMITH MFG',          '020', _d(-26), '2', '8.0', '5',
             'P-11111', 'Bracket Weldment'),
            # not overdue, no rev
            ('12347', '',  '25', 'ea', '5', _d(-6),  'LAT-001', '3', '25', _d(+30),
             'JONES IND',          '030', _d(+9),  '4', '1.5', '10',
             'P-22222', 'Pin Retaining'),
        ],
    },
    {
        'dept': 'CNC', 'wc_group': 'CNC Mill', 'wc': 'MIL-002',
        'jobs': [
            # overdue (promised same as sch_start — clearly late)
            ('23456', 'B', '2',  'ea', '1', _d(-36), 'MIL-002', '1', '2',  _d(-36),
             'APEX MACHINE',       '010', _d(-16), '5', '12.0', '0',
             'P-55555', 'Housing Assembly'),
            # not overdue
            ('23457', '',  '8',  'ea', '4', _d(-4),  'MIL-002', '2', '8',  _d(+45),
             'GLOBAL PARTS',       '020', _d(+6),  '3', '6.5',  '2',
             'P-66666', 'Flange Plate'),
        ],
    },
    {
        'dept': 'Assembly', 'wc_group': 'Final Assembly', 'wc': 'ASM-001',
        'jobs': [
            # not overdue
            ('34567', '',  '3',  'ea', '2', _d(-11), 'ASM-001', '1', '3',  _d(+9),
             'PRECISION WORKS',    '010', _d(+4),  '2', '4.0',  '0',
             'P-77777', 'Gearbox Assembly'),
            # overdue — promised yesterday
            ('34568', 'A', '1',  'ea', '1', _d(-15), 'ASM-001', '1', '1',  _d(-1),
             'CENTRAL MACH',       '020', _d(-2),  '3', '8.5',  '0',
             'P-88888', 'Control Panel Complete'),
        ],
    },
    {
        'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
        'jobs': [
            # not overdue
            ('45678', '',  '6',  'ea', '3', _d(-8),  'WLD-001', '2', '6',  _d(+12),
             'NORTHERN MET',       '010', _d(+7),  '2', '3.0',  '0',
             'P-99999', 'Frame Weldment'),
        ],
    },
]

# Page 2 — second half of Welding (tests cross-page WC merge) + Shipping
SECTIONS_P2 = [
    {
        'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
        'jobs': [
            ('45679', '',  '4',  'ea', '4', _d(-5),  'WLD-001', '3', '4',  _d(+20),
             'EASTERN FAB',        '020', _d(+14), '3', '5.5',  '1',
             'P-44444', 'Support Bracket'),
        ],
    },
    {
        'dept': 'Shipping', 'wc_group': 'Shipping', 'wc': 'SHP-001',
        'jobs': [
            ('56789', '',  '10', 'ea', '5', _d(0),   'SHP-001', '1', '10', _d(+4),
             'RAPID LOG',          '010', _d(+2),  '1', '0.5',  '8',
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

    report_date = ANCHOR.strftime('%d-%b-%y') + ' 08:30AM'

    # Header — contains the tokens the parser's regex searches for
    line('SCHURMAN MACHINE')
    line(f'Foremans Report    {report_date}    Released Jobs Only    Thru {_thru()}')
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
