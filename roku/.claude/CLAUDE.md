# Roku Client — Supplementary Rules

This directory holds the native Roku client, merged into the `shop-schedule` repo from the
formerly-separate `shop-schedule-roku` project (full history preserved via `git subtree`) so the
web kiosk/server and the Roku client release together under one version number.

**This file supplements the repo root's `.claude/CLAUDE.md` — read that first.** Rules 0-6 there
(git workflow, commits, testing, versioning, PR review, management sign-off) apply here
unchanged, with one wording note: that file's branch name is `master`, which is also this
project's default branch post-merge (not `main`, which is what the original separate
`shop-schedule-roku` repo used before the merge — don't follow stale `main` references in old
commit messages or this file's own history).

## Project Overview

**Roku client** — a native BrightScript/Roku kiosk channel that displays `shop-schedule`'s live
schedule on a TV. Polls the server's `/schedule.json` export (same `{report_date, thru_date,
sections}` shape `jobboss_db.py`/`parse_pdf()` produce, one level up) and renders it natively,
since Roku's public SDK has no web-view component — a channel can't just display `kiosk.html`
directly. Third-party/internal tool, sideload-only, not distributed through the Roku Channel Store.

Key files (all paths relative to this `roku/` directory):
- `source/main.brs` — channel entry point, creates the root scene.
- `components/AppScene.brs` — top-level router between setup (no server configured yet) and the
  schedule display, based on `ScheduleConfig` registry section.
- `components/Screens/SetupScreen.brs` — one-time server URL entry (`KeyboardDialog`-based;
  plain `TextEditBox` doesn't work for real input on Roku hardware), writes `ScheduleConfig`.
- `components/Screens/ScheduleScreen.brs` — the actual display: polls `ScheduleTask` on a timer,
  builds section headers + job rows dynamically, auto-scrolls, shows a non-destructive error
  banner on fetch failure (keeps the last good schedule on screen rather than blanking it).
- `components/Tasks/ScheduleTask.brs` — async `roUrlTransfer` GET of `{serverUrl}/schedule.json`,
  run off the render thread.
- `manifest` — Roku channel metadata (version, resolutions, icons).

Environment / deployment: no server-side component of its own and no build toolchain beyond
zipping this directory's package contents (`manifest`, `components/`, `source/`, `images/`,
`media/`) into a sideload `.zip`. The repo root's `.github/workflows/roku-ci.yml` packages that
zip as a PR artifact (only on PRs touching `roku/**`) for manual sideload testing, and
`roku-release.yml` attaches it to the shared `vMAJOR.MINOR.PATCH` GitHub Release alongside
whatever changed on the web/server side. There is no automated test suite (BrightScript has no de
facto unit-test framework in this project) — the root CLAUDE.md's Rule 3 "run the test suite"
step is manual sideload verification instead, same as before the merge.

## Easter Eggs

Every project built from this template should have at least one hidden easter egg — discoverable,
not obtrusive: never listed in `--help`, README, or any user-facing docs, never triggers by
accident during ordinary use, never interferes with normal operation. This runs on a shop floor
TV — favor something low-key (a rare remote-button combo) over anything that could look
unprofessional if stumbled into mid-workday. This client's existing one (and where to log any
future one) is documented in `roku/.claude/CODING_NOTES.md`'s "Easter Eggs" section.

## Target the Correct Branch on External Contributions

When opening a PR against a repository you do not own, do not assume the repository's default
branch is the correct target. Check `gh pr list --repo <owner>/<repo> --state merged --limit 10`
for where active development actually integrates, and check for a `CONTRIBUTING.md`. If unclear,
ask the maintainer before opening the PR.
