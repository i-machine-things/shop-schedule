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
            ('12345', 'A', '5', 'ea', '2', _d(-15), 'LAT-001', '1', '5', _d(+14),
             'ACME PARTS', '010', _d(-1), '3', '2.5', '0',
             'P-98765', 'Shaft Assembly'),
            # overdue
            ('12346', '', '10', 'ea', '3', _d(-41), 'LAT-001', '2', '10', _d(-15),
             'SMITH MFG', '020', _d(-26), '2', '8.0', '5',
             'P-11111', 'Bracket Weldment'),
            # not overdue, no rev
            ('12347', '', '25', 'ea', '5', _d(-6), 'LAT-001', '3', '25', _d(+30),
             'JONES IND', '030', _d(+9), '4', '1.5', '10',
             'P-22222', 'Pin Retaining'),
        ],
    },
    {
        'dept': 'CNC', 'wc_group': 'CNC Mill', 'wc': 'MIL-002',
        'jobs': [
            # overdue (promised same as sch_start — clearly late)
            ('23456', 'B', '2', 'ea', '1', _d(-36), 'MIL-002', '1', '2', _d(-36),
             'APEX MACHINE', '010', _d(-16), '5', '12.0', '0',
             'P-55555', 'Housing Assembly'),
            # not overdue
            ('23457', '', '8', 'ea', '4', _d(-4), 'MIL-002', '2', '8', _d(+45),
             'GLOBAL PARTS', '020', _d(+6), '3', '6.5', '2',
             'P-66666', 'Flange Plate'),
        ],
    },
    {
        'dept': 'Assembly', 'wc_group': 'Final Assembly', 'wc': 'ASM-001',
        'jobs': [
            # not overdue
            ('34567', '', '3', 'ea', '2', _d(-11), 'ASM-001', '1', '3', _d(+9),
             'PRECISION WORKS', '010', _d(+4), '2', '4.0', '0',
             'P-77777', 'Gearbox Assembly'),
            # overdue — promised yesterday
            ('34568', 'A', '1', 'ea', '1', _d(-15), 'ASM-001', '1', '1', _d(-1),
             'CENTRAL MACH', '020', _d(-2), '3', '8.5', '0',
             'P-88888', 'Control Panel Complete'),
        ],
    },
    {
        'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
        'jobs': [
            # not overdue
            ('45678', '', '6', 'ea', '3', _d(-8), 'WLD-001', '2', '6', _d(+12),
             'NORTHERN MET', '010', _d(+7), '2', '3.0', '0',
             'P-99999', 'Frame Weldment'),
        ],
    },
]

# Page 2 — second half of Welding (tests cross-page WC merge) + Shipping
SECTIONS_P2 = [
    {
        'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
        'jobs': [
            ('45679', '', '4', 'ea', '4', _d(-5), 'WLD-001', '3', '4', _d(+20),
             'EASTERN FAB', '020', _d(+14), '3', '5.5', '1',
             'P-44444', 'Support Bracket'),
        ],
    },
    {
        'dept': 'Shipping', 'wc_group': 'Shipping', 'wc': 'SHP-001',
        'jobs': [
            ('56789', '', '10', 'ea', '5', _d(0), 'SHP-001', '1', '10', _d(+4),
             'RAPID LOG', '010', _d(+2), '1', '0.5', '8',
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


# ---------------------------------------------------------------------------
# Variants — clearly different content so refreshes are visually obvious.
# ---------------------------------------------------------------------------

VARIANTS = {
    1: {
        'label': 'REPORT-ALPHA',
        'sections': [
            {
                'dept': 'CNC', 'wc_group': 'CNC Lathe', 'wc': 'LAT-001',
                'jobs': [
                    ('10001', 'A', '5', 'ea', '1', _d(-5), 'LAT-001', '1', '5', _d(+10),
                     'ALPHA PARTS', '010', _d(+5), '2', '3.0', '0', 'AP-001', 'Alpha Shaft'),
                    ('10002', '', '12', 'ea', '2', _d(-10), 'LAT-001', '2', '12', _d(+5),
                     'ALPHA MFG', '020', _d(+2), '3', '6.0', '4', 'AP-002', 'Alpha Bracket'),
                ],
            },
            {
                'dept': 'Welding', 'wc_group': 'MIG Weld', 'wc': 'WLD-001',
                'jobs': [
                    ('10003', '', '8', 'ea', '3', _d(-3), 'WLD-001', '1', '8', _d(+15),
                     'ALPHA WELD', '010', _d(+12), '2', '2.5', '0', 'AW-001', 'Alpha Frame'),
                ],
            },
        ],
    },
    2: {
        'label': 'REPORT-BRAVO',
        'sections': [
            {
                'dept': 'CNC', 'wc_group': 'CNC Mill', 'wc': 'MIL-002',
                'jobs': [
                    ('20001', 'B', '3', 'ea', '1', _d(-20), 'MIL-002', '1', '3', _d(-5),
                     'BRAVO MACHINE', '010', _d(-10), '4', '10.0', '1', 'BM-001', 'Bravo Housing'),
                    ('20002', '', '6', 'ea', '2', _d(-7), 'MIL-002', '2', '6', _d(+8),
                     'BRAVO PARTS', '020', _d(+3), '3', '4.5', '2', 'BM-002', 'Bravo Flange'),
                    ('20003', 'A', '15', 'ea', '3', _d(-2), 'MIL-002', '3', '15', _d(+20),
                     'BRAVO IND', '030', _d(+18), '2', '1.0', '0', 'BM-003', 'Bravo Pin'),
                ],
            },
            {
                'dept': 'Assembly', 'wc_group': 'Final Assembly', 'wc': 'ASM-001',
                'jobs': [
                    ('20004', '', '2', 'ea', '1', _d(-14), 'ASM-001', '1', '2', _d(-2),
                     'BRAVO WORKS', '010', _d(-5), '3', '7.0', '0', 'BA-001', 'Bravo Gearbox'),
                    ('20005', '', '4', 'ea', '2', _d(-9), 'ASM-001', '2', '4', _d(+6),
                     'BRAVO CTRL', '020', _d(+2), '2', '3.5', '1', 'BA-002', 'Bravo Panel'),
                ],
            },
            {
                'dept': 'Shipping', 'wc_group': 'Shipping', 'wc': 'SHP-001',
                'jobs': [
                    ('20006', '', '20', 'ea', '5', _d(0), 'SHP-001', '1', '20', _d(+3),
                     'BRAVO LOG', '010', _d(+2), '1', '0.5', '15', 'BS-001', 'Bravo Kit'),
                ],
            },
        ],
    },
    3: {
        'label': 'REPORT-CHARLIE',
        'sections': [
            {
                'dept': 'CNC', 'wc_group': 'CNC Lathe', 'wc': 'LAT-001',
                'jobs': [
                    ('30001', '', '7', 'ea', '2', _d(-6), 'LAT-001', '1', '7', _d(+12),
                     'CHARLIE CO', '010', _d(+8), '2', '2.0', '3', 'CC-001', 'Charlie Shaft'),
                ],
            },
            {
                'dept': 'CNC', 'wc_group': 'CNC Mill', 'wc': 'MIL-002',
                'jobs': [
                    ('30002', 'C', '4', 'ea', '1', _d(-30), 'MIL-002', '1', '4', _d(-10),
                     'CHARLIE MACH', '010', _d(-15), '5', '14.0', '0', 'CM-001', 'Charlie Housing'),
                ],
            },
            {
                'dept': 'Welding', 'wc_group': 'TIG Weld', 'wc': 'WLD-002',
                'jobs': [
                    ('30003', '', '10', 'ea', '3', _d(-4), 'WLD-002', '2', '10', _d(+18),
                     'CHARLIE FAB', '010', _d(+14), '3', '4.0', '2', 'CW-001', 'Charlie Frame'),
                    ('30004', 'A', '2', 'ea', '2', _d(-18), 'WLD-002', '1', '2', _d(-3),
                     'CHARLIE STL', '020', _d(-8), '2', '9.5', '0', 'CW-002', 'Charlie Bracket'),
                ],
            },
            {
                'dept': 'Assembly', 'wc_group': 'Sub Assembly', 'wc': 'ASM-002',
                'jobs': [
                    ('30005', '', '1', 'ea', '1', _d(-22), 'ASM-002', '1', '1', _d(-7),
                     'CHARLIE CTRL', '010', _d(-12), '4', '16.0', '0', 'CA-001', 'Charlie Control Box'),
                ],
            },
        ],
    },
}


def make_pdf(path, variant=None):
    """Generate a test PDF. variant=None uses the original SECTIONS data."""
    if variant is not None:
        v = VARIANTS[variant]
        sections_p1 = v['sections']
        sections_p2 = []
        label = v['label']
    else:
        sections_p1 = SECTIONS
        sections_p2 = SECTIONS_P2
        label = 'ORIGINAL'

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

    line('SCHURMAN MACHINE')
    line(f'Foremans Report    {report_date}    Released Jobs Only    Thru {_thru()}')
    line(f'by Work Center                                              [{label}]')
    line()
    line('Job   Rev  Make Qty  Pri  Sch Start   Curr WC   Ship Qty  Promised')
    line('Customer              Oper  Sch End   # Ops  Rem Hrs  Qty Run')
    line('Part  Description')
    line()

    y = write_sections(c, sections_p1, y, x)

    if sections_p2:
        c.showPage()
        c.setFont(FONT, FONT_SIZE)
        write_sections(c, sections_p2, H - 40, x)

    c.save()
    all_secs = sections_p1 + sections_p2
    print(f'Created: {path}  [{label}]  '
          f'{sum(len(s["jobs"]) for s in all_secs)} jobs / {len(all_secs)} sections')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate test Foreman Report PDFs')
    parser.add_argument('--variant', type=int, choices=[1, 2, 3],
                        help='Generate a specific variant (1=Alpha, 2=Bravo, 3=Charlie)')
    parser.add_argument('--all', action='store_true', help='Generate all 3 variants')
    args = parser.parse_args()

    if args.all:
        names = {1: 'test_report_alpha.pdf', 2: 'test_report_bravo.pdf', 3: 'test_report_charlie.pdf'}
        for n, fname in names.items():
            make_pdf(os.path.join(BASE_DIR, fname), variant=n)
    elif args.variant:
        names = {1: 'test_report_alpha.pdf', 2: 'test_report_bravo.pdf', 3: 'test_report_charlie.pdf'}
        make_pdf(os.path.join(BASE_DIR, names[args.variant]), variant=args.variant)
    else:
        make_pdf(OUTPUT)
