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

## Concurrency & File I/O

**Include microseconds in timestamp-based filenames.** `strftime('%Y%m%d_%H%M%S')` collides when two files are processed within the same second, silently overwriting the earlier one; add `%f`.

**Guard background subprocess triggers with a non-blocking lock.** Two rapid uploads can race on the same working directory; acquire the lock and return 409 if already running, release in `finally`.

**Write JSON config atomically: temp file + fsync + `os.replace()`.** Writing directly to the target path leaves a truncated/corrupt file if the process is interrupted mid-write.

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

## Documentation & Config Hygiene

**Quote `.env.example` values that contain spaces.** `KEY=Value With Spaces` may parse incorrectly in some dotenv loaders; use `KEY="Value With Spaces"`.

**Always tag fenced code blocks in Markdown with a language.** An untagged block (e.g. raw `.env` vars) fails MD040 lint; use e.g. ` ```dotenv `.
