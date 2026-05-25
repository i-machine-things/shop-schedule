# Standards & Practices — CodeRabbit Review Log

## 2026-05-25 — `install.sh` (PR #153 — follow-up CR findings)

**Review:** CodeRabbit rounds 2–4 on feat/installer-env-prompts
**Result:** 4 findings, all fixed.

### Findings

1. **`_get_env` stripped all quote characters, corrupting values with embedded quotes**
   - `tr -d '"'"'"` deleted every `'` and `"` byte; a value like `Bob's Shop` became `Bobs Shop`
   - Fix: replaced with `eval "printf '%s' $raw"` which correctly handles the single-quoted format written by `_set_env`

2. **`_set_env` did not enforce restrictive permissions on `.env` after writes**
   - Credentials written without enforcing file mode; world-readable on some systems
   - Fix: added `chmod 600 "$file"` in both the overwrite and append branches of `_set_env`

3. **Cron `$INSTALL_DIR` path unquoted — breaks installs with spaces in path**
   - `CRON="... $INSTALL_DIR/run_update.sh ..."` produces a broken crontab entry if `INSTALL_DIR` contains spaces
   - Fix: wrapped path in escaped quotes: `\"$INSTALL_DIR/run_update.sh\"`

4. **Initial schedule regeneration bypassed `.env`, ignoring `SHOP_NAME` / `PDF_COMPANY_NAME`**
   - Direct `GMAIL_USER='' python3 update_schedule.py` call didn't load the `.env` written by the installer
   - Fix: wrapped the call in a subshell that sources `.env` first: `( set -a; source .env; set +a; GMAIL_USER='' python3 update_schedule.py )`

---

## 2026-05-23 — `install.sh`, `install-client.sh` (PR #153 — installer env prompts)

**Review:** CodeRabbit review of feat/installer-env-prompts
**Result:** 2 findings, both fixed.

### Findings

1. **`getty@tty1` restarted from within the installer (install-client.sh)**
   - `sudo systemctl restart getty@tty1` kills the agetty instance managing the current TTY; if the installer runs from TTY1 the session is cut off mid-install
   - Fix: removed the restart call — `daemon-reload` alone is sufficient; autologin takes effect at next boot

2. **Raw user input injected into `sed` replacement in `_set_env` (install.sh)**
   - `sed -i "s|^${key}=.*|${key}=\"${val}\"|"` interpolated `val` directly; `&` and `|` corrupt the sed command, `\` and `"` corrupt the written value, and `$()` patterns execute when `.env` is later `source`d in `run_update.sh`
   - Fix: replaced sed-based update with a temp-file line rewriter; values are written as single-quoted assignments with embedded single quotes escaped as `'"'"'`, neutralising all shell metacharacters on source

---

## 2026-05-21 — `update_schedule.py` (PR #151 — WC sidebar filter)

**Review:** CodeRabbit review of feat/wc-sidebar-filter
**Result:** 1 finding, fixed.

### Findings

1. **PDF-derived values inserted raw into HTML template**
   - `sec["wc"]`, `sec["department"]`, `sec["wc_group"]`, and all job field values (`customer`, `part`, `description`, `curr_wc`, etc.) were interpolated directly into the f-string template without HTML escaping, allowing injection from malformed PDF content
   - Fix: compute `dept_e = _html.escape(sec["department"])`, `wcg_e = _html.escape(sec["wc_group"])` alongside the existing `wc_attr`; compute `je = {k: _html.escape(str(v)) for k, v in j.items()}` at the top of the job loop and use `je[...]` throughout the job row template

---

## 2026-05-18 — `server.py`, `public/install.html` (PR #150 — client kiosk installer)

**Review:** CodeRabbit review of feat/client-kiosk-installer
**Result:** 2 findings, both fixed.

### Findings

1. **Host header embedded in shell script without sanitisation**
   - `self.headers.get('Host')` was interpolated directly into `install-client.sh` via string replace; a crafted Host header could inject shell metacharacters
   - Fix: module-level `_HOST_RE` regex + `_sanitize_host(host)` function validates hostname characters (alphanum, dot, hyphen, IPv6 brackets) and port range 1–65535; falls back to `localhost:{PORT}` on any failure

2. **`navigator.clipboard.writeText` missing `.catch` and fallback**
   - Copy button promise had no error path; browsers with restricted clipboard access or non-HTTPS contexts would silently fail
   - Fix: added `fallbackCopy()` using `document.execCommand('copy')` in a temporary textarea; `.catch` on the Clipboard API call tries the fallback and shows a "Failed" state if both paths fail; both success and failure revert button text after 2s

---

## 2026-05-18 — `server.py` (PR #146 — upload page)

**Review:** CodeRabbit review of feat/pdf-upload
**Result:** 3 findings, all fixed.

### Findings

1. **Race condition on concurrent schedule uploads**
   - `process_drop.py` was triggered in a background thread with no guard; two rapid uploads would race on `DROP_DIR` with two concurrent subprocesses
   - Fix: module-level `_schedule_lock = threading.Lock()`; `_upload_schedule` acquires non-blocking — returns 409 if already running; lock released in `finally` after subprocess completes

2. **Non-atomic `pages.json` write**
   - Writing directly to `PAGES_JSON` with `open(..., 'w')` leaves a truncated/corrupt file if interrupted mid-write
   - Fix: write to `tempfile.mkstemp` in the same directory, `fsync`, then `os.replace()` to atomically swap in the new file

3. **Single-threaded `HTTPServer` blocks on long requests**
   - `HTTPServer` handles one request at a time; a slow upload would stall all other clients
   - Fix: use `ThreadingHTTPServer` (same import, same API, spawns a thread per request)

---

This file records CodeRabbit recommendations so they can be applied to future changes.
Review this file before making changes to the codebase.

---

## 2026-05-18 — `public/kiosk.html`, `public/index.html` (PR #144 — kiosk rotation shell)

**Review:** CodeRabbit review of feat/kiosk-rotation
**Result:** 3 findings, all fixed.

### Findings

1. **Live clock divs missing accessibility attributes**
   - `<div id="clock">` in `index.html` lacked `aria-live`, `aria-label`, `aria-atomic`; screen readers would not announce time updates
   - Fix: `aria-live="polite" aria-label="Current time" aria-atomic="true"` added to the element
   - Also applies to the clock in the generated `schedule.html` — fix in `update_schedule.py` HTML template when next touching that file

2. **`postMessage` handler trusted any sender for `scroll-cycle`**
   - `window.addEventListener('message', ...)` in `kiosk.html` only checked `e.data.type`; any frame (including injected content in external iframes) could trigger rotation
   - Fix: guard with `if (e.source !== schedFrame.contentWindow) return;` before processing

3. **Safety-valve timer not armed on initial render**
   - `SCHEDULE_MAX_MS` watchdog was only set inside `goToPage()`, but the schedule slide is active by default (not via `goToPage()`), so the first display had no fallback timer
   - Fix: arm `advTimer = setTimeout(advance, SCHEDULE_MAX_MS)` at the end of the `pages.json` fetch resolution when `PAGES.length > 1`

---

## 2026-05-16 — `update_schedule.py` (PR #6 — deferred schedule refresh)

**Review:** CodeRabbit review of feat/deferred-schedule-refresh
**Result:** 1 finding, fixed.

### Findings

1. **Missing null checks on querySelector results in `applyPendingUpdate`**
   - `newDoc.querySelector('.meta-info')` and `newDoc.querySelector('tbody')` were called directly without null checks; malformed/unexpected HTML from a failed fetch would throw a TypeError
   - Clearing `pendingHTML` before the null guard is critical — prevents the function from retrying on every animation frame after a failure
   - Fix: extract results into `newMeta`/`newTbody`, set `pendingHTML = null` immediately, then bail with `return` if either is null before touching the DOM

---

## 2026-05-14 — `update_schedule.py` (PR #4 — configurable PDF filename)

**Review:** CodeRabbit review of feat/configurable-pdf-filename
**Result:** 1 finding, fixed.

### Findings

1. **Empty/whitespace env var collapses PDF_PATH to BASE_DIR**
   - `os.environ.get('PDF_FILENAME', 'last_report.pdf')` does not guard against `PDF_FILENAME=` (empty) or `PDF_FILENAME=   ` (whitespace), which would set `PDF_PATH` to the repo directory and cause a crash when pdfplumber tries to open a directory
   - Fix: `os.environ.get('PDF_FILENAME', '').strip() or 'last_report.pdf'`

---

## 2026-05-12 — `update_schedule.py`, `.env.example` (PR #2 — configurable shop name)

**Review:** CodeRabbit review of feat/configurable-shop-name
**Result:** 3 findings, all fixed.

### Findings

1. **Hardcoded name in module docstring**
   - Docstring referenced "shop name" — contradicts the PR goal of removing hardcoded names
   - Fix: changed to "shop floor display"

2. **`<title>` inconsistent with `<h1>`**
   - Title used en-dash + "Foreman Schedule"; h1 used em-dash + "Foreman's Report"
   - Also: default `SHOP_NAME="Foreman Schedule"` produced "Foreman Schedule — Foreman's Report" (redundant)
   - Fix: title now uses `&mdash;` + "Foreman's Report"; default changed to "My Shop"

3. **Unquoted `.env.example` value with spaces**
   - `SHOP_NAME=Your Shop Name` may parse incorrectly in some dotenv loaders
   - Fix: `SHOP_NAME="Your Shop Name"`

---

## 2026-05-12 — `README.md` (PR #1 — add README)

**Review:** CodeRabbit review of docs/readme
**Result:** 2 findings, both fixed.

### Findings

1. **Missing language tag on env code block**
   - Fenced block with `.env` vars had no language tag — fails MD040 lint
   - Fix: changed opening fence from ` ``` ` to ` ```dotenv `

2. **Placeholder clone URL**
   - `YOUR_ORG` placeholder left in clone command
   - Fix: replaced with actual repo URL
