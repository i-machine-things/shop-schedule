#!/usr/bin/env python3
"""
Foreman Schedule - HTML generator for shop floor display.
Run via cron every 15 minutes. Pulls the current Foreman's Report (JobBoss DB,
or a PDF dropped/uploaded into place) and regenerates schedule.html for the
kiosk display. Only does anything between SCHEDULE_ACTIVE_START_HOUR and
SCHEDULE_ACTIVE_END_HOUR (.env, default 5-17 local time) -- cron/Task
Scheduler still trigger every 15 minutes around the clock either way; this
script itself skips the refresh outside that window.
"""

import hashlib
import html as _html
import json
import os
import re
import socket
import sys
import pdfplumber
from datetime import datetime

import jobboss_db


def _parse_hour(env_key, default):
    """Parse `env_key` as an hour (0-24); falls back to `default` if unset,
    blank, non-numeric, or out of range -- a malformed value should never
    crash the 15-minute refresh cycle, just use the default instead."""
    raw = os.environ.get(env_key, '').strip()
    if not raw:
        return default
    try:
        hour = int(raw)
    except ValueError:
        return default
    return hour if 0 <= hour <= 24 else default


# ── Config (loaded from .env by run_update.sh) ─────────────────────────────────
SHOP_NAME = os.environ.get('SHOP_NAME', 'My Shop')
PDF_FILENAME = os.path.basename(os.environ.get('PDF_FILENAME', '').strip()) or 'last_report.pdf'
PDF_COMPANY_NAME = os.environ.get('PDF_COMPANY_NAME', '').strip()
# The shop isn't staffed outside this window, so there's nothing new in
# JobBoss (or a new PDF worth parsing) to pick up either -- [start, end),
# in the device's own local time (same as every other datetime.now() in
# this file; assumes the system clock is already set to the device's
# correct local timezone, same assumption the midnight-refresh logic in
# update_schedule.py's generated JS already makes for this kind of fixed,
# stationary kiosk device).
SCHEDULE_ACTIVE_START_HOUR = _parse_hour('SCHEDULE_ACTIVE_START_HOUR', 5)
SCHEDULE_ACTIVE_END_HOUR = _parse_hour('SCHEDULE_ACTIVE_END_HOUR', 17)
if SCHEDULE_ACTIVE_START_HOUR >= SCHEDULE_ACTIVE_END_HOUR:
    # [start, end) only, no overnight-wraparound support (e.g. 22-6) -- a
    # start >= end would make _within_active_hours() false for every hour,
    # silently disabling the refresh entirely rather than just narrowing it.
    print(f"SCHEDULE_ACTIVE_START_HOUR ({SCHEDULE_ACTIVE_START_HOUR}) must be before "
          f"SCHEDULE_ACTIVE_END_HOUR ({SCHEDULE_ACTIVE_END_HOUR}) -- using the 5-17 default instead.",
          file=sys.stderr)
    SCHEDULE_ACTIVE_START_HOUR, SCHEDULE_ACTIVE_END_HOUR = 5, 17
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(BASE_DIR, PDF_FILENAME)
HTML_PATH = os.path.join(BASE_DIR, 'public', 'schedule.html')
KIOSK_PATH = os.path.join(BASE_DIR, 'public', 'kiosk.html')
JSON_PATH = os.path.join(BASE_DIR, 'public', 'schedule.json')
DEPT_COLORS_PATH = os.path.join(BASE_DIR, 'public', 'dept_colors.json')
# ───────────────────────────────────────────────────────────────────────────────


def _within_active_hours(now=None):
    """True if `now` (default: current local time) falls within
    [SCHEDULE_ACTIVE_START_HOUR, SCHEDULE_ACTIVE_END_HOUR)."""
    now = now or datetime.now()
    return SCHEDULE_ACTIVE_START_HOUR <= now.hour < SCHEDULE_ACTIVE_END_HOUR


def _get_local_ip():
    """Return the machine's outbound IP address, or None if unreachable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


# ── PDF Parsing ─────────────────────────────────────────────────────────────────

_SECTION_RE = re.compile(
    r'Department\s+(.+?)\s+WC\s*Group:\s*(.+?)\s+WC:\s*(.+?)\s*$', re.I)

# Each job is 3 lines in the PDF:
#   Line 1: {job} [{rev}] {qty}/ea {pri} {sch_start} {curr_wc} {ship_pri} {ship_qty} {promised}
#   Line 2: {customer} {oper} {sch_end} {num_ops} {rem_hrs} {qty_run}
#   Line 3: {part} [{description}]
_JOB_LINE_RE = re.compile(
    r'^(\d{4,5}[A-Z]?)'                        # job number
    r'(?:\s+([A-Z0-9])(?=\s+\d+/\w+))?'        # optional rev (only if followed by qty/unit)
    r'\s+(\d+)/\w+'                             # make_qty/unit
    r'\s+(\d+)'                                 # priority
    r'\s+(\d{2}-\w{3}-\d{2})'                  # sch_start
    r'\s+(.+)'                                  # curr_wc (greedy, backtracks)
    r'\s+\d+'                                   # ship_pri (ignored)
    r'\s+(\d+)'                                 # ship_qty
    r'\s+(\d{2}-\w{3}-\d{2})\s*$',             # promised
    re.I)
_CUST_LINE_RE = re.compile(
    r'^(.*?)\s+(\S+)\s+(\d{2}-\w{3}-\d{2})\s+(\d+)\s+([\d.]+)\s+(\d+)\s*$', re.I)

_company_pat = re.escape(PDF_COMPANY_NAME) + r'|' if PDF_COMPANY_NAME else ''
_SKIP_RE = re.compile(
    _company_pat +
    r'Foremans Report|Released Jobs Only|by Work Center|'
    r'Ship Qty|Sch Start|Make Qty|^\s*Page \d|Thru \d|'
    r'#\s*Ops|Curr WC|Rem Hrs|^\s*Job\s*$|Part\s+Description|Qty Run|'
    r'Rev\s+Make|Customer\s+Oper', re.I)


def parse_pdf(path):
    """Parse a Foreman's Report PDF and return {report_date, thru_date, sections}."""
    report_date = thru_date = ''
    all_lines = []

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ''
            if i == 0:
                m = re.search(r'(\d{2}-\w{3}-\d{2}\s+\d{2}:\d{2}[AP]M)', text)
                if m:
                    report_date = m.group(1)
                m = re.search(r'Thru\s+(\d+/\d+/\d+)', text)
                if m:
                    thru_date = m.group(1)
            all_lines.extend(text.split('\n'))

    sections = []
    cur_section = None
    state = 0   # 0=want job line, 1=want customer line, 2=want part line
    job_data = {}

    for raw in all_lines:
        line = raw.strip()
        if not line:
            continue

        sm = _SECTION_RE.search(line)
        if sm:
            state = 0
            cur_section = {
                'department': sm.group(1).strip(),
                'wc_group': sm.group(2).strip(),
                'wc': sm.group(3).strip(),
                'jobs': [],
            }
            sections.append(cur_section)
            continue

        if _SKIP_RE.search(line) or cur_section is None:
            continue

        if state == 0:
            m = _JOB_LINE_RE.match(line)
            if m:
                job_data = {
                    'job': m.group(1),
                    'rev': m.group(2) or '',
                    'make_qty': m.group(3),
                    'pri': m.group(4),
                    'sch_start': m.group(5),
                    'curr_wc': m.group(6).strip(),
                    'ship_qty': m.group(7),
                    'promised': m.group(8),
                    'customer': '', 'oper': '', 'op_key': '', 'oper_desc': '', 'sch_end': '',
                    'num_ops': '', 'rem_hrs': '', 'qty_run': '',
                    'part': '', 'description': '',
                }
                state = 1

        elif state == 1:
            m = _CUST_LINE_RE.match(line)
            if m:
                job_data['customer'] = m.group(1).strip()
                job_data['oper'] = m.group(2)
                job_data['sch_end'] = m.group(3)
                job_data['num_ops'] = m.group(4)
                job_data['rem_hrs'] = m.group(5)
                job_data['qty_run'] = m.group(6)
                state = 2
            else:
                # Unexpected line — check if it's actually a new job line
                m2 = _JOB_LINE_RE.match(line)
                if m2:
                    job_data = {
                        'job': m2.group(1),
                        'rev': m2.group(2) or '',
                        'make_qty': m2.group(3),
                        'pri': m2.group(4),
                        'sch_start': m2.group(5),
                        'curr_wc': m2.group(6).strip(),
                        'ship_qty': m2.group(7),
                        'promised': m2.group(8),
                        'customer': '', 'oper': '', 'op_key': '', 'oper_desc': '', 'sch_end': '',
                        'num_ops': '', 'rem_hrs': '', 'qty_run': '',
                        'part': '', 'description': '',
                    }
                else:
                    state = 0

        elif state == 2:
            parts = line.split(' ', 1)
            job_data['part'] = parts[0]
            job_data['description'] = parts[1] if len(parts) > 1 else ''
            cur_section['jobs'].append(job_data)
            job_data = {}
            state = 0

    # Merge sections that share the same WC (page-break duplicates)
    seen_wc = {}
    merged = []
    for sec in sections:
        key = sec['wc']
        if key in seen_wc:
            seen_wc[key]['jobs'].extend(sec['jobs'])
        else:
            seen_wc[key] = sec
            merged.append(sec)
    sections = merged

    return {'report_date': report_date, 'thru_date': thru_date, 'sections': sections}


# ── HTML Generation ─────────────────────────────────────────────────────────────

_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

# Keyword defaults — matched against lowercase dept name when a new dept is first seen.
_DEPT_DEFAULTS = {
    'assembly': ('#0d2b1a', '#1a6640'),
    'cnc': ('#0d1a2b', '#1a4466'),
    'inspection': ('#1e0d2b', '#4d2080'),
    'shipping': ('#2b1a0d', '#664020'),
    'welding': ('#2b0d0d', '#661a1a'),
    'manual': ('#0d2b2b', '#1a6666'),
    'machine': ('#1a1a0d', '#404020'),
    'engineer': ('#1a0d1a', '#401a40'),
}


def _load_dept_colors():
    """Return {lowercase_name: {name, bg, accent}} from dept_colors.json."""
    try:
        with open(DEPT_COLORS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_dept_colors(colors):
    """Merge colors into dept_colors.json; preserves user-set bg/accent for existing depts."""
    try:
        with open(DEPT_COLORS_PATH) as f:
            on_disk = json.load(f)
    except Exception:
        on_disk = {}
    for k, v in colors.items():
        if k not in on_disk:
            on_disk[k] = v
        else:
            on_disk[k]['name'] = v.get('name', on_disk[k].get('name', ''))
    tmp = DEPT_COLORS_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(on_disk, f, indent=2, sort_keys=True)
    os.replace(tmp, DEPT_COLORS_PATH)


def apply_work_center_backlogs(sections):
    """Attach backlog_days/gap_days to any section that doesn't already have
    them. The DB path (jobboss_db.fetch_from_db()) computes these itself
    from a separate query (no CROSS APPLY, cheaper) and attaches them before
    this ever runs. This only fills the gap for the PDF path, which has no
    such query available -- it falls back to deriving backlog from
    sec['jobs'] (whatever's in the uploaded PDF) as a reasonable, if
    narrower, approximation.

    _work_center_backlog_days() lives in jobboss_db.py, not here -- that
    module doesn't import this one, so it's the only side that can be
    shared without a circular import."""
    now = datetime.now()
    for sec in sections:
        if 'backlog_days' in sec:
            continue
        backlog_days, gap_days = jobboss_db._work_center_backlog_days(sec.get('jobs', []), now)
        sec['backlog_days'] = backlog_days
        sec['gap_days'] = gap_days


def _format_weeks_days(days):
    """'2 wk 3 day' style formatting from a raw day count -- omits a zero
    component ('3 day' or '2 wk', not '0 wk 3 day') and deliberately isn't a
    decimal-weeks number: "2.3 wk" doesn't translate into an actual calendar
    date at a glance on the shop floor the way "2 wk 2 day" does."""
    weeks, rem_days = divmod(days, 7)
    parts = []
    if weeks:
        parts.append(f"{weeks} wk")
    if rem_days or not parts:
        parts.append(f"{rem_days} day")
    return ' '.join(parts)


def generate_json(data, out_path):
    """Write the parsed schedule data as JSON for non-HTML consumers (e.g. a Roku
    kiosk client) -- same {report_date, thru_date, sections} shape used internally,
    served statically alongside schedule.html by server.py with no extra endpoint."""
    tmp = out_path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, out_path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _default_color(dept_lower):
    """Keyword match first; fall back to a deterministic hash-generated dark palette."""
    for keyword, (bg, accent) in _DEPT_DEFAULTS.items():
        if keyword in dept_lower:
            return bg, accent
    h = int(hashlib.sha1(dept_lower.encode(), usedforsecurity=False).hexdigest()[:6], 16)  # nosec B324
    r, g, b = (h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF
    bg = '#{:02x}{:02x}{:02x}'.format(max(r // 8, 5), max(g // 8, 5), max(b // 8, 5))
    accent = '#{:02x}{:02x}{:02x}'.format(
        min(r // 2 + 20, 200), min(g // 2 + 20, 200), min(b // 2 + 20, 200)
    )
    return bg, accent


def generate_html(data, out_path, *, kiosk=False, gen_ts=None):
    """Render parsed schedule data to an HTML file; kiosk=True emits the auto-scroll variant."""
    report_date = data['report_date']
    thru_date = data['thru_date']
    sections = data['sections']
    now = datetime.now()
    generated = now.strftime('%Y-%m-%d %H:%M')
    if gen_ts is None:
        gen_ts = int(now.timestamp())
    shop_name = _html.escape(SHOP_NAME)
    local_ip = _get_local_ip()
    url_path = 'kiosk.html' if kiosk else 'schedule.html'
    url_line = f'<div class="url-line">http://{local_ip}:8080/{url_path}</div>' if local_ip else ''

    colors = _load_dept_colors()
    colors_dirty = False

    # Mirrors the real Foreman's Report's header (date/time + company at
    # left, title centered, "by Work Center..."/"Released Jobs Only" at
    # right) -- shop_name comes from SHOP_NAME (.env), never hardcoded.
    #
    # "Released Jobs Only" is only claimed for DB-sourced data, where
    # jobboss_db.py's query unconditionally filters Released_Date IS NOT
    # NULL. For the PDF path it's whichever checkbox state JobBoss's own
    # Foreman's Report screen was in when someone generated the PDF we're
    # parsing -- not something we enforce, so not something we can claim.
    released_line = (
        '<div class="print-hdr-sub">Released Jobs Only</div>'
        if data.get('db_source') else ''
    )

    def _print_hdr(extra_class):
        return f'''
    <div class="print-hdr {extra_class}">
      <div class="print-hdr-left">
        <div>{generated}</div>
        <div class="print-hdr-company">{shop_name}</div>
      </div>
      <div class="print-hdr-title">Shop Schedule Report</div>
      <div class="print-hdr-right">
        <div>by Work Center - Scheduled Start Date</div>
        <div class="print-hdr-daterange"></div>
        {released_line}
      </div>
    </div>'''

    rows = []
    print_rows = []
    sec_idx = 0
    for sec in sections:
        if not sec['jobs']:
            continue
        sec_idx += 1
        dept = sec['department']
        dl = dept.lower()
        if dl not in colors:
            bg, accent = _default_color(dl)
            colors[dl] = {'name': dept, 'bg': bg, 'accent': accent}
            colors_dirty = True
        elif colors[dl].get('name') != dept:
            colors[dl]['name'] = dept
            colors_dirty = True
        bg = colors[dl]['bg']
        accent = colors[dl]['accent']
        if not (isinstance(bg, str) and _HEX_COLOR_RE.fullmatch(bg)):
            bg, _ = _default_color(dl)
        if not (isinstance(accent, str) and _HEX_COLOR_RE.fullmatch(accent)):
            _, accent = _default_color(dl)
        wc_attr = _html.escape(sec["wc"])
        dept_e = _html.escape(sec["department"])
        wcg_e = _html.escape(sec["wc_group"])
        backlog_days = sec.get('backlog_days', 0)
        gap_days = sec.get('gap_days')
        backlog_text = f"{_format_weeks_days(backlog_days)} backlog" if backlog_days > 0 else "open now"
        # gap_days is the *size* of the opening right after backlog_days, not
        # just that one exists -- a 1-week hole can't take a 2-week job, so
        # showing only "when" there's room without "how much" would be
        # actively misleading for exactly the use case this is for.
        if gap_days is not None:
            backlog_text += f" ({_format_weeks_days(gap_days)} gap)"
        rows.append(f'''
      <tr class="section-hdr" data-wc="{wc_attr}" data-sec="{sec_idx}">
        <td colspan="12" style="background:{bg};border-left:4px solid {accent}">
          <span class="wc-name">{wc_attr}</span>
          <span class="dept-name">{dept_e} &thinsp;&middot;&thinsp; {wcg_e}</span>
          <span class="wc-backlog">{backlog_text}</span>
        </td>
      </tr>''')
        # Source order is Department/WC_Group/WC/Job/Sequence (DB) or PDF
        # document order (PDF path) -- neither is chronological, so a work
        # center's rows can jump around in start date unless sorted here.
        # Blank/unparseable sch_start sorts last rather than first (datetime.min
        # default) so a job missing a date doesn't jump the whole queue.
        sec_jobs = sorted(
            sec['jobs'],
            key=lambda j: jobboss_db._parse_sched_date(j['sch_start']) or datetime.max,
        )
        print_job_rows = []
        for j in sec_jobs:
            overdue = ''
            if j['promised']:
                try:
                    if datetime.strptime(j['promised'], '%d-%b-%y') < datetime.now():
                        overdue = 'overdue'
                except Exception:
                    pass
            je = {k: _html.escape(str(v)) for k, v in j.items()}
            # ISO so the client's Schedule Window filter can Date()-parse it
            # directly -- blank (unparseable sch_start) means the row is
            # never hidden by that filter, only by the WC one.
            start_dt = jobboss_db._parse_sched_date(j['sch_start'])
            data_start = start_dt.strftime('%Y-%m-%d') if start_dt else ''
            rows.append(f'''
      <tr class="job" data-wc="{wc_attr}" data-sec="{sec_idx}" data-start="{data_start}" data-currwc="{je["curr_wc"]}">
        <td class="jnum">{je["job"]}</td>
        <td>{je["customer"]}</td>
        <td class="pdesc"><span class="pnum">{je["part"]}</span><br><span class="desc">{je["description"]}</span></td>
        <td class="c">{je["rev"]}</td>
        <td class="c">{je["oper"]}</td>
        <td class="odesc">{je["oper_desc"]}</td>
        <td class="c">{je["make_qty"]}</td>
        <td class="c">{je["sch_start"]}<br><span class="sub">{je["sch_end"]}</span></td>
        <td class="c">{je["curr_wc"]}</td>
        <td class="c">{je["rem_hrs"]}</td>
        <td class="c">{je["ship_qty"]}</td>
        <td class="c {overdue}">{je["promised"]}</td>
      </tr>''')

            print_job_rows.append(
                f'''
      <tr class="print-row" data-wc="{wc_attr}" data-sec="{sec_idx}" data-start="{data_start}" '''
                f'''data-currwc="{je["curr_wc"]}" data-remhrs="{je["rem_hrs"]}">
        <td><span class="p-job">{je["job"]}</span>'''
                f'''<span class="p-barcode" data-code="{je["job"]}"></span>{je["customer"]}<br>'''
                f'''{je["part"]}<br><span class="p-desc">{je["description"]}</span></td>
        <td>{je["rev"]}</td>
        <td>{je["oper"]}<span class="p-barcode" data-code="{je["op_key"]}" data-show-value="1"></span></td>
        <td class="p-desc">{je["oper_desc"]}</td>
        <td class="c">{je["make_qty"]}</td>
        <td class="c">{je["sch_start"]}<br>{je["sch_end"]}</td>
        <td class="c">{je["curr_wc"]}<br>{je["rem_hrs"]}</td>
        <td class="c">{je["ship_qty"]}</td>
        <td class="c {overdue}">{je["promised"]}</td>
      </tr>'''
            )

        print_rows.append(
            f'''
    <div class="print-section" data-wc="{wc_attr}" data-sec="{sec_idx}" data-dept="{dept_e}">
      {_print_hdr('print-hdr-section')}
      <div class="print-sec-hdr">Department&nbsp;&nbsp;{dept_e}&nbsp;&nbsp;&nbsp;&nbsp;'''
            f'''WC Group:&nbsp;&nbsp;{wcg_e}&nbsp;&nbsp;&nbsp;&nbsp;WC:&nbsp;{wc_attr}</div>
      <table class="print-table">
        <colgroup>
          <!-- Oper (3rd column, 17%) looks wide for "OP1" + a short number,
               but it has to fit the Oper barcode -- Code128 width scales with
               character count, and Job_Operation's real IDs can run 8+
               digits; narrower cut that barcode off into Oper Desc's text.
               CodeRabbit catch on PR #296. -->
          <col style="width:26%"><col style="width:4%"><col style="width:17%">
          <col style="width:11%"><col style="width:6%"><col style="width:11%">
          <col style="width:10%"><col style="width:6%"><col style="width:9%">
        </colgroup>
        <thead>
          <tr>
            <th>Job / Customer / Part</th>
            <th>Rev</th>
            <th>Oper</th>
            <th>Oper Desc</th>
            <th>Make Qty</th>
            <th>Sch Start / End</th>
            <th>Curr WC / Rem Hrs</th>
            <th>Ship Qty</th>
            <th>Promised</th>
          </tr>
        </thead>
        <tbody>
{"".join(print_job_rows)}
        </tbody>
        <tfoot>
          <tr class="print-total-row">
            <td colspan="6">Total Rem Hrs:</td>
            <td class="c print-total-val"></td>
            <td colspan="2"></td>
          </tr>
        </tfoot>
      </table>
    </div>''')

    if colors_dirty:
        _save_dept_colors(colors)

    body = '\n'.join(rows)
    # A standalone copy at the top for the default (continuous-flow) mode,
    # plus one baked into each section for "one page per workcenter" mode --
    # CSS shows exactly one of the two depending on that checkbox (see
    # print-hdr-main/print-hdr-section in the @media print block). @page
    # margin boxes (confirmed working in current Chromium -- see the
    # "Page X of Y" @top-right rule in that same block) only cover simple
    # generated content (counters/strings), not repeating an arbitrary HTML
    # block like this full header onto every *naturally* overflowing page --
    # this duplication only covers the case where we already know where each
    # page starts, because we forced the break.
    print_body = _print_hdr('print-hdr-main') + '\n' + '\n'.join(print_rows)

    home_btn = '' if kiosk else '<a href="index.html" id="home-btn" title="Home">&#8962;</a>\n    '

    kiosk_css = '''
#kiosk-overlay{position:fixed;inset:0;z-index:200;background:#000;
  opacity:0;pointer-events:none;transition:opacity var(--fade-ms,1500ms) ease}
#kiosk-overlay.visible{opacity:1;pointer-events:auto}
#kiosk-overlay iframe{width:100%;height:100%;border:none}''' if kiosk else ''

    overlay_div = '\n<div id="kiosk-overlay"><iframe id="kiosk-frame"></iframe></div>' if kiosk else ''

    scroll_cycle_js = (
        "if(typeof window._kioskOnScrollCycle==='function') window._kioskOnScrollCycle();"
        if kiosk else
        "if(window.parent !== window) window.parent.postMessage({type:'scroll-cycle'},'*');"
    )
    fits_screen_js = (
        "if(!loopReady && typeof window._kioskOnFitsScreen==='function') window._kioskOnFitsScreen();"
        if kiosk else
        "if(!loopReady && window.parent !== window)\n    window.parent.postMessage({type:'fits-screen'},'*');"
    )

    kiosk_js = '''
// ── Kiosk navigation lock ─────────────────────────────────────────────────────
history.pushState(null, '', location.href);
window.addEventListener('popstate', () => history.pushState(null, '', location.href));
window.addEventListener('beforeunload', e => { e.preventDefault(); e.returnValue = ''; });

// ── Kiosk page rotation ───────────────────────────────────────────────────────
(function(){
  let SCHEDULE_CYCLES = 2, PAGE_DURATION = 60, FADE_MS_K = 1500;
  let SCHEDULE_MAX_MS = 300000, PAGES = [], cycleCount = 0;
  let advTimer = null, overlayVisible = false, slotIdx = -1;
  const overlay = document.getElementById('kiosk-overlay');
  const frame   = document.getElementById('kiosk-frame');

  function armScheduleTimer() {
    clearTimeout(advTimer);
    advTimer = setTimeout(() => { advTimer = null; showNextPage(); }, SCHEDULE_MAX_MS);
  }

  function showNextPage() {
    if (!PAGES.length) return;
    slotIdx = (slotIdx + 1) % PAGES.length;
    const page = PAGES[slotIdx];
    const secs = page.seconds ?? PAGE_DURATION;
    const raw  = page.url ?? '';
    const path = raw.split('?')[0].split('#')[0];
    frame.src  = path.toLowerCase().endsWith('.pdf')
      ? 'pdf-viewer.html?url=' + encodeURIComponent(raw) + '&t=' + secs
      : raw;
    overlay.classList.add('visible');
    overlayVisible = true;
    clearTimeout(advTimer);
    advTimer = setTimeout(snapBack, secs * 1000);
  }

  function snapBack() {
    clearTimeout(advTimer); advTimer = null;
    overlay.classList.remove('visible');
    overlayVisible = false;
    cycleCount = 0;
    setTimeout(() => { frame.src = ''; }, FADE_MS_K);
    if (PAGES.length) armScheduleTimer();
  }

  ['mousemove', 'keydown', 'touchstart', 'click'].forEach(ev =>
    document.addEventListener(ev, () => { if (overlayVisible) snapBack(); })
  );

  window._kioskOnScrollCycle = () => {
    if (!PAGES.length || overlayVisible) return;
    if (++cycleCount >= SCHEDULE_CYCLES) { cycleCount = 0; showNextPage(); }
  };
  window._kioskOnFitsScreen = () => {
    if (!PAGES.length || overlayVisible || advTimer !== null) return;
    armScheduleTimer();
  };

  function applyKioskConfig(cfg) {
    SCHEDULE_CYCLES = cfg.scroll_cycles ?? 2;
    PAGE_DURATION   = cfg.page_duration ?? 60;
    FADE_MS_K       = cfg.transition_ms ?? 1500;
    const rawMaxS   = parseInt(cfg.schedule_max_s, 10);
    SCHEDULE_MAX_MS = (Number.isNaN(rawMaxS) ? 300 : Math.max(1, Math.min(rawMaxS, 3600))) * 1000;
    if (cfg.allow_manual_scroll === true) { clearTimeout(advTimer); advTimer = null; }
    document.documentElement.style.setProperty('--fade-ms', FADE_MS_K + 'ms');
    PAGES = (cfg.pages ?? []).map(p => typeof p === 'string' ? { url: p } : p);
    if (PAGES.length > 0 && cfg.allow_manual_scroll !== true && typeof window._kioskOnFitsScreen === 'function') {
      window._kioskOnFitsScreen();
    }
  }

  fetch('/api/pages').then(r => r.json()).then(applyKioskConfig).catch(() => {});
  setInterval(() => fetch('/api/pages').then(r => r.json()).then(applyKioskConfig).catch(() => {}), 60000);
})();''' if kiosk else ''

    html = (f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{shop_name} &mdash; Shop Schedule</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#07070f;color:#ddd;font-family:'Courier New',monospace;font-size:14px;overflow:hidden;height:100vh}}
#hdr{{position:fixed;top:0;left:0;right:0;height:50px;background:#0b0b18;border-bottom:2px solid #222;
      display:flex;align-items:center;justify-content:space-between;padding:0 18px;z-index:99}}
#hdr-left{{display:flex;align-items:center;gap:12px;min-width:0;overflow:hidden}}
#hdr h1{{font-size:18px;color:#fff;letter-spacing:2px;text-transform:uppercase;
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}}
#home-btn{{display:flex;align-items:center;justify-content:center;flex-shrink:0;
           width:32px;height:32px;color:#4af;border:1px solid #4af;
           text-decoration:none;font-size:16px;opacity:0.7;transition:opacity 0.2s}}
#home-btn:hover{{opacity:1;background:#1a2a44}}
#hdr .meta{{display:flex;align-items:center;gap:20px;flex-shrink:0;white-space:nowrap}}
.meta-info{{font-size:12px;color:#888;text-align:right;line-height:1.4}}
.url-line{{font-size:10px;color:#4af;opacity:0.8}}
#clock{{font-size:24px;color:#4af;font-weight:bold}}
#sidebar{{position:fixed;top:50px;left:0;bottom:0;width:160px;background:#0b0b18;
          border-right:1px solid #222;z-index:50;display:flex;flex-direction:column;overflow-y:auto}}
.sidebar-hdr{{padding:8px 10px 4px;font-size:10px;color:#555;letter-spacing:2px;text-transform:uppercase;
              flex-shrink:0;cursor:pointer;display:flex;align-items:center;justify-content:space-between;
              user-select:none}}
.sidebar-hdr:hover{{color:#888}}
.sidebar-hdr .chev{{font-size:9px;transition:transform 0.15s}}
.sidebar-hdr.collapsed .chev{{transform:rotate(-90deg)}}
.hidden-section{{display:none!important}}
#wc-all{{margin:2px 8px 6px;padding:5px 4px;background:transparent;border:1px solid #4af;
         color:#4af;cursor:pointer;font-family:inherit;font-size:11px;
         letter-spacing:1px;text-transform:uppercase}}
#wc-all:hover{{background:#1a2a44}}
#wc-list{{flex:1 1 auto;min-height:80px;overflow-y:auto;padding:0 8px 8px;display:flex;flex-direction:column;gap:2px}}
.wc-btn{{padding:5px 8px;background:#0d1a2b;border:1px solid #222;color:#666;cursor:pointer;
         font-family:inherit;font-size:11px;letter-spacing:1px;text-transform:uppercase;
         text-align:left;transition:background 0.15s,border-color 0.15s,color 0.15s}}
.wc-btn.active{{background:#0d2010;border-color:#3a7a3a;color:#8f8}}
.wc-btn:hover{{background:#1a2233;color:#ddd;border-color:#4af}}
#view-list,#mode-list{{flex-shrink:0;padding:0 8px 8px;display:flex;flex-direction:column;gap:2px}}
.view-btn{{padding:5px 8px;background:#0d1a2b;border:1px solid #222;color:#666;cursor:pointer;
         font-family:inherit;font-size:11px;letter-spacing:1px;text-transform:uppercase;
         text-align:left;transition:background 0.15s,border-color 0.15s,color 0.15s}}
.view-btn.active{{background:#0d1a2b;border-color:#4af;color:#4af}}
.view-btn:hover{{background:#1a2233;color:#ddd;border-color:#4af}}
.print-opt{{display:flex;align-items:center;gap:6px;margin:2px 8px 6px;padding:0 4px;
            font-size:10px;color:#888;letter-spacing:1px;text-transform:uppercase;cursor:pointer}}
.print-opt input{{cursor:pointer}}
#print-select-row{{display:flex;gap:4px;margin:2px 8px 6px}}
#print-select-all,#print-deselect-all{{flex:0 0 auto;padding:4px 8px;background:transparent;
                    border:1px solid #4af;color:#4af;cursor:pointer;font-family:inherit;
                    font-size:10px;letter-spacing:1px;text-transform:uppercase}}
#print-select-all:hover,#print-deselect-all:hover{{background:#1a2a44}}
#print-select-dept{{flex:1 1 auto;min-width:0;background:#0d1a2b;border:1px solid #222;
                     color:#888;font-family:inherit;font-size:10px;padding:4px;cursor:pointer}}
#print-list{{display:flex;flex-direction:column;gap:2px;padding:0 8px 8px;
             max-height:240px;overflow-y:auto}}
#print-btn{{margin:2px 8px 8px;padding:5px 4px;background:transparent;border:1px solid #4af;
         color:#4af;cursor:pointer;font-family:inherit;font-size:11px;
         letter-spacing:1px;text-transform:uppercase}}
#print-btn:hover{{background:#1a2a44}}
#print-btn:disabled{{opacity:0.3;cursor:not-allowed}}
#print-btn:disabled:hover{{background:transparent}}
#wrap{{position:fixed;top:50px;bottom:0;left:160px;right:0;overflow-y:scroll}}
/* Laid out off-screen at all times (not display:none) so paginatePrintOutput()
   can measure real row/header heights via getBoundingClientRect() whenever
   Print is clicked, without a display:none->block toggle dance first. Width
   matches the real printed content area (Letter landscape - 2*0.5in @page
   margin) so text wrapping in pdesc/odesc matches what will actually print. */
#print-output{{position:absolute;top:0;left:0;width:10in;visibility:hidden;pointer-events:none}}
table{{width:100%;border-collapse:separate;border-spacing:0}}
thead th{{position:sticky;top:0;z-index:20;background:#0d0d20;color:#7799ff;font-size:11px;
          text-transform:uppercase;letter-spacing:1px;padding:6px 8px;border-bottom:2px solid #333}}
.section-hdr td{{position:sticky;z-index:10;padding:8px 14px;border-bottom:1px solid #333}}
.wc-name{{font-size:16px;font-weight:bold;color:#fff;letter-spacing:2px;text-transform:uppercase;margin-right:14px}}
.dept-name{{font-size:11px;color:#888}}
.wc-backlog{{font-size:11px;color:#4af;font-weight:bold;margin-left:14px}}
.job td{{padding:5px 8px;border-bottom:1px solid #111;vertical-align:top}}
.job:nth-child(even){{background:rgba(255,255,255,0.02)}}
.jnum{{color:#4af;font-weight:bold;font-size:15px;white-space:nowrap}}
.pdesc{{max-width:220px;white-space:normal}}
.odesc{{max-width:160px;white-space:normal;color:#aaa;font-size:12px}}
.pnum{{color:#eee}}
.desc{{color:#777;font-size:12px}}
.c{{text-align:center;white-space:nowrap}}
.sub{{color:#666;font-size:12px}}
.overdue{{color:#f55;font-weight:bold}}
#theme-btn{{background:transparent;border:1px solid #4af;color:#4af;
           cursor:pointer;font-size:14px;padding:0;width:32px;height:32px;
           font-family:inherit;flex-shrink:0;opacity:0.7;transition:opacity 0.2s}}
#theme-btn:hover{{opacity:1;background:#1a2a44}}
[data-theme="light"] body{{background:#f5f5f0;color:#111}}
[data-theme="light"] #hdr{{background:#e8e8f0;border-bottom-color:#ccc}}
[data-theme="light"] #hdr h1{{color:#111}}
[data-theme="light"] #home-btn{{color:#0066cc;border-color:#0066cc}}
[data-theme="light"] #home-btn:hover{{background:#c0d8f0}}
[data-theme="light"] .meta-info{{color:#555}}
[data-theme="light"] .url-line{{color:#0066cc}}
[data-theme="light"] #clock{{color:#0066cc}}
[data-theme="light"] #theme-btn{{border-color:#0066cc;color:#0066cc}}
[data-theme="light"] #theme-btn:hover{{background:#c0d8f0}}
[data-theme="light"] #sidebar{{background:#e8e8f0;border-right-color:#ccc}}
[data-theme="light"] .sidebar-hdr{{color:#888}}
[data-theme="light"] #wc-all{{border-color:#0066cc;color:#0066cc}}
[data-theme="light"] #wc-all:hover{{background:#c0d8f0}}
[data-theme="light"] .wc-btn{{background:#dde4f0;border-color:#ccc;color:#555}}
[data-theme="light"] .wc-btn.active{{background:#d0f0d8;border-color:#3a7a3a;color:#1a6020}}
[data-theme="light"] .wc-btn:hover{{background:#c8d8f0;color:#111;border-color:#0066cc}}
[data-theme="light"] .view-btn{{background:#dde4f0;border-color:#ccc;color:#555}}
[data-theme="light"] .view-btn.active{{background:#dde4f0;border-color:#0066cc;color:#0066cc}}
[data-theme="light"] .view-btn:hover{{background:#c8d8f0;color:#111;border-color:#0066cc}}
[data-theme="light"] .print-opt{{color:#555}}
[data-theme="light"] #print-select-all,[data-theme="light"] #print-deselect-all{{border-color:#0066cc;color:#0066cc}}
[data-theme="light"] #print-select-all:hover,[data-theme="light"] #print-deselect-all:hover{{background:#c0d8f0}}
[data-theme="light"] #print-select-dept{{background:#dde4f0;border-color:#ccc;color:#555}}
[data-theme="light"] #print-btn{{border-color:#0066cc;color:#0066cc}}
[data-theme="light"] #print-btn:hover{{background:#c0d8f0}}
[data-theme="light"] #print-btn:disabled:hover{{background:transparent}}
[data-theme="light"] thead th{{background:#d8dcf0;color:#224499;border-bottom-color:#ccc}}
[data-theme="light"] .section-hdr td{{background:#eaecf8!important;border-bottom-color:#ccc}}
[data-theme="light"] .wc-name{{color:#111}}
[data-theme="light"] .dept-name{{color:#555}}
[data-theme="light"] .wc-backlog{{color:#0066cc}}
[data-theme="light"] .job td{{border-bottom-color:#ddd}}
[data-theme="light"] .job:nth-child(even){{background:rgba(0,0,0,0.03)}}
[data-theme="light"] .jnum{{color:#0066cc}}
[data-theme="light"] .pnum{{color:#222}}
[data-theme="light"] .desc{{color:#555}}
[data-theme="light"] .odesc{{color:#555}}
[data-theme="light"] .sub{{color:#666}}
[data-theme="light"] .overdue{{color:#cc0000}}

/* Print Report -- "mirror the screen": only rows already visible under the
   current Schedule Window/Mode filter AND belonging to a selected work
   center print. Page numbers ("Page X of Y") can't use CSS Paged Media's
   @page margin boxes (@top-right etc.) -- Firefox has never implemented
   them, only Chromium has -- so paginatePrintOutput() (see the print-btn
   click handler) computes real page breaks itself from measured element
   heights and stamps an ordinary .print-page-num element before each one;
   .print-force-break is what actually breaks the page at that point. A
   section whose jobs don't fit on one page is split into multiple <table>s
   by the same function, each with its own repeated column-header row.
   Position:fixed/sticky are reset to static since fixed positioning clips
   print output to a single page in Chrome.

   All of #print-output's own content styling below is deliberately NOT
   scoped to @media print, even though it only ever matters when printing --
   #print-output is already invisible on screen (position:absolute;
   visibility:hidden, set unconditionally above) regardless of media type,
   so these rules have zero visual effect outside of printing. Scoping them
   to @media print instead would make them invisible to
   getBoundingClientRect() during paginatePrintOutput()'s measurement pass,
   since that runs in ordinary screen context, not inside an actual print
   -- the real heights it needs to measure (print-table row heights,
   section header heights, barcode heights, ...) only exist once these
   rules are live. */
.print-page-num {{ text-align:right; font-size:10px; color:#000; margin-bottom:4px }}
.print-force-break {{ break-before:page }}
.print-chunked-out {{ display:none!important }}
.print-hdr {{ display:flex; justify-content:space-between; align-items:flex-start;
              border-bottom:2px solid #000; padding-bottom:8px; margin-bottom:10px }}
.print-hdr-left {{ font-size:10px }}
.print-hdr-company {{ font-weight:bold; font-size:13px; margin-top:2px }}
.print-hdr-title {{ font-weight:bold; font-size:16px; align-self:center }}
.print-hdr-right {{ font-size:10px; text-align:right }}
.print-hdr-sub {{ margin-top:2px }}
.print-hdr-daterange {{ margin-top:2px }}
.print-hdr-section {{ display:none }}
#print-output.pagebreak-per-wc .print-hdr-main {{ display:none }}
#print-output.pagebreak-per-wc .print-hdr-section {{ display:flex }}
.print-sec-hdr {{ font-weight:bold; font-size:11px; border-bottom:1px solid #000; padding:4px 0; margin-top:4px }}
/* table-layout:fixed + the <colgroup> above locks column widths to fixed
   percentages instead of sizing them from each table's own cell content --
   needed so a chunk table built from a subset of rows (see
   paginatePrintOutput()) can't wrap text differently than the original
   table did, which would silently invalidate the row heights that were
   measured against the original. */
.print-table {{ width:100%; table-layout:fixed; border-collapse:collapse; font-size:10px; color:#000 }}
.print-table th {{ text-align:left; font-size:9px; border-bottom:1px solid #000; padding:3px 4px;
                    background:#fff; color:#000; position:static }}
.print-table td {{ padding:3px 4px; border-bottom:1px solid #ccc; vertical-align:top }}
.print-table td.c {{ text-align:center }}
.print-row {{ break-inside:avoid }}
.p-job {{ font-weight:bold }}
.p-desc {{ color:#444; font-size:9px }}
.p-barcode {{ display:block; margin:2px 0 }}
.p-barcode rect {{ fill:#000 }}
.p-barcode-num {{ display:block; font-size:8px; color:#000; letter-spacing:1px }}
.print-table .overdue {{ color:#c00; font-weight:bold }}
.print-total-row td {{ border-top:2px solid #000; border-bottom:none; font-weight:bold;
                        text-align:right; padding-top:6px }}
@page {{ size: letter landscape; margin: 0.5in }}
@media print {{
  #hdr, #sidebar, #wrap {{ display:none }}
  body {{ overflow:visible; height:auto; background:#fff; color:#000 }}
  #print-output {{ position:static; width:auto; visibility:visible; pointer-events:auto }}
}}
{kiosk_css}
</style>
<script>try{{if(localStorage.getItem('theme')==='light')document.documentElement.setAttribute('data-theme','light');}}catch(e){{}}</script>
</head>
<body data-gen="{gen_ts}">
<div id="hdr">
  <div id="hdr-left">
    {home_btn}<h1>{shop_name} &mdash; Shop Schedule</h1>
  </div>
  <div class="meta">
    <div class="meta-info">
      <div>Report: {report_date} &nbsp;|&nbsp; Thru: {thru_date}</div>
      <div>Updated: {generated}</div>
      {url_line}
    </div>
    <div id="clock" aria-live="polite" aria-label="Current time" aria-atomic="true"></div>
    <button id="theme-btn" aria-label="Toggle theme">&#9728;</button>
  </div>
</div>

<div id="sidebar">
  <div class="sidebar-hdr" data-toggle="wc-all,wc-list">Work Centers<span class="chev">&#9662;</span></div>
  <button id="wc-all">All</button>
  <div id="wc-list"></div>
  <div class="sidebar-hdr" data-toggle="view-list">Schedule Window<span class="chev">&#9662;</span></div>
  <div id="view-list"></div>
  <div class="sidebar-hdr" data-toggle="mode-list">Schedule Mode<span class="chev">&#9662;</span></div>
  <div id="mode-list"></div>
  <div class="sidebar-hdr" data-toggle="print-select-row,print-list,print-pagebreak-opt,print-btn">"""
        f"""Print Report<span class="chev">&#9662;</span></div>
  <div id="print-select-row">
    <button id="print-select-all">All</button>
    <button id="print-deselect-all">None</button>
    <select id="print-select-dept"><option value="">Dept&hellip;</option></select>
  </div>
  <div id="print-list"></div>
  <label id="print-pagebreak-opt" class="print-opt">
    <input type="checkbox" id="print-pagebreak">
    One page per workcenter
  </label>
  <button id="print-btn" disabled>Print</button>
</div>
<div id="wrap">
<table>
  <thead>
    <tr>
      <th>Job</th><th>Customer</th><th>Part / Description</th>
      <th>Rev</th><th>Oper</th><th>Oper Desc</th><th>Qty</th>
      <th>Sch Start/End</th><th>Curr WC</th>
      <th>Rem Hrs</th><th>Ship Qty</th><th>Promised</th>
    </tr>
  </thead>
  <tbody>
{body}
  </tbody>
</table>
</div>
<div id="print-output">
{print_body}
</div>
{overlay_div}
<script>
// Sidebar sections -- the sidebar itself always stays visible; each
// section (Work Centers / Schedule Window / Schedule Mode / Print
// Report) collapses independently via its own header, so a short
// viewport or a crowded sidebar doesn't lose access to the ones below.
// Persisted per section like the theme toggle, since this is a standing
// display preference rather than a one-off choice.
(function(){{
  // Print Report starts collapsed by default (a shop can have dozens of work
  // centers, making it by far the tallest section) -- everything else starts
  // expanded. Only applies on a first visit with nothing stored yet; once the
  // user has toggled anything, their own choice always wins.
  const DEFAULT_COLLAPSED = ['print-select-row,print-list,print-pagebreak-opt,print-btn'];
  let collapsed;
  try {{
    const stored = localStorage.getItem('sidebar_collapsed');
    collapsed = new Set(stored !== null ? JSON.parse(stored) : DEFAULT_COLLAPSED);
  }} catch(e) {{ collapsed = new Set(DEFAULT_COLLAPSED); }}
  function persist(){{
    try {{ localStorage.setItem('sidebar_collapsed', JSON.stringify([...collapsed])); }} catch(e) {{}}
  }}
  document.querySelectorAll('.sidebar-hdr[data-toggle]').forEach(hdr => {{
    const key = hdr.dataset.toggle;
    const targets = key.split(',').map(id => document.getElementById(id));
    function apply(){{
      const isCollapsed = collapsed.has(key);
      hdr.classList.toggle('collapsed', isCollapsed);
      targets.forEach(el => {{ if(el) el.classList.toggle('hidden-section', isCollapsed); }});
    }}
    apply();
    hdr.addEventListener('click', () => {{
      if(collapsed.has(key)) collapsed.delete(key); else collapsed.add(key);
      apply();
      persist();
    }});
  }});
}})();

// Theme
(function(){{
  let t; try {{ t=localStorage.getItem('theme'); }} catch(e) {{}}
  const btn=document.getElementById('theme-btn');
  btn.textContent=t==='light'?'☾':'☀';
  btn.addEventListener('click',function(){{
    const next=document.documentElement.getAttribute('data-theme')==='light'?'dark':'light';
    if(next==='light') document.documentElement.setAttribute('data-theme','light');
    else document.documentElement.removeAttribute('data-theme');
    try {{ localStorage.setItem('theme',next); }} catch(e) {{}}
    btn.textContent=next==='light'?'☾':'☀';
  }});
}})();

// Clock
(function tick(){{
  document.getElementById('clock').textContent =
    new Date().toLocaleTimeString('en-US',{{hour:'2-digit',minute:'2-digit',second:'2-digit'}});
  setTimeout(tick,1000);
}})();

// Pin section headers just below the frozen column header row
function pinSectionHeaders(){{
  const theadH = document.querySelector('thead').offsetHeight;
  document.querySelectorAll('.section-hdr td').forEach(td => td.style.top = theadH + 'px');
}}

const wrap = document.getElementById('wrap');
let pos = 0;
let paused = false;
let pauseTimer = null;
let PAUSE_RESUME_MS = 10000; // overridden by scroll_resume_s from pages.json
const SPEED = 0.6;
let singleHeight = 0;
let loopReady = false;

function setupLoop(){{
  const tbody = document.querySelector('#wrap tbody');
  singleHeight = tbody.offsetHeight;
  if(!loopReady && singleHeight > wrap.clientHeight){{
    tbody.innerHTML += tbody.innerHTML;
    loopReady = true;
  }}
  pinSectionHeaders();
  {fits_screen_js}
}}
setupLoop();

function pauseScroll(){{
  paused = true;
  clearTimeout(pauseTimer);
  pauseTimer = setTimeout(()=>{{ paused = false; pos = wrap.scrollTop; }}, PAUSE_RESUME_MS);
}}

wrap.addEventListener('wheel',      pauseScroll, {{passive:true}});
wrap.addEventListener('touchstart', pauseScroll, {{passive:true}});
wrap.addEventListener('mousedown',  pauseScroll, {{passive:true}});

// Check for schedule updates; apply only when scrolled back to top
let currentGen = document.body.dataset.gen;
let pendingHTML = null;

function applyPendingUpdate() {{
  const m = pendingHTML.match(/data-gen="(\\d+)"/);
  if (!m) {{ pendingHTML = null; return; }}
  currentGen = m[1];
  const newDoc = new DOMParser().parseFromString(pendingHTML, 'text/html');
  const newMeta = newDoc.querySelector('.meta-info');
  const newTbody = newDoc.querySelector('#wrap tbody');
  const newPrintOutput = newDoc.querySelector('#print-output');
  pendingHTML = null;
  if (!newMeta || !newTbody) return;
  document.querySelector('.meta-info').innerHTML = newMeta.innerHTML;
  document.querySelector('#wrap tbody').innerHTML = newTbody.innerHTML;
  if (newPrintOutput) document.querySelector('#print-output').innerHTML = newPrintOutput.innerHTML;
  loopReady = false;
  buildSidebar();
  buildPrintList();
  renderBarcodes();
  applyFilter();
  wrap.scrollTop = 0;
  pos = 0;
}}

const _fpsLimit = parseInt(new URLSearchParams(location.search).get('fps'), 10);
const _frameMs  = (_fpsLimit > 0 && _fpsLimit < 60) ? 1000 / _fpsLimit : 0;
let _stepTs = 0;
function step(ts){{
  if(_frameMs && ts - _stepTs < _frameMs){{ requestAnimationFrame(step); return; }}
  const dt = _frameMs ? Math.min(ts - _stepTs, 200) : 16.67;
  _stepTs = ts;
  if(!paused){{
    if(wrap.scrollHeight - wrap.clientHeight > 0){{
      pos += SPEED * dt / 16.67;
      if(singleHeight > 0 && pos >= singleHeight){{
        pos -= singleHeight;
        wrap.scrollTop = pos;
        {scroll_cycle_js}
      }}
      wrap.scrollTop = pos;
    }}
  }}
  if(pendingHTML !== null && pos < 2) applyPendingUpdate();
  requestAnimationFrame(step);
}}

// scroll_resume_s is a local (per-device) setting stored in localStorage
(function(){{
  let raw = NaN; try {{ raw = parseInt(localStorage.getItem('scroll_resume_s'), 10); }} catch(e) {{}}
  PAUSE_RESUME_MS = (Number.isNaN(raw) ? 10 : Math.max(1, Math.min(raw, 300))) * 1000;
}})();
fetch('/api/pages').then(r => r.json()).then(cfg => {{
  if(cfg.allow_manual_scroll !== true) requestAnimationFrame(step);
}}).catch(() => requestAnimationFrame(step));

// WC sidebar filter
const activeWCs = new Set();
let allWCs = [];

function buildSidebar(){{
  allWCs = [...new Set(
    [...document.querySelectorAll('#wrap tbody .section-hdr')].map(tr => tr.dataset.wc).filter(Boolean)
  )];
  activeWCs.clear();
  allWCs.forEach(wc => activeWCs.add(wc));
  const list = document.getElementById('wc-list');
  list.innerHTML = '';
  allWCs.forEach(wc => {{
    const btn = document.createElement('button');
    btn.className = 'wc-btn active';
    btn.dataset.wc = wc;
    btn.textContent = wc;
    btn.addEventListener('click', () => toggleWC(wc));
    list.appendChild(btn);
  }});
}}

// Code128 (subset B) barcode encoder + SVG renderer, hand-rolled rather than
// a vendored library, matching the rest of this page (no third-party JS,
// no CDN -- the kiosk device may have no internet access). Subset B maps
// ASCII 32-126 directly onto symbol values 0-94 (value = charCode-32), so no
// character-to-symbol lookup table is needed, only the bar-pattern table
// itself. That pattern table is the same one the well-established Python
// "python-barcode" library uses; this encoder was verified against it
// before shipping -- both a from-scratch pixel-decode round trip and a
// direct bar-pattern comparison against that library's own output (which
// matched for every input except ones with 4+ consecutive digits, where
// that library switches to the more compact subset C -- a size
// optimization this encoder deliberately skips, not a bug: subset B alone
// is fully spec-compliant and reads fine on any standard scanner).
const CODE128_PATTERNS = [
  '11011001100', '11001101100', '11001100110', '10010011000', '10010001100',
  '10001001100', '10011001000', '10011000100', '10001100100', '11001001000',
  '11001000100', '11000100100', '10110011100', '10011011100', '10011001110',
  '10111001100', '10011101100', '10011100110', '11001110010', '11001011100',
  '11001001110', '11011100100', '11001110100', '11101101110', '11101001100',
  '11100101100', '11100100110', '11101100100', '11100110100', '11100110010',
  '11011011000', '11011000110', '11000110110', '10100011000', '10001011000',
  '10001000110', '10110001000', '10001101000', '10001100010', '11010001000',
  '11000101000', '11000100010', '10110111000', '10110001110', '10001101110',
  '10111011000', '10111000110', '10001110110', '11101110110', '11010001110',
  '11000101110', '11011101000', '11011100010', '11011101110', '11101011000',
  '11101000110', '11100010110', '11101101000', '11101100010', '11100011010',
  '11101111010', '11001000010', '11110001010', '10100110000', '10100001100',
  '10010110000', '10010000110', '10000101100', '10000100110', '10110010000',
  '10110000100', '10011010000', '10011000010', '10000110100', '10000110010',
  '11000010010', '11001010000', '11110111010', '11000010100', '10001111010',
  '10100111100', '10010111100', '10010011110', '10111100100', '10011110100',
  '10011110010', '11110100100', '11110010100', '11110010010', '11011011110',
  '11011110110', '11110110110', '10101111000', '10100011110', '10001011110',
  '10111101000', '10111100010', '11110101000', '11110100010', '10111011110',
  '10111101110', '11101011110', '11110101110', '11010000100', '11010010000',
  '11010011100',
];
const CODE128_STOP = '11000111010';
const CODE128_START_B = 104;

function code128Modules(text){{
  const values = [CODE128_START_B];
  for (const ch of text){{
    const v = ch.charCodeAt(0) - 32;
    if (v >= 0 && v <= 94) values.push(v);
  }}
  let checksum = values[0];
  for (let i = 1; i < values.length; i++) checksum += i * values[i];
  values.push(checksum % 103);
  return values.map(v => CODE128_PATTERNS[v]).join('') + CODE128_STOP + '11';
}}

function code128Svg(text, moduleWidth, height){{
  const modules = code128Modules(text);
  const width = modules.length * moduleWidth;
  let bars = '';
  for (let i = 0; i < modules.length; i++){{
    if (modules[i] === '1') {{
      bars += `<rect x="${{i * moduleWidth}}" y="0" width="${{moduleWidth}}" height="${{height}}"/>`;
    }}
  }}
  return `<svg class="p-barcode" viewBox="0 0 ${{width}} ${{height}}" """
        f"""width="${{width}}" height="${{height}}">${{bars}}</svg>`;
}}

// Renders every still-unrendered barcode placeholder inside #print-output.
// Run once at page load and again after applyPendingUpdate() replaces
// #print-output's innerHTML with freshly-generated (unrendered) markup.
function renderBarcodes(){{
  document.querySelectorAll('#print-output .p-barcode[data-code]').forEach(el => {{
    // je["oper"] (and in principle je["job"]) can be a blank string -- remove
    // the placeholder entirely rather than leaving an empty display:block
    // span with its own margin sitting in the row.
    if (!el.dataset.code) {{ el.remove(); return; }}
    // The job barcode's own value is already shown as bold plaintext right
    // above it (the job number); the op barcode's value (op_key) has no
    // other plaintext appearance anywhere on the page, so only it repeats
    // its value below the barcode -- not a blanket behavior for every
    // barcode, just this one, via data-show-value.
    const valueHtml = el.dataset.showValue === '1'
      ? `<span class="p-barcode-num">${{el.dataset.code}}</span>` : '';
    el.outerHTML = code128Svg(el.dataset.code, 1, 10) + valueHtml;
  }});
}}

// Print Report -- "mirror the screen": prints only rows already visible
// under the current Schedule Window/Mode filter, restricted to the work
// centers selected here. Independent multi-select; not persisted, since
// it's a deliberate per-print choice rather than a display preference
// like the other sidebar controls.
const printWCs = new Set();

function buildPrintList(){{
  for (const wc of [...printWCs]) if (!allWCs.includes(wc)) printWCs.delete(wc);
  const list = document.getElementById('print-list');
  list.innerHTML = '';
  allWCs.forEach(wc => {{
    const btn = document.createElement('button');
    btn.className = 'view-btn' + (printWCs.has(wc) ? ' active' : '');
    btn.textContent = wc;
    btn.addEventListener('click', () => {{
      if(printWCs.has(wc)) printWCs.delete(wc); else printWCs.add(wc);
      btn.classList.toggle('active', printWCs.has(wc));
      syncPrintButton();
    }});
    list.appendChild(btn);
  }});
  syncPrintButton();

  // Department -> its work centers, straight off the print-output sections
  // (same source the print selection itself reads), so "select dept" always
  // matches whatever work centers are actually on the page right now.
  const deptToWCs = new Map();
  document.querySelectorAll('#print-output .print-section').forEach(sec => {{
    const dept = sec.dataset.dept;
    if(!dept) return;
    if(!deptToWCs.has(dept)) deptToWCs.set(dept, new Set());
    deptToWCs.get(dept).add(sec.dataset.wc);
  }});
  const deptSelect = document.getElementById('print-select-dept');
  deptSelect.innerHTML = '<option value="">Dept&hellip;</option>';
  [...deptToWCs.keys()].sort().forEach(dept => {{
    const opt = document.createElement('option');
    opt.value = dept;
    opt.textContent = dept;
    deptSelect.appendChild(opt);
  }});
  deptSelect.onchange = () => {{
    const wcs = deptToWCs.get(deptSelect.value);
    if(wcs) wcs.forEach(wc => printWCs.add(wc));
    deptSelect.value = '';
    syncPrintListButtons();
  }};
}}

function syncPrintListButtons(){{
  document.querySelectorAll('#print-list .view-btn').forEach(btn => {{
    btn.classList.toggle('active', printWCs.has(btn.textContent));
  }});
  syncPrintButton();
}}

document.getElementById('print-select-all').addEventListener('click', () => {{
  allWCs.forEach(wc => printWCs.add(wc));
  syncPrintListButtons();
}});

document.getElementById('print-deselect-all').addEventListener('click', () => {{
  printWCs.clear();
  syncPrintListButtons();
}});

function syncPrintButton(){{
  document.getElementById('print-btn').disabled = printWCs.size === 0;
}}

// Off by default: the real Foreman's Report lets work centers flow
// continuously, only breaking pages where content happens to overflow.
// Forcing a fresh page per WC is opt-in, persisted like the theme toggle.
const pagebreakCb = document.getElementById('print-pagebreak');
try {{ pagebreakCb.checked = localStorage.getItem('print_pagebreak') === '1'; }} catch(e) {{}}
pagebreakCb.addEventListener('change', () => {{
  try {{ localStorage.setItem('print_pagebreak', pagebreakCb.checked ? '1' : '0'); }} catch(e) {{}}
}});


// "Thru <date>", not a two-sided range -- the Schedule Window filter only
// ever caps how far *out* a job can start (see matchesWindowAndMode()); it
// never excludes an overdue/already-started job on the other end, so a
// literal start-to-end range would misleadingly imply jobs before today
// are excluded.
function printDateRangeText(){{
  const active = VIEW_WINDOWS.find(w => w.days === viewDays) || VIEW_WINDOWS[VIEW_WINDOWS.length - 1];
  if(viewDays === Infinity) return active.label;
  const end = new Date();
  end.setHours(0, 0, 0, 0);
  // matchesWindowAndMode()'s cutoff (today + viewDays) is an EXCLUSIVE upper
  // bound -- the last day actually included is one day before that, so the
  // printed label needs the same -1 or it'd claim a day that's excluded.
  end.setDate(end.getDate() + viewDays - 1);
  const fmt = d => d.toLocaleDateString('en-US', {{month:'2-digit', day:'2-digit', year:'2-digit'}});
  return `${{active.label}} (thru ${{fmt(end)}})`;
}}

// Page numbers ("Page X of Y") can't rely on CSS Paged Media's @page margin
// boxes -- Firefox has never implemented @top-right/etc, only Chromium has
// -- so this computes real page breaks itself from measured element heights
// (which is why #print-output's print styling isn't gated behind @media
// print: it needs to be live during this ordinary-screen-context pass) and
// stamps an ordinary .print-page-num element before each one.
// Letter landscape content height is 7.5in (0.5in @page margin, 96 CSS
// px/in) minus ~14px for the per-page label and a safety margin:
// getBoundingClientRect() on an element doesn't include its own margins,
// and several small per-element shortfalls like that compound once enough
// rows/headers share a page -- empirically tuned against a worst-case
// render (three sections packed onto one page) rather than derived
// exactly, so this errs conservative on purpose. Only valid for landscape,
// which is why @page above pins `size: letter landscape` -- a page's real
// printed dimensions aren't exposed to JS at all (no API reports the print
// dialog's selected paper size/orientation), so the only way to keep this
// budget trustworthy is to force the one layout it was computed for.
const PRINT_PAGE_BUDGET_PX = 620;

function clearPagination(printOutput){{
  printOutput.querySelectorAll('.print-injected').forEach(el => el.remove());
  printOutput.querySelectorAll('.print-force-break').forEach(el => el.classList.remove('print-force-break'));
  printOutput.querySelectorAll('.print-chunked-out').forEach(el => el.classList.remove('print-chunked-out'));
}}

function paginatePrintOutput(printOutput, useBreaks){{
  const mainHdr = printOutput.querySelector(':scope > .print-hdr-main');
  const sections = [...printOutput.querySelectorAll(':scope > .print-section')]
    .filter(sec => !sec.classList.contains('hidden-section'));
  if(!sections.length) return;

  // The very first thing printed overall: the main header in continuous
  // mode (mainHdr is absent here already if useBreaks, see the click
  // handler), otherwise the first section's own repeated header.
  const pageStarts = [(!useBreaks && mainHdr) ? mainHdr : sections[0]];
  let budget = PRINT_PAGE_BUDGET_PX;
  if(!useBreaks && mainHdr) budget -= mainHdr.getBoundingClientRect().height;

  sections.forEach((sec, secIdx) => {{
    const secHdr = sec.querySelector(':scope > .print-hdr-section');
    const deptHdr = sec.querySelector(':scope > .print-sec-hdr');
    const table = sec.querySelector(':scope > table.print-table');
    const thead = table.querySelector('thead');
    const tfoot = table.querySelector('tfoot');
    const rows = [...table.querySelectorAll('tbody > tr.print-row')]
      .filter(tr => !tr.classList.contains('hidden-section'));
    const theadH = thead.getBoundingClientRect().height;
    // secHdr is only really going to render in useBreaks mode (CSS hides it
    // otherwise), but that CSS rule depends on the .pagebreak-per-wc class
    // alone, so it's already live here too -- no need to re-check useBreaks.
    const topBlockH = secHdr.getBoundingClientRect().height + deptHdr.getBoundingClientRect().height + theadH;

    if(secIdx > 0){{
      const firstRowH = rows[0].getBoundingClientRect().height;
      if(useBreaks || budget < topBlockH + firstRowH){{
        pageStarts.push(sec);
        budget = PRINT_PAGE_BUDGET_PX;
      }}
    }}
    budget -= topBlockH;

    // Walk this section's own rows, splitting into page-chunks as needed.
    // chunk[0] always stays put in the original table; chunk[1+] become new
    // <table>s appended after it (built below), each repeating the column
    // header. Rows aren't moved out of the original table for this -- they're
    // cloned into the new chunk table and hidden (.print-chunked-out) in the
    // original -- so there's nothing to "undo": next click's clearPagination
    // just removes the injected tables and un-hides the originals.
    const chunks = [[]];
    const deptHdrH = deptHdr.getBoundingClientRect().height;
    rows.forEach(tr => {{
      const h = tr.getBoundingClientRect().height;
      let chunk = chunks[chunks.length - 1];
      if(chunk.length && budget < h){{
        // deptHdr repeats on every continuation page too (not just thead) --
        // a reader starting mid-table on page 3 of a long work center still
        // needs to see which department/WC this is, same as page 1 does.
        chunks.push(chunk = []);
        budget = PRINT_PAGE_BUDGET_PX - deptHdrH - theadH;
      }}
      chunk.push(tr);
      budget -= h;
    }});
    // Exactly one copy of tfoot ends up visible, wherever this section's
    // last row landed (the original table if it wasn't split, otherwise the
    // last chunk) -- either way it still takes up real space on that page,
    // which the next section (if one shares the page) needs to know about.
    budget -= tfoot.getBoundingClientRect().height;

    for(let i = 1; i < chunks.length; i++){{
      const deptHdrClone = deptHdr.cloneNode(true);
      deptHdrClone.classList.add('print-injected');
      const chunkTable = document.createElement('table');
      chunkTable.className = table.className;
      chunkTable.classList.add('print-injected');
      chunkTable.appendChild(table.querySelector('colgroup').cloneNode(true));
      chunkTable.appendChild(thead.cloneNode(true));
      const tbody = document.createElement('tbody');
      // Clone BEFORE hiding the originals -- cloneNode(true) copies whatever
      // classes are on tr *at clone time*, so hiding tr first would hide its
      // clone too.
      chunks[i].forEach(tr => tbody.appendChild(tr.cloneNode(true)));
      chunks[i].forEach(tr => tr.classList.add('print-chunked-out'));
      chunkTable.appendChild(tbody);
      if(i === chunks.length - 1 && tfoot) chunkTable.appendChild(tfoot.cloneNode(true));
      sec.appendChild(deptHdrClone);
      sec.appendChild(chunkTable);
      // The label (and its break-before:page, added in the labeling pass
      // below) goes before deptHdrClone, not chunkTable -- deptHdrClone is
      // genuinely the first thing on this page now, so insertBefore needs
      // to target it, not the table that comes after it.
      pageStarts.push(deptHdrClone);
    }}
    if(chunks.length > 1 && tfoot) tfoot.classList.add('print-chunked-out');
  }});

  const total = pageStarts.length;
  pageStarts.forEach((el, i) => {{
    const label = document.createElement('div');
    label.className = 'print-page-num print-injected';
    // The break itself goes on the LABEL, not on `el` -- el is only used to
    // find the right insertion point. A break on `el` would land between the
    // label and its page's real content, stranding the label on the
    // *previous* page instead of the one it's labeling.
    if(i > 0) label.classList.add('print-force-break');
    label.textContent = `Page ${{i + 1}} of ${{total}}`;
    el.parentNode.insertBefore(label, el);
  }});
}}

document.getElementById('print-btn').addEventListener('click', () => {{
  const printOutput = document.getElementById('print-output');
  clearPagination(printOutput);
  const useBreaks = pagebreakCb.checked;
  printOutput.classList.toggle('pagebreak-per-wc', useBreaks);
  const rangeText = printDateRangeText();
  document.querySelectorAll('#print-output .print-hdr-daterange').forEach(el => {{
    el.textContent = rangeText;
  }});
  // display:none isn't enough to rule out: pull print-hdr-main out of the DOM
  // entirely in this mode rather than trust that a hidden sibling can't
  // affect where break-before:page lands on the first section. Reinserted
  // after printing so unchecking the box later still has a header to show.
  const mainHdr = printOutput.querySelector(':scope > .print-hdr-main');
  if(useBreaks && mainHdr){{
    mainHdr.remove();
    window.addEventListener('afterprint', () => {{ printOutput.prepend(mainHdr); }}, {{ once:true }});
  }}
  document.querySelectorAll('#print-output .print-section').forEach(sec => {{
    let total = 0;
    let anyVisible = false;
    sec.querySelectorAll('.print-row').forEach(tr => {{
      const visible = printWCs.has(tr.dataset.wc) &&
        matchesWindowAndMode(tr.dataset.wc, tr.dataset.start, tr.dataset.currwc);
      tr.classList.toggle('hidden-section', !visible);
      if(visible){{
        anyVisible = true;
        total += parseFloat(tr.dataset.remhrs) || 0;
      }}
    }});
    sec.classList.toggle('hidden-section', !anyVisible);
    const totalEl = sec.querySelector('.print-total-val');
    if(totalEl) totalEl.textContent = anyVisible ? total.toFixed(2) : '';
  }});
  paginatePrintOutput(printOutput, useBreaks);
  window.print();
}});

function syncButtons(){{
  document.querySelectorAll('.wc-btn').forEach(btn => {{
    btn.classList.toggle('active', activeWCs.has(btn.dataset.wc));
  }});
}}

// Schedule Window -- local (per-device) setting stored in localStorage,
// same pattern as theme/scroll_resume_s above. Hides job rows whose
// sch_start falls beyond the chosen window, and in turn hides a section's
// header once none of its jobs are visible -- purely client-side filtering
// of what the server already sent; doesn't touch the server, schedule.json,
// or any other kiosk/browser viewing the same schedule.
const VIEW_WINDOWS = [
  {{label:'Today', days:1, key:'1'}},
  {{label:'3 Days', days:3, key:'3'}},
  {{label:'1 Week', days:7, key:'7'}},
  {{label:'2 Weeks', days:14, key:'14'}},
  {{label:'All', days:Infinity, key:'all'}},
];
let viewDays = Infinity;

function buildViewFilter(){{
  let saved; try {{ saved = localStorage.getItem('view_window_days'); }} catch(e) {{}}
  saved = saved || 'all';
  const active = VIEW_WINDOWS.find(w => w.key === saved) || VIEW_WINDOWS.find(w => w.key === 'all');
  viewDays = active.days;
  const list = document.getElementById('view-list');
  list.innerHTML = '';
  VIEW_WINDOWS.forEach(w => {{
    const btn = document.createElement('button');
    btn.className = 'view-btn' + (w.key === active.key ? ' active' : '');
    btn.textContent = w.label;
    btn.addEventListener('click', () => setViewWindow(w));
    list.appendChild(btn);
  }});
}}

function setViewWindow(w){{
  viewDays = w.days;
  try {{ localStorage.setItem('view_window_days', w.key); }} catch(e) {{}}
  document.querySelectorAll('#view-list .view-btn').forEach((btn, i) => {{
    btn.classList.toggle('active', VIEW_WINDOWS[i].key === w.key);
  }});
  applyFilter();
}}

// Schedule Mode -- a second, independent exclusive-choice control (Standard /
// WC Dispatch) stored under its own localStorage key. Orthogonal to the
// Schedule Window above: both filters are ANDed together in applyFilter(),
// so switching to WC Dispatch narrows whatever date window is already
// selected rather than replacing it.
const SCHEDULE_MODES = [
  {{label:'Standard', key:'standard'}},
  {{label:'WC Dispatch', key:'dispatch'}},
];
let dispatchMode = false;

function buildScheduleMode(){{
  let saved; try {{ saved = localStorage.getItem('schedule_mode'); }} catch(e) {{}}
  saved = saved || 'standard';
  const active = SCHEDULE_MODES.find(m => m.key === saved) || SCHEDULE_MODES[0];
  dispatchMode = active.key === 'dispatch';
  const list = document.getElementById('mode-list');
  list.innerHTML = '';
  SCHEDULE_MODES.forEach(m => {{
    const btn = document.createElement('button');
    btn.className = 'view-btn' + (m.key === active.key ? ' active' : '');
    btn.textContent = m.label;
    btn.addEventListener('click', () => setScheduleMode(m));
    list.appendChild(btn);
  }});
}}

function setScheduleMode(m){{
  dispatchMode = m.key === 'dispatch';
  try {{ localStorage.setItem('schedule_mode', m.key); }} catch(e) {{}}
  document.querySelectorAll('#mode-list .view-btn').forEach((btn, i) => {{
    btn.classList.toggle('active', SCHEDULE_MODES[i].key === m.key);
  }});
  applyFilter();
}}

// Schedule Window (date) and Schedule Mode (WC Dispatch) are independent,
// ANDed filters -- WC Dispatch narrows whatever date window is already
// selected (e.g. "1 Week" + WC Dispatch = ready-to-run jobs due within a
// week) rather than replacing it.
// matchesWindowAndMode() is shared by applyFilter() (the on-screen table) and
// the Print Report handler (the separate #print-output layout) so the
// Schedule Window/Mode half of "mirror the screen" can't drift out of sync.
// The Work Center filter is deliberately NOT part of that shared check --
// Print Report has its own independent work-center selection (printWCs), so
// isVisible() (on-screen only) layers activeWCs on top, while the print
// handler layers printWCs on top instead.
function matchesWindowAndMode(wc, startStr, currWc){{
  if(viewDays !== Infinity){{
    const cutoff = new Date();
    cutoff.setHours(0, 0, 0, 0);
    cutoff.setDate(cutoff.getDate() + viewDays);
    if(startStr && new Date(startStr + 'T00:00:00') >= cutoff) return false;
  }}
  if(dispatchMode && currWc !== wc) return false;
  return true;
}}
function isVisible(wc, startStr, currWc){{
  return activeWCs.has(wc) && matchesWindowAndMode(wc, startStr, currWc);
}}

function applyFilter(){{
  if(loopReady){{
    const rows = [...document.querySelectorAll('#wrap tbody tr')];
    const half = rows.length / 2;
    rows.slice(half).forEach(r => r.remove());
    loopReady = false;
  }}
  // A hot content swap (applyPendingUpdate, via a stale served page mid-rollback)
  // could in principle deliver rows without data-sec. Falling back to data-wc
  // keeps those rows grouped by their own work center instead of every such
  // row colliding on the same `undefined` key and toggling every legacy
  // section header together.
  const sectionHasVisibleJob = new Set();
  document.querySelectorAll('#wrap tbody tr.job').forEach(tr => {{
    const visible = isVisible(tr.dataset.wc, tr.dataset.start, tr.dataset.currwc);
    tr.style.display = visible ? '' : 'none';
    if(visible) sectionHasVisibleJob.add(tr.dataset.sec || tr.dataset.wc);
  }});
  document.querySelectorAll('#wrap tbody tr.section-hdr').forEach(tr => {{
    const secKey = tr.dataset.sec || tr.dataset.wc;
    tr.style.display = (activeWCs.has(tr.dataset.wc) && sectionHasVisibleJob.has(secKey)) ? '' : 'none';
  }});
  pos = 0;
  wrap.scrollTop = 0;
  setupLoop();
}}

function toggleWC(wc){{
  if(activeWCs.size === allWCs.length){{
    activeWCs.clear();
    activeWCs.add(wc);
  }} else if(activeWCs.size === 1 && activeWCs.has(wc)){{
    allWCs.forEach(w => activeWCs.add(w));
  }} else {{
    if(activeWCs.has(wc)) activeWCs.delete(wc); else activeWCs.add(wc);
  }}
  syncButtons();
  applyFilter();
}}

document.getElementById('wc-all').addEventListener('click', ()=>{{
  allWCs.forEach(wc => activeWCs.add(wc));
  syncButtons();
  applyFilter();
}});

buildSidebar();
buildPrintList();
buildViewFilter();
buildScheduleMode();
renderBarcodes();
applyFilter();

// Keep the "Today" window's cutoff current if the page is left open across
// midnight without a new schedule generation arriving to re-trigger applyFilter().
function scheduleMidnightRefresh(){{
  const now = new Date();
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 5);
  // "All" has no date cutoff, so there's nothing for midnight to change --
  // skip the needless scroll-position reset, but still keep scheduling.
  setTimeout(() => {{ if(viewDays !== Infinity) applyFilter(); scheduleMidnightRefresh(); }}, next - now);
}}
scheduleMidnightRefresh();

// Pause/resume from kiosk shell
window.addEventListener('message', e => {{
  if(e.data?.type === 'pause') {{ clearTimeout(pauseTimer); paused = true; }}
  else if(e.data?.type === 'resume') {{ paused = false; pos = wrap.scrollTop; }}
}});

// Poll version.json every 15 s; fetch full HTML only when generation timestamp changes
setInterval(async () => {{
  try {{
    const v = await (await fetch('version.json?_=' + Date.now())).json();
    if(String(v.gen) === currentGen || pendingHTML !== null) return;
    const txt = await (await fetch(location.pathname + '?_=' + Date.now())).text();
    const m = txt.match(/data-gen="(\\d+)"/);
    if(m && m[1] !== currentGen) pendingHTML = txt;
  }} catch(e) {{ console.warn('Update check failed:', e); }}
}}, 15000);
{kiosk_js}
</script>
</body>
</html>""")  # nosec B608 -- static HTML/JS template, no DB query built here;
    # bandit's DOTALL regex matches "select" (an HTML <select>) ... "from" (English
    # prose in a JS comment) across this whole literal. See CODING_NOTES.md.

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    version_path = os.path.join(os.path.dirname(out_path), 'version.json')
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump({'gen': gen_ts}, f)
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Generated: {out_path}")


# ── Main ────────────────────────────────────────────────────────────────────────

def main(force=False):
    """Regenerate schedule.html/kiosk.html from the JobBoss DB if configured,
    otherwise fall back to parsing a PDF already sitting at PDF_PATH from a
    manual drop (incoming/) or web upload (options.html) -- same on both
    platforms. No-ops outside SCHEDULE_ACTIVE_START_HOUR/END_HOUR, leaving
    the last-generated pages in place, unless force=True (--force on the
    command line) -- process_drop.py passes that for a web upload or a
    manual drop-dir run, since someone deliberately handing over a new PDF
    right now should take effect immediately, not silently wait for the
    next active-hours cycle. The unattended cron/Task Scheduler path never
    passes it, so the gate still applies there."""
    if not force and not _within_active_hours():
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] Outside active hours "
              f"({SCHEDULE_ACTIVE_START_HOUR:02d}:00-{SCHEDULE_ACTIVE_END_HOUR:02d}:00) -- skipping this cycle.")
        return
    if jobboss_db.is_configured():
        data = jobboss_db.fetch_from_db()
        if data is None:
            # Leave the existing schedule.html in place rather than guessing --
            # a transient DB outage shouldn't blank the kiosk or fall back to a
            # stale PDF parse that could silently disagree with the DB going forward.
            print("DB fetch failed; keeping last displayed schedule.", file=sys.stderr)
            return
        # Our own query always filters Released_Date IS NOT NULL (jobboss_db.py)
        # -- unlike the PDF path, where "released jobs only" is just whichever
        # checkbox state JobBoss's own Foreman's Report screen happened to be
        # in when someone generated the PDF we're parsing, not something we
        # enforce ourselves. Only claim it on the print report for this path.
        data['db_source'] = True
        total_jobs = sum(len(s['jobs']) for s in data['sections'])
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] DB fetch OK: "
              f"{len(data['sections'])} sections, {total_jobs} job rows. Display refreshed.")
    else:
        if not os.path.exists(PDF_PATH):
            print("JOBBOSS_DB_* is not configured and no PDF has been provided. "
                  "Fill in .env's JOBBOSS_DB_* (preferred), or drop a PDF into incoming/.",
                  file=sys.stderr)
            return
        data = parse_pdf(PDF_PATH)
        data['db_source'] = False
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] Parsed {PDF_PATH}. Display refreshed.")

    apply_work_center_backlogs(data['sections'])

    gen_ts = int(datetime.now().timestamp())
    generate_html(data, HTML_PATH, gen_ts=gen_ts)
    generate_html(data, KIOSK_PATH, kiosk=True, gen_ts=gen_ts)
    generate_json(data, JSON_PATH)


if __name__ == '__main__':
    main(force='--force' in sys.argv)
