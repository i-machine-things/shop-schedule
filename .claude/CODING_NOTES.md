# Coding Best Practices & Reminders

> **Style rule:** Notes must be clear and concise — 300 characters or less each. Group by topic, not by date. Whenever a PR review (CodeRabbit or human) catches a mistake, add or amend a note here right away so it isn't repeated.

## Resource Cleanup & Temporary Files

**IMPORTANT**: Always add proper cleanup code in programs to prevent lingering temp files after closing.

### Best Practices:

1. **GUI Applications (PyQt, Tkinter, etc.)**
   - Implement `closeEvent()` handler to cleanup resources on window close
   - Call `deleteLater()` on widgets to ensure proper Qt object cleanup
   - Process pending events with `app.processEvents()` before exit

2. **File Handling**
   - Use context managers (`with` statements) for file operations
   - Explicitly close file handles when not using context managers
   - Release file locks before program exit
   - Clean up temporary files in temp directories

3. **Background Threads & Workers**
   - Stop and join all background threads before exit
   - Cancel any pending operations
   - Clean up thread-specific resources

4. **Testing Cleanup**
   - After closing the program, verify the executable can be:
     - Deleted immediately
     - Moved to another location
     - Replaced with a new version
   - If the file is locked, cleanup code is missing or incomplete

### Example Implementation (PyQt6):

```python
def closeEvent(self, event):
    """Handle window close event - ensure proper cleanup"""
    # Cleanup modules/components
    for module in self.modules:
        try:
            module.cleanup()
        except Exception as e:
            print(f"Error cleaning up module: {e}")

    # Save state
    self.save_settings()

    # Accept close event
    event.accept()
    QApplication.quit()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    exit_code = app.exec()

    # Final cleanup
    window.deleteLater()
    app.processEvents()

    sys.exit(exit_code)
```

### PyInstaller Specific:

In `.spec` file, add:
```python
exe = EXE(
    ...
    bootloader_ignore_signals=True,  # Better cleanup handling
    ...
)
```

## Date: 2025-12-16
This note was created based on issues encountered with PyInstaller executables remaining locked after closing.

## CI/CD & Linting

**Keep linter flags in a config file, not duplicated across workflow YAML.** Hardcoding `--max-line-length`/`--select`/`--exclude` in multiple workflows risks silent drift; use a project-level `.flake8` instead.

**Give read-only CI jobs explicit `permissions: contents: read`.** Jobs that don't push back should declare minimal permissions instead of inheriting repo-default `GITHUB_TOKEN` scope.

**Set `persist-credentials: false` on `actions/checkout` for jobs that don't push.** Prevents the git config from retaining a writable token unnecessarily.

**Add `timeout-minutes` to CI jobs.** A hung linter/scanner invocation without a timeout can occupy a runner indefinitely.

**Fork PRs get restricted `issues: write` via `GITHUB_TOKEN`.** If this repo ever accepts external contributions, gate `gh issue create` in CI on `github.event.pull_request.head.repo.full_name == github.repository`.

**PR audits enforce an 80% docstring-coverage threshold on changed files.** Add a concise one-line docstring to every function touched by a PR, public or private.

**Bandit's B608 (`hardcoded_sql_expressions`) regex-matches SQL keywords (`select`/`update`/`delete`/...) anywhere inside an f-string, including inside `//`-comments embedded in the generated JS/HTML.** `generate_html()`'s template is one giant f-string, so plain-English wording like "single-**select**" in a code comment trips `ci.yml`'s `bandit --severity-level medium` gate even though there's no SQL anywhere near it (CWE-89, Confidence: Low — the giveaway). Verified by diffing bandit's output between `master` and the branch that introduced the word. Fix is just wording, not a `# nosec`: reword to avoid the bare keyword (e.g. "exclusive-choice" instead of "single-select"). A second, unavoidable case (the literal HTML `<select>` tag added for the Print Report's dept dropdown, matched against unrelated "from" prose thousands of lines later) couldn't be worded around; fixed instead with a same-line `# nosec B608` after wrapping the whole `html = f"""..."""` in parens -- see that commit for why the parens are required (a bare `# nosec` can't attach to any line *inside* a multi-line string literal).

**When splitting a long line inside `generate_html()`'s giant template via adjacent string-literal concatenation, the split MUST use the *same* quote style as the literal you're splitting -- mixing them produces no error, just silently wrong output.** The outer template is `f"""..."""` (triple-double); the smaller per-row builders like `print_job_rows.append(...)` are separate `f'''...'''` (triple-single) literals. Splitting a line that lives directly in the *outer* `"""`-delimited literal using a `''' f'''` break (copied from the look of the `'''`-delimited row builders) doesn't fail flake8 *or* break the AST structure -- Python just sees three literal apostrophe characters sitting inside the still-open `"""` string, and `'''`/`f'''` show up verbatim in the generated JS/HTML. Caught only by reading the actual generated output (`grep` the rendered `<script>` block, or diff a function's source before/after), not by any lint/compile check. Before splitting a long line this way, check which quote character the *enclosing* literal actually uses and match it exactly.

## Shell Scripting & Installers

**Chromium cache-size flags need `=1`, not `=0`.** Chromium treats `--disk-cache-size=0`/`--media-cache-size=0` as "use default," not zero bytes; use `=1` to force an effectively empty cache.

**Anchor `grep` checks on config files so they don't match comments.** `grep -q 'map to guest'` also matches `# map to guest = ...`; use `grep -qiE '^[[:space:]]*key[[:space:]]*='` to match only active directives.

**Use `sudo install -o root -g root -m 0644`, not `sudo mv`, to replace root-owned system config files.** A temp file from `mktemp` is user-owned; `mv` preserves that ownership after the swap.

**Delete-then-reinsert config keys rather than checking presence.** `grep -q 'guest ok'` passes even when the value is wrong (`guest ok = no`); remove the key first, then unconditionally append the correct value.

**Use `printf`, not `echo`, for output containing backslashes.** `echo`'s backslash-escape expansion is implementation-defined (ShellCheck SC2028); `printf` is unambiguous.

**Don't strip quotes from env values with `tr -d` — and never `eval` to unwrap them.** Both corrupt or execute embedded content (e.g. `Bob's Shop`, or arbitrary shell code). Write values without shell-quoting in the first place, or unwrap with a non-evaluating parser instead.

**Quote path variables inside generated crontab entries.** An unquoted `$INSTALL_DIR` breaks the cron line if the install path contains spaces.

**Source `.env` before invoking scripts that depend on it during install.** Calling a script directly right after writing `.env` skips its vars; wrap the call in a subshell that sources `.env` first.

**Quote any `.env` value containing a backslash.** `run_update.sh` does `source .env`; an unquoted backslash (e.g. a SQL Server named-instance host like `SRV\INSTANCE`) gets silently stripped by bash during sourcing. Wrap in single quotes: `JOBBOSS_DB_HOST='SRV\INSTANCE'`.

**Pin `python-tds` to `1.13.0`.** 1.14.0+ imports `typing.Protocol`/`TypedDict` directly, which don't exist in Python 3.7 -- this board's Debian Buster stock `python3`. 1.13.0's `connect()` API is otherwise identical (verified against the real DB).

**`pytds.connect()` raises `ValueError` if a named-instance `dsn` (e.g. `SRV\INSTANCE`) and an explicit `port=` are both given.** Strip the instance suffix from the host when a static port is configured instead -- you can't resolve-by-instance-name and connect-to-a-fixed-port at the same time. CodeRabbit catch, confirmed in pytds source (`tds_base.py`).

**Don't `systemctl restart getty@tty1` from inside an installer running on that TTY.** It kills the current session mid-install; `daemon-reload` alone is enough — autologin applies at next boot.

**Guard env vars with `.strip() or default`, not just `.get(key, default)`.** An empty or whitespace-only value (e.g. `FILENAME=` ) is non-empty to `.get()` and slips through, producing a broken path.

**Removing an installer-provisioned feature must also retire it on existing installs, not just stop provisioning it on new ones.** `install.sh`/`install.ps1` dropped the SMB `schedule-drop` share setup (PR #284), but re-running either installer on an already-provisioned box left the old share and its ACL/Samba config live -- an upgrade silently didn't remove the thing being removed. Fix: on run, check for the specific resource this installer previously created (match by path, not just by name, in case it was repointed) and retire only that -- never touch unrelated shares or disable shared services (`smbd`/`nmbd`) wholesale, since the host may use them for something else. CodeRabbit catch on PR #284.

**`FileSystemSecurity.RemoveAccessRule()` does a rights SUBTRACTION against any rule for the same identity+inheritance, not an exact-match removal -- verified directly, not just reasoned about.** On a folder with only an unrelated `Everyone:(OI)(CI)(R)` grant (not the specific rule being "removed"), `RemoveAccessRule(ModifyRule)` still returns `$true` and rewrites that grant down to a near-empty `Everyone:(OI)(CI)(S)` ACE -- silently corrupting an admin's unrelated grant instead of leaving it alone. `RemoveAccessRuleSpecific()` is the exact-match method (identity+rights+inheritance+propagation+type all equal, or no-op); it has no return value, so detect whether anything was actually removed by comparing `$Acl.Access.Count` before/after. CodeRabbit catch on PR #284 (`install.ps1`'s legacy-SMB-share ACL cleanup), confirmed with a real `Get-Acl`/`Set-Acl` round trip against both an exact-match folder and an unrelated-grant one before pushing.

## Security

**Never interpolate raw user input into a `sed` replacement pattern.** `&`, `|`, backslashes, and `$()` in the value corrupt the sed command or execute later on `source`; rewrite lines via a temp file and single-quote values instead.

**Sanitize filename env vars with `os.path.basename()` before joining paths.** An unsanitized value like `PDF_FILENAME` could contain `../` traversal or an absolute path, escaping the install directory.

**HTML-escape all externally-derived values before interpolating into an HTML template.** Malformed PDF/user content injected raw into an f-string template can inject markup; use `html.escape()` on every field.

**Validate hex color strings server-side and again at render time.** User-supplied `bg`/`accent` values must match `^#[0-9a-fA-F]{6}$` before persisting or injecting into inline styles, to prevent CSS/HTML injection.

**Build DOM nodes with `createElement`/`textContent`, not `innerHTML` template strings, for untrusted data.** A crafted filename in an `innerHTML` template can execute script; add `rel="noopener noreferrer"` on any `target="_blank"` link too.

**`chmod 600` any file immediately after writing credentials to it.** Files created by an installer can default to broader permissions on some systems; enforce restrictive mode on every write path, not just the first.

**Sanitize the `Host` header before using it in a generated script or config.** Validate against an allowlist regex (hostname chars, IPv6 brackets, port 1-65535) and fall back to a safe default on any failure.

**Verify `event.source` in `postMessage` handlers.** Without `if (e.source !== expectedWindow) return;`, any frame — including injected content in an iframe — can trigger the handler's action.

**`pytds.connect()` is plaintext unless `cafile` is passed — confirmed in source (`tds.py`'s prelogin handling).** Without `cafile`, `login.enc_flag` is `ENCRYPT_NOT_SUP` and the whole session (not just login) is cleartext if the server doesn't force encryption. `cafile` set + `enc_login_only=False` (default) requests full-session TLS; requires `pyOpenSSL`. CodeRabbit Major finding on `jobboss_db.py`; added as opt-in `JOBBOSS_DB_CAFILE` rather than forced, since forcing it would break the already-deployed Pi until a DBA exports the cert.

**Audited `jobboss_db.py` for SQL injection (e.g. `DROP TABLE` as a "username") -- no vulnerability found.** Both queries are static SQL text; neither ever interpolates a value into the query string itself. Repo-wide grep confirms `jobboss_db.py` is the only file that executes SQL.

**`_QUERY` binds exactly one value (`cutoff`, a `datetime`) via pytds's `%s`/`cursor.execute(query, (cutoff,))` placeholder; `_BACKLOG_QUERY` has no placeholder and runs via `cursor.execute(query)` with zero params.** Neither builds SQL text with `%`/`.format()`/f-strings.

**`DB_USER`/`DB_HOST`/`DB_NAME`/`DB_PASS` (from `.env`) are passed to `pytds.connect()` as TDS-protocol connection fields, not SQL text.** A hostile value (e.g. a "username" containing `DROP TABLE`) can only fail authentication -- it never reaches a query.

**Bandit B608 on `update_schedule.py`'s `html = f"""..."""` template is a confirmed false positive, not a real SQL-injection risk.** Its regex is `select\s.*from\s` with `re.DOTALL`, scanned across the *entire* f-string's literal text joined together -- it matches `<select id="print-select-dept">` against an unrelated `// Pause/resume from kiosk shell` comment thousands of lines later; no query is built anywhere in this file (see the audit above -- `jobboss_db.py` is the only file that executes SQL). Suppressed with a same-line `# nosec B608`, which requires wrapping the f-string in `html = (f"""..."""` / `""")  # nosec B608` -- a bare `# nosec` can't attach to any line *inside* the literal (every line is string content, not a comment token), so the trailing comment has to land on the physical line holding the closing `"""`.

## Concurrency & File I/O

**Include microseconds in timestamp-based filenames.** `strftime('%Y%m%d_%H%M%S')` collides when two files are processed within the same second, silently overwriting the earlier one; add `%f`.

**Guard background subprocess triggers with a non-blocking lock.** Two rapid uploads can race on the same working directory; acquire the lock and return 409 if already running, release in `finally`.

**Write JSON config atomically: temp file + fsync + `os.replace()`.** Writing directly to the target path leaves a truncated/corrupt file if the process is interrupted mid-write.

**Delete the `.tmp` file on write failure, then re-raise.** An atomic temp-file-then-`os.replace()` write that hits `OSError` mid-write leaves an orphaned `.tmp` file behind; wrap in `try`/`except OSError: os.unlink(tmp); raise` so the error still propagates but doesn't litter the disk. CodeRabbit catch on `generate_json()`.

**Use `ThreadingHTTPServer`, not `HTTPServer`, for anything handling uploads or slow requests.** Same import/API, but a slow request won't stall every other client.

## Kiosk / Scroll Timer Logic

**Use strict `=== true` for boolean config flags, not `??`/truthiness.** `cfg.flag ?? false` or `if (!cfg.flag)` mishandle truthy strings (even `"false"`); only the literal boolean `true` should switch behavior.

**Validate and clamp numeric config values pulled from JSON/query params.** `parseInt(...) || 300` silently replaces `0`/`NaN` with 300 and lets truthy negatives through unchanged; NaN-check explicitly, then `Math.max(min, Math.min(v, max))` before using as a timeout duration.

**Re-arm fallback/advance timers immediately after a config reload changes scroll settings.** Otherwise a stale timer window persists until the next scroll cycle completes.

**Cancel pending timers immediately when a config reload changes mode.** If a poll switches to manual scroll mid-cycle, clear the existing advance timer right away or it still fires unexpectedly.

**Arm watchdog/fallback timers at initial render, not only inside the state-transition function.** A timer set only inside `goToPage()` never starts if the first view is active by default.

**Compute a shared timestamp once and pass it to every function call that needs it in that cycle.** Two independent `datetime.now()` calls in the same operation can straddle a second boundary and disagree.

**Clear pending state before the null guard, not after.** If DOM query results are null from malformed fetched HTML, clear the pending flag first, or the function retries on every animation frame.

**A `today + N` exclusive cutoff's last-included day is `today + N - 1`, not `today + N`.** `matchesWindowAndMode()`'s cutoff (`>=` exclusive) correctly caps the Schedule Window at `today + viewDays`, but `printDateRangeText()`'s "thru" label computed that same cutoff date and displayed it as if it were included -- off by one, claiming a day the filter actually excludes. CodeRabbit catch on PR #296.

## Accessibility

**Custom `<div>` controls need `role`, `tabindex`, a keydown handler, and `:focus-visible`.** Any `<div>` replacing a native interactive element (e.g. a drop zone) must remain keyboard-operable.

**Add `aria-live="polite" aria-atomic="true"` to elements that auto-update (clocks, live status).** Screen readers otherwise never announce the changing content.

## JavaScript Patterns

**Never wrap `URLSearchParams.get()` values in `decodeURIComponent()`.** They're already percent-decoded; double-decoding breaks values containing `%25`-style sequences.

**Strip `?` and `#` before checking a URL's file extension.** `url.endsWith('.pdf')` misses `file.pdf?token=...` or `file.pdf#page=2`.

**Check `res.ok` before reporting success on a `fetch` call.** Ignoring the response status let the UI show success even when the server returned an error.

**Reset `input.value = ''` after handling a file upload.** Browsers suppress the `change` event when the same file is reselected without clearing the input first.

**Add `.catch` and a fallback for `navigator.clipboard.writeText`.** It fails silently in browsers with restricted clipboard access or non-HTTPS contexts; fall back to `document.execCommand('copy')`.

**Flagged, not fixed (CodeRabbit, PR #290): `scheduleMidnightRefresh()`'s `setTimeout` is computed once from the local date/time at call time, so a timezone change on the device wouldn't retrigger it early.** Not fixing: these are fixed, stationary kiosk/server devices (no travel, no timezone reconfiguration in normal operation) — the scenario this guards against doesn't occur for this deployment model. Revisit if that assumption changes (e.g. a portable/VM-hosted deployment where the host clock's timezone could change under the running page).

## Print Output (CSS)

**Firefox has never implemented CSS Paged Media's `@page` margin boxes (`@top-right` etc.) -- only Chromium/Edge have.** A real user printing from Firefox saw the page-number box render as nothing at all (not wrong, just silently absent) even though it worked perfectly in headless Chromium testing -- an engine gap this wide doesn't surface in a Chromium-only test harness, so cross-browser print features need at least one real check in the *other* engine, not just Chromium automation. (An earlier note here, now superseded, had confirmed Chromium 156 supports `@page` margin boxes -- true, but incomplete: it never occurred to check Firefox at all.) Fixed by dropping `@page`/`@top-right` entirely and computing pagination in plain JS instead: `paginatePrintOutput()` measures each section/row's real height via `getBoundingClientRect()`, decides page boundaries itself, and stamps an ordinary (non-margin-box) `.print-page-num` element plus a `break-before:page` class at each one -- works identically in both engines since none of it depends on Paged Media.

**`getBoundingClientRect()` only sees styling the element actually has *right now* -- rules scoped inside `@media print` don't apply outside of real printing, even on an element positioned off-screen specifically so it can be measured ahead of time.** `paginatePrintOutput()` needs real row/header heights *before* `window.print()` is called, but `#print-output`'s content styling (`.print-table`, `.print-row`, `.print-hdr`, etc.) used to live entirely inside `@media print { ... }` -- correct for what gets drawn, useless for what JS can measure beforehand, since the measurement pass runs in ordinary screen context. Fixed by moving that styling out of `@media print` to always-on rules; `#print-output` itself stays invisible outside of printing via `visibility:hidden` (not `display:none`, which would zero out all its children's heights too), so none of this is visible on screen.

**A CSS `break-before:page` must be on the element that starts the new page, not on the element right after it.** Had the break on each page's actual content (a `.print-section` or a split-off chunk `<table>`) while inserting that page's `.print-page-num` label as a sibling *before* it -- the label isn't what has the break, so it stayed on the *previous* page as "content that still fit," stranded one page ahead of the content it was labeling. Move the `break-before:page` class onto the label itself.

**`element.cloneNode(true)` clones whatever classes are on the element *at that moment* -- hide-then-clone silently clones the hidden class too.** Splitting an overflowing section's rows into a new chunk `<table>` added `.print-chunked-out` (`display:none`) to the original rows *before* cloning them into the new table, so every clone inherited that class and rendered invisible -- the new page looked like it had the right column headers and nothing else. Clone first, hide the originals after.

**A per-row/section JS pagination budget derived from "CSS `in` = 96px" math (e.g. a Letter page's 10in content height = 960px) still needs a real safety margin, not just the raw arithmetic.** `getBoundingClientRect().height` doesn't include an element's own margins, and several small per-element shortfalls like that compound once multiple sections' headers/footers share a single page -- a page's real, empirically-observed capacity ran about 90px under the theoretical 960px-minus-header number once three sections were packed onto one page together. Tuned against a deliberately worst-case render (three short sections plus one long one, forcing both inter-section sharing and an intra-section overflow split) rather than trusting the arithmetic alone.

**A JS pagination budget computed from an assumed page size/orientation is only valid if the real print output is pinned to that same size/orientation -- there's no API that reports what the user actually selected in the print dialog.** `paginatePrintOutput()`'s byte-for-byte page-count math assumes Letter portrait; nothing in JS can read back the print dialog's paper-size/orientation choice to adapt to it, so the only way to keep the budget trustworthy is `@page { size: letter portrait; ... }` forcing that one layout, not attempting to detect or adapt to whatever was selected. CodeRabbit catch on PR #296.

**When a JS pagination budget walks past the last content on a page, it still has to account for anything repeating/trailing after that content, not just subtract already-walked items.** `paginatePrintOutput()`'s per-row budget loop correctly tracked rows but never subtracted the `<tfoot>` ("Total Rem Hrs") row's height afterward, silently overestimating how much space was left for whatever came next (the following section, if one shares the page). Subtract trailing elements' heights once, right after the loop that produces them -- exactly once, since it's the SAME tfoot whether the section split into chunks or not (only its final location changes). CodeRabbit catch on PR #296.

**A multi-page table split into separate `<table>` elements (one per physical page, built by `paginatePrintOutput()`) must declare identical column widths across every one of them, or text can wrap differently per-table and silently invalidate the row heights that were measured before the split.** Each `<table>`'s columns are otherwise auto-sized from that table's own cell content -- a continuation chunk containing a different subset of rows than the original can get different column widths, hence different wrapping, hence a different real height than whatever was measured against the original table. Fixed with a `<colgroup>` of fixed percentage widths (identical across every chunk, since it's cloned onto each one) plus `table-layout:fixed`, which locks column sizing to those declared widths regardless of a given table's content. CodeRabbit catch on PR #296.

**A repeating per-page heading (department/work-center name) belongs on every continuation page of a long section, not just the page where that section starts.** `paginatePrintOutput()` originally only repeated the column-header row (`<thead>`) on a section's own overflow continuation pages, matching what plain `<table>` pagination already did natively -- but a reader starting mid-list on page 3 of a long work center still needs to see *which* department/work center it is, same as page 1 shows. Fixed by cloning `.print-sec-hdr` onto every continuation chunk too (not just the first page), and reserving its height in that chunk's budget. CodeRabbit catch on PR #296.

**A barcode column's width has to be sized for the longest value it will ever encode, not for its label text.** The Oper column looked plenty wide for "OP1" plus a short number, but Code128's rendered width scales directly with character count (`code128Svg(text, 1, 10)` -- 1px/module, ~11 modules/character) -- an 8+ digit `op_key` (`Job_Operation`'s real IDs grow unbounded) overflowed visibly into the Oper Desc column's text. Widened from 10% to 17% of the table, confirmed against both an 8-digit and a 10-digit op_key with room to spare. CodeRabbit catch on PR #296.

## Server & HTTP

**Guard `int(Content-Length)` parsing with try/except; return 400 on failure or negative values.** Malformed requests otherwise raise an unhandled `ValueError` and produce a 500.

**`jo.Description` (operation description) must be aliased to avoid colliding with `j.Description` (job description) in the same query.** Both `Job` and `Job_Operation` have a `Description` column; `jobboss_db.py`'s `_QUERY` already selects `j.Description` unaliased for the job's own description, so the new operation-level field is `jo.Description AS Oper_Desc` -- pytds's `as_dict=True` keys by column name, and an unaliased second `Description` would have silently overwritten the first in the result row.

## PDF Handling

**Verify CodeRabbit API-change claims against the actual library version in use.** CR claimed `PDFDocumentProxy.destroy()` was removed in PDF.js 3.x; it wasn't — `cleanup()` doesn't terminate the worker and would have leaked it.

**Every job-record initializer branch in `parse_pdf()`'s state machine must set the same keys.** The `state==0` happy path and the `state==1` recovery branch (an "unexpected line" that turns out to be a new job line, not a customer line) each build their own `job_data` dict from scratch — adding a field to one without the other means any job reaching the template via the branch you missed hits a `KeyError` on an unconditional `je["<field>"]` lookup in `generate_html()`. Happened with `oper_desc` (PR #282): the recovery branch was missed when the field was added to the happy path. Grep both initializers whenever adding a new job field, not just the first one you find.

## Work Center Backlog Calculation

**Call it "backlog," not "load."** Shipped the first version as `load_weeks`/"wk load"; the actual shop-floor term for queued work at a work center is backlog, not load. Renamed throughout (`_work_center_backlog_days()`, `_BACKLOG_QUERY`, `apply_work_center_backlogs()`, `.wc-backlog`, "wk backlog") after the fact rather than caught before shipping -- worth getting shop-floor terminology right from a domain person before building the feature, not after.

**An overdue-but-still-open job (`sch_end` already in the past, `Status <> 'C'`) means that work center is *behind*, not free starting at that stale date — went through two rounds to get this right.** Round 1 only fixed the reported gap *size* (floor it at today instead of measuring from the stale date: "open now (1.1 wk gap)" → "open now (3 day gap)" when the next job was really only 3 days out). Round 2 (real user feedback: a work center playing catch-up on old jobs was still showing a false gap) fixed the deeper issue -- an overdue job's *occupied interval* itself needs clamping to `[sch_start, max(sch_end, now)]` in `_work_center_backlog_days()`, not just the reported gap number. Without that, a near-term job starting shortly after the overdue one reads as a gap (idle time) right when the work center is actually going to spend that time catching up on the backlog, not sitting idle. The round-1 fix (`max(queue_end, now)` on the reported size) became redundant once the clamp was applied at interval-construction time -- `queue_end` can no longer be stale at all -- and was removed rather than left as dead-but-harmless code. Confirmed genuine future gaps past the catch-up work still detect correctly (synthetic case 4) -- this isn't gap detection getting suppressed generally, just the illusory ones caused by stale dates.

**`backlog_days`/`gap_days` are integer days, not fractional weeks (`backlog_weeks`/`gap_weeks` in the first version).** Requested after shipping: shop floor staff wanted "2 wk 3 day," not "2.3 wk" -- a decimal week doesn't translate to an actual calendar date at a glance. Storing raw days (exact) and formatting with `_format_weeks_days()` (`divmod(days, 7)`, omitting a zero component) avoids compounding rounding on top of an already-rounded decimal, which storing pre-rounded fractional weeks would have.

**Work center backlog stops at the first gap of ≥1 week between jobs, rather than reporting the furthest-out job's end date.** Walk `[sch_start, sch_end]` intervals in start order; a gap here is real idle time at that work center, which sales needs visible to fill — reporting the far job's date instead would hide it. See `_work_center_backlog_days()`.

**`_work_center_backlog_days()` returns `(backlog_days, gap_days)`, not just `backlog_days`.** A bare "when it opens" without the gap's *size* could schedule a 2-week job into a 1-week hole. `gap_days` is `None` when no gap of at least one week is found among jobs with parseable start and end dates; otherwise, it gives the first gap's size.

**`jobboss_db.py` runs two unbounded queries for one reason: avoid paying `CROSS APPLY`'s cost twice.** The main query uses `CROSS APPLY` for `Rem_Hrs`/`NumOps_Ahead`/`Curr_WC`; `_BACKLOG_QUERY` omits it. `fetch_from_db()` groups both result sets by `(department, wc_group, wc)`, then calculates `backlog_days`/`gap_days` from the backlog rows and attaches them to each section. `JOBBOSS_DAYS_AHEAD` (the old display-day cutoff that this split originally worked around) is gone — the Schedule Window PR moved that limiting client-side.

**Unverified risk (CodeRabbit, PR #285): the main query's `CROSS APPLY` (`Rem_Hrs`/`NumOps_Ahead`) now runs over the entire open backlog every 15-minute update cycle, not a ~14-day slice.** Cost scales with total open-job-operation count; depends on whether `Job_Operation` indexes let SQL Server seek instead of scan per row — not measurable without a real JobBoss SQL Server. Needs a timing run against real backlog size before closing out; not rewritten speculatively without one.

**`_work_center_backlog_days()`/`_parse_sched_date()` live in `jobboss_db.py`, not `update_schedule.py`, despite being used by both the DB and PDF paths.** `update_schedule.py` already does `import jobboss_db`; the reverse would be circular. `apply_work_center_backlogs()` in `update_schedule.py` now only fills in `backlog_days`/`gap_days` for sections that don't already have them (i.e. the PDF path, which has no equivalent wide query available and keeps the narrower, `sec['jobs']`-based calculation as a known, accepted limitation) — it skips any section the DB path already computed via the wide query, so the DB path's correct value is never silently overwritten by a re-derived, truncated one.

**Verified the gap-detection boundary with synthetic data before pushing, not just read through it** — eight cases (no gap, gap >1wk, the overdue-catch-up scenario specifically, a genuine gap past some overdue backlog that must still be detected, gap <1wk that must NOT stop early, empty job list, all-overdue with no next job, gap exactly at the 7-day threshold) all matched hand-computed `(backlog_days, gap_days)` pairs. Cheap and worth doing for any date-arithmetic-with-a-threshold change; off-by-one-week errors here are exactly the kind of bug that looks right on a quick read -- neither the overdue-catch-up case nor the still-must-detect-a-real-gap case were caught by earlier rounds of this test suite, since none of those cases had a job already in the past.

## JobBoss Schema Gotchas

**Every `jobboss_db.py` query change that touches a new table needs a matching `GRANT SELECT` in README's `shop_schedule_ro` setup script, plus an explicit upgrade step for already-provisioned logins.** Adding the `Delivery` OUTER APPLY (Ship Qty/Promised Date) without updating the documented login's grants would leave every existing install's read-only login unable to actually run the new query. CodeRabbit catch on PR #296.

**`Job_Operation`'s real "Operation Key" (what JobBoss's own UI calls it, and what a shop-floor scanner should read) is the `Job_Operation` column -- yes, a column named identically to its own table -- not the decoy-named `Job_OperationKey` column that sits right next to it (ordinal 1 vs. 2 in `jobboss-tables.xlsx`'s schema dump).** Picked `Job_OperationKey` first on name alone and shipped it in the Print Report's op-code barcode; wrong on the first try, caught only by the user comparing a live barcode's scanned value against JobBoss's own UI for a real job. Don't trust a JobBoss column name's plain-English reading when a near-identical alternative exists on the same table -- verify against `jobboss-tables.xlsx` (or live data for a known job) before relying on one.

**DPAPI's `CurrentUser` scope is incompatible with a SYSTEM-run scheduled task encrypting/decrypting across different accounts.** `protect-db-password.ps1` runs interactively as whoever's logged in; `ShopScheduleServer`/`ShopScheduleUpdate` run as `SYSTEM` (see `install.ps1`). A `CurrentUser`-scoped blob from the first can't be decrypted by the second. Use `LocalMachine` scope instead -- any local account can decrypt it, which is weaker than `CurrentUser` but matches this cross-account reality; still far better than the plaintext it replaces.

**.NET's `System.Security.Cryptography.ProtectedData` (PowerShell, via `Add-Type -AssemblyName System.Security`) and pywin32's `win32crypt.CryptProtectData`/`CryptUnprotectData` (Python) are the same DPAPI primitive.** No need for pywin32 on the PowerShell encrypt side -- only the Python decrypt side (`jobboss_db.py`, which has no .NET available) needs that dependency, and only on Windows.

**Resolve an optionally-encrypted credential lazily, inside the function that uses it, not at module import time.** A `dpapi:`-prefixed `JOBBOSS_DB_PASS` left in `.env` would otherwise break importing `jobboss_db` at all -- including on Linux, or during a Gmail-path run that never touches the DB. `_resolve_db_pass()` is only ever called from inside `fetch_from_db()`'s own `try`, so a decrypt failure is reported the same way as any other connection failure.

**Gating Gmail auto-fetch on Windows must not also block manual PDF drop/upload.** First pass returned early from `main()`'s whole non-DB branch on Windows, which also silently broke `options.html`/SMB manual uploads -- those go through the same `else` branch via `parse_pdf()`, with no dependency on Gmail at all. Fix: only skip the `fetch_pdf()` IMAP call itself on Windows; still fall through to parsing an already-present PDF either way.

**Modern Windows has no equivalent to Samba's guest access.** The SMB1 guest-fallback removal in the 1709 update means `New-SmbShare` can't offer a true no-password share the way `install.sh`'s Samba config does — `install.ps1`'s `schedule-drop` share always requires a real Windows account on that PC. Documented as a real limitation, not something to fake with registry hacks.

**A native .exe's non-zero exit code does NOT raise a PowerShell terminating error on its own**, even with `$ErrorActionPreference = 'Stop'` — that setting only affects cmdlets/script errors. This cuts both ways: `run_update.ps1` doesn't need bash's `|| true` equivalent around `process_drop.py` since a failure there already can't halt the script, but `install.ps1`'s `pip install` calls needed an explicit `if ($LASTEXITCODE -ne 0)` check added — without it, a failed dependency install silently let the script continue on to register and start scheduled tasks with a venv that can't import its own packages. CodeRabbit catch on PR #277; same underlying mechanism as the `process_drop.py` case, opposite correct handling.

**`icacls /inheritance:r /grant:r` does not reset an ACL — it only removes *inherited* ACEs and replaces the *named accounts'* explicit grants.** Other pre-existing explicit ACEs on a file (e.g. a broader grant left over on an existing `.env` this installer reuses) survive untouched, which could leave `JOBBOSS_DB_PASS` more readable than intended despite the command looking like a full lockdown. Run `icacls $Path /reset` first to clear back to default inherited ACLs, then apply the restrictive `/inheritance:r /grant:r`. CodeRabbit security catch on PR #277, confirmed against Microsoft's icacls docs.

**`New-SmbShare -FullAccess` sets only the SHARE-level permission, not the NTFS filesystem ACL — both layers gate actual access.** A folder shared with `-FullAccess 'Everyone'` can still refuse writes if its NTFS ACL (inherited from its parent) doesn't separately grant the connecting account write access -- the share looks reachable (authenticates fine) but dropping a file fails with access denied. Grant the matching NTFS permission on that specific folder too (`icacls $Path /grant 'Everyone:(OI)(CI)M'`), scoped to just that folder, not the whole install directory. CodeRabbit catch on PR #277.

**Windows PowerShell 5.1's `Get-Content` defaults to the system ANSI codepage for a BOM-less file, not UTF-8.** A `.env` saved as UTF-8-without-BOM (common from most editors) containing any non-ASCII character would decode wrong and silently corrupt that value. Always pass `-Encoding UTF8` explicitly when reading a file another tool might have saved as UTF-8. CodeRabbit catch on PR #277 (`Import-DotEnv`); same principle already noted elsewhere in this file for the write side (`Set-Content`/`Out-File`).

**A value written with embedded single quotes into the shared `.env` format must stay valid bash, not just valid for this project's own PowerShell reader.** `SHOP_NAME='Joe's Garage'` parses fine under this project's own lenient `Import-DotEnv` (naive first/last-char quote stripping) but is a bash syntax error (unterminated quote) when `run_update.sh` sources it on Linux. Fixed by matching `install.sh`'s own `_set_env()` escaping exactly: replace an embedded `'` with `'"'"'` (close-quote, double-quoted literal quote, reopen-quote) -- then taught `Import-DotEnv` to reverse that same sequence back to a literal `'`, so a value survives a full round trip through either platform's writer and either platform's reader, not just bash's `eval`-based one. Verified directly (write → read back through the real `Import-DotEnv`, not just reasoned about) before pushing. CodeRabbit catch on PR #277.

**`-RepetitionDuration ([TimeSpan]::MaxValue)` on a scheduled task trigger risks failing to serialize into Task Scheduler's XML.** Use a large-but-concrete span instead, e.g. `(New-TimeSpan -Days 3650)`, for "repeat indefinitely."

**`install.ps1` requires Administrator; `install.sh` refuses to run as root.** Not a contradiction — Windows's privilege model is the opposite of sudo-per-command, and scheduled tasks + SMB shares both need an elevated session to register at all.

**`dotenv.ps1`'s parser matches bash's single-quote semantics (strip one layer of matching quotes, no escape interpretation inside) on purpose.** Keeps one `.env` file portable between `run_update.sh` and `run_update.ps1`, including backslash-containing values like a named SQL Server instance (`JOBBOSS_DB_HOST='SRV\INSTANCE'`).

**Use `pythonw.exe`, not `python.exe`, for the Windows HTTP server's scheduled task.** `pythonw.exe` (ships alongside `python.exe` in every stock venv) runs with no console window, the Windows equivalent of a systemd service with no attached TTY.

**A Task Scheduler `AtLogOn` trigger has no ordering guarantee against a separate `AtStartup` task**, unlike systemd's `After=` unit dependency. `kiosk-launch.ps1` retries until the HTTP server actually answers instead of a fixed sleep, mirroring `install-client.sh`'s existing retry loop rather than `foreman-kiosk.service`'s flat 5s sleep (which only works because of the `After=` ordering this setup doesn't have).

**Checking `$LASTEXITCODE` once after a native command is not the same as checking it after every native command in a sequence.** The `.env` lockdown runs `icacls /reset` then `icacls /inheritance:r /grant:r` back to back; only checking after the first (or neither) lets a failed second call leave a broader ACL than intended while the installer still proceeds to print `=== Done ===`. Both calls need their own `if ($LASTEXITCODE -ne 0) { Write-Error ...; exit 1 }`. CodeRabbit catch on PR #277, second review pass.

**Deliberately not adding the same `$LASTEXITCODE` check to the `incoming/` SMB-share `icacls` call (line ~221) that was just added to the `.env` one above.** Same underlying bug (unchecked native-command exit code), but SMB drop is being deprecated and removed in the next major version per explicit user direction — not worth hardening an error path on a feature that's going away. Logged per Rule 5 instead of silently dropping the finding; revisit only if SMB outlives that plan. CodeRabbit catch on PR #277, second review pass.

**A stacked PR that copies/refactors a function out to a shared file freezes that function's bugs at the moment of the copy -- a later fix to the original, still-duplicated version on the base branch does not propagate.** PR #278 branched off `feat/windows-server-port` and moved `install.ps1`'s local `Set-EnvFileValue` into `dotenv.ps1` as `Set-DotEnvValue`, before that base branch got a *later* commit adding embedded-single-quote escaping and `-Encoding UTF8` to the (still-local, not-yet-moved) original. Merging master into #278 picked up that later commit's other changes cleanly (no conflict in `dotenv.ps1` -- the two versions had already diverged into different files), but silently left `Set-DotEnvValue` without either fix, reintroducing both a known bash-sourcing break (`SHOP_NAME='Joe's Garage'`) and the ANSI/UTF-8 misread. Caught by re-deriving the fix's own history (`git log`/`git show` on the function across both branches) rather than trusting a clean `git merge` to mean "nothing to check" -- a clean auto-merge only means git found no *textual* overlap, not that both branches' bug fixes ended up in the result. Verified the reinstated fix with a real `Set-DotEnvValue`/`Import-DotEnv` round trip plus a bash `source` of the same written line, not just by re-reading the diff.

**`Set-Content -Encoding utf8` in Windows PowerShell 5.1 always writes a UTF-8 BOM** (unlike PowerShell 7's separate `utf8NoBOM`) -- verified directly by reading the written file's raw bytes. A BOM on `.env`'s first line breaks bash's `source` outright: the BOM bytes glue onto the first `KEY=value` as one token ("command not found"), and that variable silently never gets set -- could be `JOBBOSS_DB_PASS`. Use `[System.IO.File]::WriteAllLines($Path, $content, (New-Object System.Text.UTF8Encoding $false))` instead. CodeRabbit catch on PR #278 (`Set-DotEnvValue`).

**A key-match regex for rewriting a `.env` line must tolerate the same leading whitespace/whitespace-around-`=` that the reader already tolerates, or an indented existing key silently gets duplicated instead of replaced.** `Set-DotEnvValue`'s `^$Key=` match didn't handle an indented `   JOBBOSS_DB_PASS=...` line (`Import-DotEnv` trims the whole line before matching, so it reads such a line fine) -- the writer would then append a second, unindented line instead of replacing it, leaving the OLD value (e.g. a plaintext password `protect-db-password.ps1` just "encrypted") still sitting in the file right next to the new one. Fixed with `^\s*$([regex]::Escape($Key))\s*=`, verified against a real indented-key file (confirmed exactly one line survives, with the new value). CodeRabbit catch on PR #278.

**A "has this already been encrypted?" check must verify the value actually decrypts, not just match a marker prefix.** `protect-db-password.ps1` skipped re-encryption whenever `JOBBOSS_DB_PASS` started with `dpapi:` -- but a legitimate plaintext password that itself happens to start with `dpapi:` (e.g. `dpapi:hunter2`) would pass that check and get left in plaintext, then later fail to connect when `jobboss_db.py`'s `_resolve_db_pass()` tries to `CryptUnprotectData` it as if it were real DPAPI data. Fixed by attempting `ProtectedData]::Unprotect` inside a `try`/`catch` and only treating it as already-encrypted if that call actually succeeds; anything else (bad base64, not a valid DPAPI blob) falls through to being encrypted normally. Verified end-to-end against a real `.env`: a plaintext password encrypts on first run, and a second run against the now-encrypted value correctly no-ops. CodeRabbit catch on PR #278.

## Documentation & Config Hygiene

**Quote `.env.example` values that contain spaces.** `KEY=Value With Spaces` may parse incorrectly in some dotenv loaders; use `KEY="Value With Spaces"`.

**Always tag fenced code blocks in Markdown with a language.** An untagged block (e.g. raw `.env` vars) fails MD040 lint; use e.g. ` ```dotenv `.

## Scheduled Refresh Gating

**A `[start, end)` active-hours window read from `.env` must validate `start < end` itself -- an inverted or equal pair (e.g. a typo'd `START=17 END=5`) silently makes the gate always-false, disabling the refresh entirely with no error anywhere.** Not just a malformed-value problem (`_parse_hour()` already guards that) -- both values can individually be perfectly valid integers and still produce a useless window together. Fixed by checking `start >= end` after parsing both and resetting to the default with a stderr warning, rather than trusting the pair blindly. CodeRabbit catch on PR #297.

**A gate added to an unattended script's `main()` has to be bypassable for every *other* caller of that same `main()`, not just the scheduler it was designed for.** `update_schedule.py` gained an active-hours no-op for its cron/Task Scheduler cycle, but `process_drop.py` also calls it directly after a manual PDF drop/upload (`server.py`'s web upload handler) -- without a bypass, a supervisor uploading a corrected PDF at 6pm would see nothing happen, with no indication why. Fixed with a `--force` CLI flag that `process_drop.py` always passes (that code path is never reached by the unattended cron cycle, which always uses `--no-regen` instead -- see `run_update.sh`/`.ps1`), so a deliberate, right-now action takes effect immediately while the scheduled cycle still respects the gate. Before adding a gate like this, grep every caller of the function being gated, not just the one that motivated it. CodeRabbit catch on PR #297.
