# Standards & Practices — CodeRabbit Review Log

## 2026-06-26 — `install.sh` (PR #260 — guest SMB installer)

**Review:** CodeRabbit flagged 4 findings: grep matching commented `map to guest` lines, root ownership lost on smb.conf temp-file swap, stale `guest ok`/`force user` values not replaced, and `echo` used for UNC backslash path.
**Result:** All 4 fixed.

### Findings

1. **`grep 'map to guest'` matched commented-out lines, skipping the `awk` insertion**
   - The original `if ! grep -q 'map to guest'` check matched comment lines like `# map to guest = ...`, so the awk-insertion branch was silently skipped on a default smb.conf, leaving guest access broken
   - Fix: `sudo grep -qiE '^[[:space:]]*map[[:space:]]+to[[:space:]]+guest[[:space:]]*='` — only matches active (uncommented) directives
   - Pattern: when grepping smb.conf for a directive, always anchor with `^[[:space:]]*` to exclude comment lines

2. **`sudo mv $tmp /etc/samba/smb.conf` preserved user ownership**
   - `mktemp` creates files owned by the running user; `sudo mv` preserves that ownership, making the system config user-writable after the swap
   - Fix: `sudo install -o root -g root -m 0644 "$tmp" /etc/samba/smb.conf && rm -f "$tmp"` — installs with explicit root ownership and mode
   - Pattern: whenever replacing a root-owned system file from a temp file, use `sudo install -o root -g root -m 0644` instead of `sudo mv`

3. **Presence-check for `guest ok` / `force user` skips normalization of stale values**
   - `grep -q 'guest ok'` passes if the key exists even as `guest ok = no`; the old value is left unchanged
   - Fix: delete all three keys (`valid users`, `guest ok`, `force user`) from the `[schedule-drop]` block first, then unconditionally append the correct values
   - Pattern: when migrating share config, always delete-then-reinsert rather than checking for key presence

4. **`echo` used for UNC path with backslashes (SC2028)**
   - `echo "\\\\hostname\\share"` — `echo` expansion of backslash escape sequences is implementation-defined; ShellCheck flags SC2028
   - Fix: `printf '\\\\%s\\share\n' "$(hostname -I | awk '{print $1}')"` — unambiguous escaping
   - Pattern: use `printf` instead of `echo` whenever the output contains backslashes

---

## 2026-06-22 — `public/pdf-viewer.html` (PR #259 — PDF viewer OOM fix)

**Review:** CodeRabbit flagged one finding: claimed `pdf.destroy()` was removed from the PDF.js 3.x API and should be replaced with `pdf.cleanup()`.
**Result:** False positive — not applied.

### Findings

1. **`pdf.destroy()` vs `pdf.cleanup()` — false positive (skipped)**
   - CR claimed `PDFDocumentProxy.destroy()` was removed; `cleanup()` is the correct method
   - Verified against the actual PDF.js 3.11.174 bundle: `destroy()` exists and delegates to `loadingTask.destroy()`, which terminates the worker and clears all resources
   - `cleanup()` only clears internal caches and does NOT terminate the worker — using it instead would leak the worker on every rotation cycle
   - Pattern: verify CR API-change claims against the actual library version in use before accepting

---

## 2026-06-19 — `public/pdf-viewer.html`, `update_schedule.py` (PR #258 — PDF viewer auto-scroll)

**Review:** CodeRabbit flagged a double-decode bug and a URL matching bug in the PDF kiosk viewer.
**Result:** 2 findings fixed, 1 false positive skipped.

### Findings

1. **Redundant `decodeURIComponent()` in pdf-viewer.html**
   - `URLSearchParams.get('url')` already percent-decodes the value; wrapping it in `decodeURIComponent()` caused double decoding and broke signed URLs containing `%25`-encoded characters
   - Fix: pass `pdfUrl` directly to `pdfjsLib.getDocument()` without wrapping
   - Pattern: never call `decodeURIComponent()` on values from `URLSearchParams.get()` — they are already decoded

2. **`endsWith('.pdf')` fails for URLs with query params or hash fragments**
   - `raw.toLowerCase().endsWith('.pdf')` misses URLs like `file.pdf?token=...` or `file.pdf#page=2`
   - Fix: strip query string and hash before checking — `raw.split('?')[0].split('#')[0].toLowerCase().endsWith('.pdf')`
   - Pattern: always strip `?` and `#` from a URL before doing a file-extension check

3. **`page.seconds` vs `page.duration` — false positive (skipped)**
   - CR claimed the config key should be `duration`; the actual config in `options.html` and `schedule.html` uses `seconds` consistently throughout
   - No change made

---

## 2026-06-02 — `process_drop.py`, `update_schedule.py` (PR #253 — PDF_FILENAME path traversal)

**Review:** CodeRabbit flagged that `PDF_FILENAME` from the environment was joined directly with `BASE_DIR` without stripping path components, allowing values like `../../etc/passwd` to escape the install directory.
**Result:** Fixed in both files.

### Findings

1. **`PDF_FILENAME` env var used without basename sanitisation**
   - `os.path.join(BASE_DIR, PDF_FILENAME)` where `PDF_FILENAME` could be an absolute path or contain `..` traversal
   - Fix: wrap the env read with `os.path.basename(...)` in both `process_drop.py` and `update_schedule.py` before joining with `BASE_DIR`
   - Pattern: apply `os.path.basename()` to any env var that is used as a filename component in a path join

---

## 2026-05-29 — `update_schedule.py` (PR #171 — CR round 3)

**Review:** CodeRabbit follow-up on feat/manual-scroll-pause-timeout (commit 713db397)
**Result:** 2 findings, both fixed.

### Findings

1. **`update_schedule.py`: two `generate_html` calls compute independent `datetime.now()` timestamps**
   - Each call assigned its own `gen_ts = int(now.timestamp())`, so `schedule.html`, `kiosk.html`, and `version.json` could carry different values if the two calls straddle a second boundary
   - Fix: compute `gen_ts = int(datetime.now().timestamp())` once in `main()` after `parse_pdf()`, pass to both calls via new `gen_ts` kwarg; function defaults `gen_ts=None` for standalone use

2. **`update_schedule.py` (`kiosk_js`): `applyKioskConfig` never re-arms the fits-screen fallback timer**
   - After the initial or periodic `/api/pages` fetch updates `PAGES` and `SCHEDULE_MAX_MS`, `_kioskOnFitsScreen` was never called, so a new advance timer was not armed until the next scroll cycle completed
   - Fix: at the end of `applyKioskConfig`, when `PAGES.length > 0` and `allow_manual_scroll !== true`, call `window._kioskOnFitsScreen()` to arm the timer immediately

---

## 2026-05-28 — `public/kiosk.html` (PR #171 — follow-up CR round 2)

**Review:** CodeRabbit follow-up on feat/manual-scroll-pause-timeout
**Result:** 2 findings, both fixed.

### Findings

1. **`public/kiosk.html`: `ALLOW_MANUAL_SCROLL` assigned with `?? false` accepts truthy non-boolean values**
   - `cfg.allow_manual_scroll ?? false` passes truthy strings through; only the literal boolean `true` should enable manual mode
   - Fix: `cfg.allow_manual_scroll === true`

2. **`public/kiosk.html`: pending `advTimer` not cancelled when config reload flips `ALLOW_MANUAL_SCROLL` to true**
   - If the 60s config poll switches to manual mode mid-cycle, the existing countdown would fire and advance the page unexpectedly
   - Fix: `if (ALLOW_MANUAL_SCROLL) { clearTimeout(advTimer); advTimer = null; }` immediately after setting the flag

---

## 2026-05-28 — `update_schedule.py`, `public/kiosk.html`, `public/options.html` (PR #171 — manual scroll flag and schedule timeout)

**Review:** CodeRabbit review of feat/manual-scroll-pause-timeout
**Result:** 3 findings, all fixed.

### Findings

1. **`update_schedule.py`: loose truthiness on `cfg.allow_manual_scroll` misinterprets string `"false"`**
   - `if(!cfg.allow_manual_scroll)` treats the string `"false"` as truthy and would incorrectly disable auto-scroll
   - Fix: `if(cfg.allow_manual_scroll !== true)` — only the actual boolean `true` disables the loop

2. **`public/kiosk.html`: `cfg.schedule_max_s` not validated before conversion to ms**
   - `(cfg.schedule_max_s ?? 300) * 1000` passes non-numeric or out-of-range values through, producing NaN or immediate timeouts
   - Fix: `parseInt` → NaN check → `Math.max(1, Math.min(v, 3600))` before multiplying

3. **`public/options.html`: `parseInt(...) || 300` fallback for `schedule_max_s` does not clamp range**
   - Zero or negative values would fall through; `|| 300` hides `0` as if it were NaN
   - Fix: explicit NaN guard then `Math.max(10, Math.min(v, 3600))` matching the input's min/max

---

## 2026-05-25 — `server.py`, `update_schedule.py`, `options.html` (PR #168 — dynamic dept colors & options page)

**Review:** CodeRabbit on feat/dynamic-dept-colors
**Result:** 5 findings, all fixed by linter before merge.

### Findings

1. **`Content-Length` header not guarded against non-numeric values (server.py)**
   - `int(self.headers.get('Content-Length', 0))` raises `ValueError` on malformed requests → unhandled 500
   - Fix: wrap in `try/except ValueError`, return 400; also reject negative values
   - Pattern: apply to every handler that reads `Content-Length`

2. **Color strings not validated before persisting or injecting into HTML (server.py, update_schedule.py)**
   - POST `/api/dept-colors` only checked key presence, not that `bg`/`accent` were valid hex — allowed injection into inline styles
   - Fix: compile `r'^#[0-9a-fA-F]{6}$'` and `fullmatch()` both fields in the API handler; also validate at render time in `generate_html()` with fallback to `_default_color()`

3. **`innerHTML` interpolation with untrusted filenames (options.html)**
   - `item.innerHTML = \`<a href="${url}">${name}</a>\`` — crafted filename executes script in admin page
   - Fix: use `document.createElement`, set `textContent` and `href`; add `rel="noopener noreferrer"` on `target="_blank"` links

4. **DELETE response status ignored before declaring success (options.html)**
   - `await fetch(...DELETE...)` without checking `res.ok` — UI showed "Reset" even on server error
   - Fix: `if (!r.ok) throw new Error(...)` inside the try block

5. **File input not cleared after upload — same file can't be re-selected (options.html)**
   - Browser suppresses `change` event when the same file is chosen again
   - Fix: `input.value = ''` after calling `onFiles()`

---

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
