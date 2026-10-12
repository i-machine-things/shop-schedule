#!/usr/bin/env python3
"""Pull Foreman's Report data directly from the JobBoss SQL Server database.

Returns the same {report_date, thru_date, sections} shape as parse_pdf() in
update_schedule.py, so generate_html() needs no changes to consume either
source. Used instead of the Gmail/PDF pipeline when JOBBOSS_DB_* is set.

Only SELECTs the columns needed for display (no pricing/cost/margin fields)
and only ever runs read queries — pair this with a SQL login that has
SELECT-only grants on Job, Job_Operation, and Work_Center, nothing broader.
See README.md for the recommended login setup.
"""

import os
import sys
from datetime import datetime, timedelta

import pytds

DB_HOST = os.environ.get('JOBBOSS_DB_HOST', '').strip()
# Blank unless explicitly set -- a named instance (e.g. "SMI-APP02\JBSQL" in
# JOBBOSS_DB_HOST) is resolved to its real port via the SQL Browser service
# at connect time. Only set JOBBOSS_DB_PORT if that resolution isn't an
# option (e.g. the browser service/UDP 1434 is firewalled) and a DBA has
# given you the instance's static port instead.
_DB_PORT_RAW = os.environ.get('JOBBOSS_DB_PORT', '').strip()
DB_PORT = int(_DB_PORT_RAW) if _DB_PORT_RAW else None
DB_NAME = os.environ.get('JOBBOSS_DB_NAME', '').strip()
DB_USER = os.environ.get('JOBBOSS_DB_USER', '').strip()
DB_PASS = os.environ.get('JOBBOSS_DB_PASS', '')
# Optional -- path to the SQL Server's certificate (PEM/Base-64 .cer), exported
# by a DBA from SQL Server Configuration Manager. Without this, pytds leaves
# the connection unencrypted (matches the existing ODBC DSN's "Data Encryption:
# No" setting, so no new exposure vs. today's Excel/Power Query access -- but
# set this whenever a DBA can provide the cert). See README.md.
DB_CAFILE = os.environ.get('JOBBOSS_DB_CAFILE', '').strip()
DAYS_AHEAD = int(os.environ.get('JOBBOSS_DAYS_AHEAD', '').strip() or 14)

# Current operation per job = earliest non-complete Sequence. Rem_Hrs/NumOps_Ahead
# are the sum/count of everything queued ahead of *this row's* operation, not the
# job's current one -- confirmed against a real multi-page Foreman's Report where
# the same job appears once per open operation with those two values changing
# per appearance while Curr_WC stays constant. See PR description for the worked
# example (job 30180, 5 appearances, 5 matching Rem_Hrs/#Ops pairs).
_QUERY = """
SELECT
    wc.Department,
    COALESCE(wc.Parent_ID, wc.Work_Center) AS WC_Group,
    jo.Work_Center                          AS WC,
    j.Job, j.Rev, j.Customer, j.Part_Number, j.Description,
    j.Make_Quantity, j.Priority,
    jo.Operation_Service                    AS Oper,
    jo.Description                          AS Oper_Desc,
    jo.Sched_Start, jo.Sched_End,
    cur.Curr_WC,
    cur.Rem_Hrs,
    cur.NumOps_Ahead,
    jo.Act_Run_Qty                          AS Qty_Run
FROM Job_Operation jo
JOIN Job j          ON j.Job = jo.Job
JOIN Work_Center wc ON wc.Work_Center = jo.Work_Center
CROSS APPLY (
    SELECT TOP 1
        cjo.Work_Center AS Curr_WC,
        (SELECT SUM(jo2.Rem_Total_Hrs) FROM Job_Operation jo2
           WHERE jo2.Job = jo.Job AND jo2.Sequence < jo.Sequence) AS Rem_Hrs,
        (SELECT COUNT(*) FROM Job_Operation jo2
           WHERE jo2.Job = jo.Job AND jo2.Sequence < jo.Sequence AND jo2.Status <> 'C') AS NumOps_Ahead
    FROM Job_Operation cjo
    WHERE cjo.Job = jo.Job AND cjo.Status <> 'C'
    ORDER BY cjo.Sequence ASC
) cur
WHERE jo.Status <> 'C'
  AND j.Released_Date IS NOT NULL
  AND jo.Sched_Start <= %s
ORDER BY wc.Department, COALESCE(wc.Parent_ID, wc.Work_Center), jo.Work_Center, j.Job, jo.Sequence
"""

# Separate, unbounded query for work-center backlog only -- no Sched_Start
# cutoff and no per-row CROSS APPLY (don't need Rem_Hrs/NumOps_Ahead/Curr_WC
# here, just the schedule window). The main query above is intentionally
# limited to JOBBOSS_DAYS_AHEAD so the scrolling kiosk display stays
# near-term, but reusing that same limited row set for the backlog stat
# silently capped it at ~days_ahead too -- defeating the point, since sales
# needs to see real backlog depth beyond what's on screen. Cheaper than
# widening the main query's cutoff would be: no CROSS APPLY means this
# doesn't pay the correlated-subquery cost per row across a much larger date
# range on every 60s refresh.
_BACKLOG_QUERY = """
SELECT
    wc.Department,
    COALESCE(wc.Parent_ID, wc.Work_Center) AS WC_Group,
    jo.Work_Center                          AS WC,
    jo.Sched_Start, jo.Sched_End
FROM Job_Operation jo
JOIN Job j          ON j.Job = jo.Job
JOIN Work_Center wc ON wc.Work_Center = jo.Work_Center
WHERE jo.Status <> 'C'
  AND j.Released_Date IS NOT NULL
"""


def is_configured():
    """True if enough JOBBOSS_DB_* env vars are set to attempt a connection."""
    return bool(DB_HOST and DB_NAME and DB_USER)


def _fmt_date(dt):
    """Match the PDF parser's dd-Mon-yy date format, e.g. '18-Sep-26'."""
    return dt.strftime('%d-%b-%y') if dt else ''


def _parse_sched_date(s):
    """Parse a 'dd-Mon-yy' sch_start/sch_end string back to a datetime, or
    None if blank/unparseable. Lives here (not update_schedule.py) so both
    this module's wide backlog query and update_schedule.py's PDF-path fallback
    can share it without a circular import (update_schedule.py already
    imports this module, not the other way around)."""
    if not s:
        return None
    try:
        return datetime.strptime(s, '%d-%b-%y')
    except ValueError:
        return None


def _work_center_backlog_days(jobs, now):
    """Days of work queued at a work center, based on the end time of the
    last job -- but stopping at the first gap of at least a week between
    jobs, so the reported backlog reflects the nearer job instead of hiding an
    open gap behind a later one. Lets sales see where there's actually room
    to slot something in rather than reading a work center as fully booked
    out to its furthest-out job when it isn't really.

    Jobs are treated as occupying [sch_start, max(sch_end, now)] at this work
    center -- the max(..., now) matters for a job that's overdue but still
    open (sch_end already passed, Status <> 'C' per the caller's query): that
    means the work center is *behind*, not free starting at that stale date.
    Without the clamp, a real near-term job starting shortly after would read
    as a gap (idle time) right after the overdue job's stale end, when in
    reality the work center is going to spend that time catching up on the
    overdue job, not sitting idle. Jobs scheduled before today get applied to
    filling in apparent gaps, not treated as already finished and out of the
    way. Walking jobs in start order, a gap means idle time between one job's
    (clamped) end and the next job's start, not just a distance between two
    end dates.

    Returns (backlog_days, gap_days) as integer days, not fractional weeks --
    exact, so weeks-and-days display formatting doesn't compound rounding on
    top of an already-rounded decimal. gap_days is None when the queue simply
    has nothing scheduled after it (open-ended, not a bounded gap) --
    backlog_days alone says *when* there's room, not *how much*; a work
    center reading "2 wk backlog" could have a 1-week hole right after that
    point or a 4-week one, and only one of those actually fits a 2-week job.
    """
    intervals = []
    for j in jobs:
        start = _parse_sched_date(j.get('sch_start'))
        end = _parse_sched_date(j.get('sch_end'))
        if start and end:
            intervals.append((start, max(end, now)))
    if not intervals:
        return 0, None
    intervals.sort(key=lambda t: t[0])

    queue_end = None
    gap_days = None
    for start, end in intervals:
        if queue_end is not None and (start - queue_end) >= timedelta(weeks=1):
            gap_days = (start - queue_end).days
            break
        if queue_end is None or end > queue_end:
            queue_end = end

    if queue_end is None:
        return 0, None
    return max(0, (queue_end - now).days), gap_days


def fetch_from_db():
    """Query JobBoss directly; return {report_date, thru_date, sections}, or None on failure."""
    cutoff = datetime.now() + timedelta(days=DAYS_AHEAD)
    # Only pass port= when explicitly configured -- otherwise let pytds resolve
    # a named instance (e.g. "SMI-APP02\JBSQL") via the SQL Browser service,
    # same as the ODBC driver does for Excel/Power Query against this server.
    # pytds raises ValueError if both an instance suffix and an explicit port
    # are given ("Both instance and port shouldn't be specified"), so a static
    # port means connecting to the bare host instead.
    dsn = DB_HOST
    connect_kwargs = {
        'database': DB_NAME, 'user': DB_USER, 'password': DB_PASS,
        'timeout': 15, 'as_dict': True,
    }
    if DB_PORT is not None:
        dsn = DB_HOST.split('\\', 1)[0]
        connect_kwargs['port'] = DB_PORT
    if DB_CAFILE:
        connect_kwargs['cafile'] = DB_CAFILE
    try:
        with pytds.connect(dsn, **connect_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(_QUERY, (cutoff,))
                rows = cur.fetchall()
                cur.execute(_BACKLOG_QUERY)
                backlog_rows = cur.fetchall()
    except Exception as exc:
        # Log only the exception type, not str(exc) -- TDS driver error text can
        # echo back connection parameters, and this is the one error path in the
        # app where that text could end up in a log file instead of just stderr.
        print(f"DB connection failed ({type(exc).__name__}); check JOBBOSS_DB_* in .env",
              file=sys.stderr)
        return None

    sections = {}
    for r in rows:
        key = (r['Department'] or '', r['WC_Group'] or '', r['WC'] or '')
        sec = sections.setdefault(key, {
            'department': key[0], 'wc_group': key[1], 'wc': key[2], 'jobs': [],
        })
        sec['jobs'].append({
            'job': r['Job'] or '',
            'rev': r['Rev'] or '',
            'make_qty': str(r['Make_Quantity']) if r['Make_Quantity'] is not None else '',
            'pri': str(r['Priority']) if r['Priority'] is not None else '',
            'sch_start': _fmt_date(r['Sched_Start']),
            'curr_wc': r['Curr_WC'] or '',
            # Not yet sourced from the DB -- see CODING_NOTES.md. Report still
            # renders fine with these blank (overdue highlighting just no-ops).
            'ship_qty': '',
            'promised': '',
            'customer': r['Customer'] or '',
            'oper': r['Oper'] or '',
            'oper_desc': r['Oper_Desc'] or '',
            'sch_end': _fmt_date(r['Sched_End']),
            'num_ops': str(r['NumOps_Ahead']) if r['NumOps_Ahead'] is not None else '',
            'rem_hrs': f"{r['Rem_Hrs']:.2f}" if r['Rem_Hrs'] is not None else '0.00',
            'qty_run': str(r['Qty_Run']) if r['Qty_Run'] is not None else '',
            'part': r['Part_Number'] or '',
            'description': r['Description'] or '',
        })

    # Group the unbounded backlog-query rows by the same (department,
    # wc_group, wc) key as sections above, and compute backlog_days/
    # gap_days from that full set -- not from sec['jobs'], which is
    # intentionally truncated to JOBBOSS_DAYS_AHEAD for display.
    backlog_jobs_by_wc = {}
    for r in backlog_rows:
        key = (r['Department'] or '', r['WC_Group'] or '', r['WC'] or '')
        backlog_jobs_by_wc.setdefault(key, []).append({
            'sch_start': _fmt_date(r['Sched_Start']),
            'sch_end': _fmt_date(r['Sched_End']),
        })

    now = datetime.now()
    for key, sec in sections.items():
        backlog_days, gap_days = _work_center_backlog_days(backlog_jobs_by_wc.get(key, []), now)
        sec['backlog_days'] = backlog_days
        sec['gap_days'] = gap_days

    return {
        'report_date': datetime.now().strftime('%d-%b-%y %I:%M%p'),
        'thru_date': cutoff.strftime('%m/%d/%Y'),
        'sections': list(sections.values()),
    }
