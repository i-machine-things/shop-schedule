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

## Accessibility

**Custom `<div>` controls need `role`, `tabindex`, a keydown handler, and `:focus-visible`.** Any `<div>` replacing a native interactive element (e.g. a drop zone) must remain keyboard-operable.

**Add `aria-live="polite" aria-atomic="true"` to elements that auto-update (clocks, live status).** Screen readers otherwise never announce the changing content.

## JavaScript Patterns

**Never wrap `URLSearchParams.get()` values in `decodeURIComponent()`.** They're already percent-decoded; double-decoding breaks values containing `%25`-style sequences.

**Strip `?` and `#` before checking a URL's file extension.** `url.endsWith('.pdf')` misses `file.pdf?token=...` or `file.pdf#page=2`.

**Check `res.ok` before reporting success on a `fetch` call.** Ignoring the response status let the UI show success even when the server returned an error.

**Reset `input.value = ''` after handling a file upload.** Browsers suppress the `change` event when the same file is reselected without clearing the input first.

**Add `.catch` and a fallback for `navigator.clipboard.writeText`.** It fails silently in browsers with restricted clipboard access or non-HTTPS contexts; fall back to `document.execCommand('copy')`.

## Server & HTTP

**Guard `int(Content-Length)` parsing with try/except; return 400 on failure or negative values.** Malformed requests otherwise raise an unhandled `ValueError` and produce a 500.

## PDF Handling

**Verify CodeRabbit API-change claims against the actual library version in use.** CR claimed `PDFDocumentProxy.destroy()` was removed in PDF.js 3.x; it wasn't — `cleanup()` doesn't terminate the worker and would have leaked it.

## Work Center Backlog Calculation

**Call it "backlog," not "load."** Shipped the first version as `load_weeks`/"wk load"; the actual shop-floor term for queued work at a work center is backlog, not load. Renamed throughout (`_work_center_backlog_days()`, `_BACKLOG_QUERY`, `apply_work_center_backlogs()`, `.wc-backlog`, "wk backlog") after the fact rather than caught before shipping -- worth getting shop-floor terminology right from a domain person before building the feature, not after.

**An overdue-but-still-open job (`sch_end` already in the past, `Status <> 'C'`) means that work center is *behind*, not free starting at that stale date — went through two rounds to get this right.** Round 1 only fixed the reported gap *size* (floor it at today instead of measuring from the stale date: "open now (1.1 wk gap)" → "open now (3 day gap)" when the next job was really only 3 days out). Round 2 (real user feedback: a work center playing catch-up on old jobs was still showing a false gap) fixed the deeper issue -- an overdue job's *occupied interval* itself needs clamping to `[sch_start, max(sch_end, now)]` in `_work_center_backlog_days()`, not just the reported gap number. Without that, a near-term job starting shortly after the overdue one reads as a gap (idle time) right when the work center is actually going to spend that time catching up on the backlog, not sitting idle. The round-1 fix (`max(queue_end, now)` on the reported size) became redundant once the clamp was applied at interval-construction time -- `queue_end` can no longer be stale at all -- and was removed rather than left as dead-but-harmless code. Confirmed genuine future gaps past the catch-up work still detect correctly (synthetic case 4) -- this isn't gap detection getting suppressed generally, just the illusory ones caused by stale dates.

**`backlog_days`/`gap_days` are integer days, not fractional weeks (`backlog_weeks`/`gap_weeks` in the first version).** Requested after shipping: shop floor staff wanted "2 wk 3 day," not "2.3 wk" -- a decimal week doesn't translate to an actual calendar date at a glance. Storing raw days (exact) and formatting with `_format_weeks_days()` (`divmod(days, 7)`, omitting a zero component) avoids compounding rounding on top of an already-rounded decimal, which storing pre-rounded fractional weeks would have.

**Work center backlog stops at the first gap of ≥1 week between jobs, rather than reporting the furthest-out job's end date.** Walk `[sch_start, sch_end]` intervals in start order; a gap here is real idle time at that work center, which sales needs visible to fill — reporting the far job's date instead would hide it. See `_work_center_backlog_days()`.

**Report the gap's *size*, not just that one exists.** First version returned only `backlog_days` (when the opening starts); caught before pushing that this alone invites scheduling a 2-week job into what might actually be a 1-week hole. `_work_center_backlog_days()` now returns `(backlog_days, gap_days)` — `gap_days` is `None` when the queue simply has nothing scheduled after it (open-ended, not a bounded opening) vs. an actual number when there's a real gap with a known size.

**Reusing `sec['jobs']` (the display-bound job list) for the backlog calculation silently capped it at ~`JOBBOSS_DAYS_AHEAD` (default 14 days, so "~2ish weeks") — reported after shipping, not caught before.** The main query's `Sched_Start <= cutoff` filter is correct and intentional for what's *displayed* (a scrolling kiosk shouldn't show months of future jobs), but the backlog stat needs real depth beyond that window — that's the entire point of showing it. Fix: `jobboss_db.py` runs a second, unbounded query (`_BACKLOG_QUERY`, no date cutoff, no `CROSS APPLY` since it doesn't need `Rem_Hrs`/`NumOps_Ahead`/`Curr_WC`) purely for the backlog calc, grouped by the same `(department, wc_group, wc)` key, and attaches `backlog_days`/`gap_days` to each section itself before `update_schedule.py` ever sees it.

**`_work_center_backlog_days()`/`_parse_sched_date()` live in `jobboss_db.py`, not `update_schedule.py`, despite being used by both the DB and PDF paths.** `update_schedule.py` already does `import jobboss_db`; the reverse would be circular. `apply_work_center_backlogs()` in `update_schedule.py` now only fills in `backlog_days`/`gap_days` for sections that don't already have them (i.e. the PDF path, which has no equivalent wide query available and keeps the narrower, `sec['jobs']`-based calculation as a known, accepted limitation) — it skips any section the DB path already computed via the wide query, so the DB path's correct value is never silently overwritten by a re-derived, truncated one.

**Verified the gap-detection boundary with synthetic data before pushing, not just read through it** — eight cases (no gap, gap >1wk, the overdue-catch-up scenario specifically, a genuine gap past some overdue backlog that must still be detected, gap <1wk that must NOT stop early, empty job list, all-overdue with no next job, gap exactly at the 7-day threshold) all matched hand-computed `(backlog_days, gap_days)` pairs. Cheap and worth doing for any date-arithmetic-with-a-threshold change; off-by-one-week errors here are exactly the kind of bug that looks right on a quick read -- neither the overdue-catch-up case nor the still-must-detect-a-real-gap case were caught by earlier rounds of this test suite, since none of those cases had a job already in the past.
## Windows Port

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

## Documentation & Config Hygiene

**Quote `.env.example` values that contain spaces.** `KEY=Value With Spaces` may parse incorrectly in some dotenv loaders; use `KEY="Value With Spaces"`.

**Always tag fenced code blocks in Markdown with a language.** An untagged block (e.g. raw `.env` vars) fails MD040 lint; use e.g. ` ```dotenv `.
