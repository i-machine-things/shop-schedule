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
# A 'dpapi:<base64>' prefix means this was encrypted by protect-db-password.ps1
# (Windows DPAPI, see that script) -- resolved lazily in _resolve_db_pass(),
# not here at import time, so a leftover Windows-encrypted value can't break
# module import -- or a Gmail-path run that doesn't even touch the DB -- on
# a platform that can't decrypt it.
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


def is_configured():
    """True if enough JOBBOSS_DB_* env vars are set to attempt a connection."""
    return bool(DB_HOST and DB_NAME and DB_USER)


def _resolve_db_pass():
    """Decrypt DB_PASS if protect-db-password.ps1 DPAPI-encrypted it, else
    return it unchanged. Only decryptable on the Windows machine that
    encrypted it (DPAPI, LocalMachine-scoped) -- raises clearly instead of
    pytds producing a confusing auth failure on the literal 'dpapi:...' blob.
    """
    if not DB_PASS.startswith('dpapi:'):
        return DB_PASS
    if not sys.platform.startswith('win'):
        raise RuntimeError(
            "JOBBOSS_DB_PASS is DPAPI-encrypted, which only decrypts on the "
            "Windows machine it was encrypted on (see protect-db-password.ps1).")
    import base64
    import win32crypt  # Windows-only (pywin32) -- import lazily, not installed on Linux.
    blob = base64.b64decode(DB_PASS[len('dpapi:'):])
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode('utf-8')


def _fmt_date(dt):
    """Match the PDF parser's dd-Mon-yy date format, e.g. '18-Sep-26'."""
    return dt.strftime('%d-%b-%y') if dt else ''


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
    if DB_PORT is not None:
        dsn = DB_HOST.split('\\', 1)[0]
    try:
        # Password resolution (DPAPI decrypt, if applicable) happens inside
        # this try too -- a decryption failure is a connection failure from
        # the caller's point of view, and should be reported the same way.
        connect_kwargs = {
            'database': DB_NAME, 'user': DB_USER, 'password': _resolve_db_pass(),
            'timeout': 15, 'as_dict': True,
        }
        if DB_PORT is not None:
            connect_kwargs['port'] = DB_PORT
        if DB_CAFILE:
            connect_kwargs['cafile'] = DB_CAFILE
        with pytds.connect(dsn, **connect_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(_QUERY, (cutoff,))
                rows = cur.fetchall()
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
            'sch_end': _fmt_date(r['Sched_End']),
            'num_ops': str(r['NumOps_Ahead']) if r['NumOps_Ahead'] is not None else '',
            'rem_hrs': f"{r['Rem_Hrs']:.2f}" if r['Rem_Hrs'] is not None else '0.00',
            'qty_run': str(r['Qty_Run']) if r['Qty_Run'] is not None else '',
            'part': r['Part_Number'] or '',
            'description': r['Description'] or '',
        })

    return {
        'report_date': datetime.now().strftime('%d-%b-%y %I:%M%p'),
        'thru_date': cutoff.strftime('%m/%d/%Y'),
        'sections': list(sections.values()),
    }
