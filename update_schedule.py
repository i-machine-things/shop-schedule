#!/usr/bin/env python3
"""
Foreman Schedule - Email poller & HTML generator for shop floor display.
Run via cron every 15 minutes. Checks Gmail for new Shop Schedule PDF, parses it,
and regenerates schedule.html for the kiosk display.
"""

import html as _html
import imaplib
import email
import json
import os
import re
import socket
import sys
import pdfplumber
from datetime import datetime

# ── Config (loaded from .env by run_update.sh) ─────────────────────────────────
GMAIL_USER        = os.environ.get('GMAIL_USER', '')
GMAIL_PASS        = os.environ.get('GMAIL_PASS', '')   # Gmail App Password
SHOP_NAME         = os.environ.get('SHOP_NAME', 'My Shop')
PDF_FILENAME      = os.environ.get('PDF_FILENAME', '').strip() or 'last_report.pdf'
PDF_COMPANY_NAME  = os.environ.get('PDF_COMPANY_NAME', '').strip()
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PDF_PATH     = os.path.join(BASE_DIR, PDF_FILENAME)
HTML_PATH    = os.path.join(BASE_DIR, 'public', 'schedule.html')
# ───────────────────────────────────────────────────────────────────────────────


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


# ── Email ───────────────────────────────────────────────────────────────────────

def fetch_pdf():
    """Check Gmail inbox for unread email with PDF attachment. Returns True if new PDF saved."""
    try:
        conn = imaplib.IMAP4_SSL('imap.gmail.com', timeout=30)
        conn.login(GMAIL_USER, GMAIL_PASS)
        conn.select('inbox')
        _, data = conn.search(None, 'UNSEEN')
        for num in data[0].split():
            _, raw = conn.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(raw[0][1])
            for part in msg.walk():
                fname = part.get_filename() or ''
                if fname.lower().endswith('.pdf'):
                    with open(PDF_PATH, 'wb') as f:
                        f.write(part.get_payload(decode=True))
                    conn.store(num, '+FLAGS', '\\Seen')
                    conn.logout()
                    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Saved: {fname}")
                    return True
        conn.logout()
    except Exception as exc:
        print(f"Email error: {exc}", file=sys.stderr)
    return False


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
                'wc_group':   sm.group(2).strip(),
                'wc':         sm.group(3).strip(),
                'jobs':       [],
            }
            sections.append(cur_section)
            continue

        if _SKIP_RE.search(line) or cur_section is None:
            continue

        if state == 0:
            m = _JOB_LINE_RE.match(line)
            if m:
                job_data = {
                    'job':      m.group(1),
                    'rev':      m.group(2) or '',
                    'make_qty': m.group(3),
                    'pri':      m.group(4),
                    'sch_start':m.group(5),
                    'curr_wc':  m.group(6).strip(),
                    'ship_qty': m.group(7),
                    'promised': m.group(8),
                    'customer': '', 'oper': '', 'sch_end': '',
                    'num_ops':  '', 'rem_hrs': '', 'qty_run': '',
                    'part':     '', 'description': '',
                }
                state = 1

        elif state == 1:
            m = _CUST_LINE_RE.match(line)
            if m:
                job_data['customer'] = m.group(1).strip()
                job_data['oper']     = m.group(2)
                job_data['sch_end']  = m.group(3)
                job_data['num_ops']  = m.group(4)
                job_data['rem_hrs']  = m.group(5)
                job_data['qty_run']  = m.group(6)
                state = 2
            else:
                # Unexpected line — check if it's actually a new job line
                m2 = _JOB_LINE_RE.match(line)
                if m2:
                    job_data = {
                        'job':      m2.group(1),
                        'rev':      m2.group(2) or '',
                        'make_qty': m2.group(3),
                        'pri':      m2.group(4),
                        'sch_start':m2.group(5),
                        'curr_wc':  m2.group(6).strip(),
                        'ship_qty': m2.group(7),
                        'promised': m2.group(8),
                        'customer': '', 'oper': '', 'sch_end': '',
                        'num_ops':  '', 'rem_hrs': '', 'qty_run': '',
                        'part':     '', 'description': '',
                    }
                else:
                    state = 0

        elif state == 2:
            parts = line.split(' ', 1)
            job_data['part']        = parts[0]
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

_DEPT_COLORS = {
    'assembly':  ('#0d2b1a', '#1a6640'),
    'cnc':       ('#0d1a2b', '#1a4466'),
    'inspection':('#1e0d2b', '#4d2080'),
    'shipping':  ('#2b1a0d', '#664020'),
    'welding':   ('#2b0d0d', '#661a1a'),
    'manual':    ('#0d2b2b', '#1a6666'),
    'machine':   ('#1a1a0d', '#404020'),
    'engineer':  ('#1a0d1a', '#401a40'),
}

def _dept_colors(dept):
    dl = dept.lower()
    for k, (bg, accent) in _DEPT_COLORS.items():
        if k in dl:
            return bg, accent
    return '#111122', '#334'


def generate_html(data, out_path):
    report_date = data['report_date']
    thru_date   = data['thru_date']
    sections    = data['sections']
    now         = datetime.now()
    generated   = now.strftime('%Y-%m-%d %H:%M')
    gen_ts      = int(now.timestamp())
    shop_name   = _html.escape(SHOP_NAME)
    local_ip    = _get_local_ip()
    url_line    = f'<div class="url-line">http://{local_ip}:8080/schedule.html</div>' if local_ip else ''

    rows = []
    for sec in sections:
        if not sec['jobs']:
            continue
        bg, accent = _dept_colors(sec['department'])
        rows.append(f'''
      <tr class="section-hdr">
        <td colspan="11" style="background:{bg};border-left:4px solid {accent}">
          <span class="wc-name">{sec["wc"]}</span>
          <span class="dept-name">{sec["department"]} &thinsp;&middot;&thinsp; {sec["wc_group"]}</span>
        </td>
      </tr>''')
        for j in sec['jobs']:
            overdue = ''
            if j['promised']:
                try:
                    if datetime.strptime(j['promised'], '%d-%b-%y') < datetime.now():
                        overdue = 'overdue'
                except Exception:
                    pass
            rows.append(f'''
      <tr class="job">
        <td class="jnum">{j["job"]}</td>
        <td>{j["customer"]}</td>
        <td class="pdesc"><span class="pnum">{j["part"]}</span><br><span class="desc">{j["description"]}</span></td>
        <td class="c">{j["rev"]}</td>
        <td class="c">{j["oper"]}</td>
        <td class="c">{j["make_qty"]}</td>
        <td class="c">{j["sch_start"]}<br><span class="sub">{j["sch_end"]}</span></td>
        <td class="c">{j["curr_wc"]}</td>
        <td class="c">{j["rem_hrs"]}</td>
        <td class="c">{j["ship_qty"]}</td>
        <td class="c {overdue}">{j["promised"]}</td>
      </tr>''')

    body = '\n'.join(rows)

    html = f"""<!DOCTYPE html>
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
#hdr h1{{font-size:18px;color:#fff;letter-spacing:2px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}}
#home-btn{{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:32px;height:32px;color:#4af;border:1px solid #4af;text-decoration:none;font-size:16px;opacity:0.7;transition:opacity 0.2s}}
#home-btn:hover{{opacity:1;background:#1a2a44}}
#hdr .meta{{display:flex;align-items:center;gap:20px;flex-shrink:0;white-space:nowrap}}
.meta-info{{font-size:12px;color:#888;text-align:right;line-height:1.4}}
.url-line{{font-size:10px;color:#4af;opacity:0.8}}
#clock{{font-size:24px;color:#4af;font-weight:bold}}
#wrap{{position:fixed;top:50px;bottom:0;left:0;right:0;overflow-y:scroll}}
table{{width:100%;border-collapse:separate;border-spacing:0}}
thead th{{position:sticky;top:0;z-index:20;background:#0d0d20;color:#7799ff;font-size:11px;
          text-transform:uppercase;letter-spacing:1px;padding:6px 8px;border-bottom:2px solid #333}}
.section-hdr td{{position:sticky;z-index:10;padding:8px 14px;border-bottom:1px solid #333}}
.wc-name{{font-size:16px;font-weight:bold;color:#fff;letter-spacing:2px;text-transform:uppercase;margin-right:14px}}
.dept-name{{font-size:11px;color:#888}}
.job td{{padding:5px 8px;border-bottom:1px solid #111;vertical-align:top}}
.job:nth-child(even){{background:rgba(255,255,255,0.02)}}
.jnum{{color:#4af;font-weight:bold;font-size:15px;white-space:nowrap}}
.pdesc{{max-width:220px;white-space:normal}}
.pnum{{color:#eee}}
.desc{{color:#777;font-size:12px}}
.c{{text-align:center;white-space:nowrap}}
.sub{{color:#666;font-size:12px}}
.overdue{{color:#f55;font-weight:bold}}
</style>
</head>
<body data-gen="{gen_ts}">
<div id="hdr">
  <div id="hdr-left">
    <a href="index.html" id="home-btn" title="Home">&#8962;</a>
    <h1>{shop_name} &mdash; Shop Schedule</h1>
  </div>
  <div class="meta">
    <div class="meta-info">
      <div>Report: {report_date} &nbsp;|&nbsp; Thru: {thru_date}</div>
      <div>Updated: {generated}</div>
      {url_line}
    </div>
    <div id="clock"></div>
  </div>
</div>

<div id="wrap">
<table>
  <thead>
    <tr>
      <th>Job</th><th>Customer</th><th>Part / Description</th>
      <th>Rev</th><th>Oper</th><th>Qty</th>
      <th>Sch Start/End</th><th>Curr WC</th>
      <th>Rem Hrs</th><th>Ship Qty</th><th>Promised</th>
    </tr>
  </thead>
  <tbody>
{body}
  </tbody>
</table>
</div>

<script>
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
const SPEED = 0.6;
let singleHeight = 0;
let loopReady = false;

function setupLoop(){{
  const tbody = document.querySelector('tbody');
  singleHeight = tbody.offsetHeight;
  if(!loopReady && singleHeight > wrap.clientHeight){{
    tbody.innerHTML += tbody.innerHTML;
    loopReady = true;
  }}
  pinSectionHeaders();
}}
setupLoop();

function pauseScroll(){{
  paused = true;
  clearTimeout(pauseTimer);
  pauseTimer = setTimeout(()=>{{ paused = false; pos = wrap.scrollTop; }}, 10000);
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
  const newTbody = newDoc.querySelector('tbody');
  pendingHTML = null;
  if (!newMeta || !newTbody) return;
  document.querySelector('.meta-info').innerHTML = newMeta.innerHTML;
  document.querySelector('tbody').innerHTML = newTbody.innerHTML;
  loopReady = false;
  setupLoop();
  wrap.scrollTop = 0;
  pos = 0;
}}

function step(){{
  if(!paused){{
    if(wrap.scrollHeight - wrap.clientHeight > 0){{
      pos += SPEED;
      if(singleHeight > 0 && pos >= singleHeight){{
        pos -= singleHeight;
        wrap.scrollTop = pos;
        if(window.parent !== window) window.parent.postMessage({{type:'scroll-cycle'}},'*');
      }}
      wrap.scrollTop = pos;
    }}
  }}
  if(pendingHTML !== null && pos < 2) applyPendingUpdate();
  requestAnimationFrame(step);
}}
requestAnimationFrame(step);

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
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    version_path = os.path.join(os.path.dirname(out_path), 'version.json')
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump({'gen': gen_ts}, f)
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Generated: {out_path}")


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    fetched = fetch_pdf() if GMAIL_USER else False

    if os.path.exists(PDF_PATH):
        data = parse_pdf(PDF_PATH)
        generate_html(data, HTML_PATH)
        if not fetched:
            print("No new email. Display refreshed.")
    else:
        print("No PDF yet. Send the Shop Schedule PDF to the Gmail inbox.", file=sys.stderr)


if __name__ == '__main__':
    main()
