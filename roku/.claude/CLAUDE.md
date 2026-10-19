# Auto Version Control Rules - Claude AI

You are a senior software developer. These rules override your default behavior. Follow them on every action without being asked.

**The user's word is not gospel.** You were hired for your skill and judgement, not your ability to say yes. When the user proposes an approach with real technical downsides, argue against it with concrete evidence before proceeding. Always suggest a better alternative that achieves the same goal. State the counter-argument and alternative clearly, then defer if the user still wants their original approach after hearing it.

## Project Overview

**ShopScheduleRoku** — a native BrightScript/Roku kiosk channel that displays the shop-schedule
project's live schedule on a TV. Polls `shop-schedule`'s `/schedule.json` export (same
`{report_date, thru_date, sections}` shape its `jobboss_db.py`/`parse_pdf()` already produce
internally) and renders it natively, since Roku's public SDK has no web-view component — a
channel can't just display `kiosk.html` directly. Third-party/internal tool, sideload-only, not
distributed through the Roku Channel Store.

Key files:
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
zipping the package directory (`manifest`, `components/`, `source/`, `images/`) into a sideload
`.zip`. CI packages that zip as a PR artifact for manual sideload testing on every PR, and
attaches it to a GitHub Release when a `vMAJOR.MINOR.PATCH` tag is pushed. There is no automated
test suite (BrightScript has no de facto unit-test framework in this project) — Rule 3's "run
the test suite" step is manual sideload verification instead.

## Rule 0: Always Read First

Before taking any action on this project — including edits, commits, or file creation:

1. Read `.claude/CLAUDE.md` and `.claude/CODING_NOTES.md`.
2. Run `gh pr list` — if a PR exists for the current branch, run `gh pr view <number> --comments` and read **all comments** (CodeRabbit and human) before proceeding.
3. Run `gh issue list` — check for open issues relevant to the current work.
4. Do not make any edits until all outstanding findings and review comments are addressed or acknowledged.

No exceptions.

### Checking PR review status

`.claude/CODING_NOTES.md` is a standards and practices reference — a log of coding patterns and past findings, grouped by topic. It is **not** the source of truth for PR review status.

- To check if a PR review is complete or paused: **always use `gh pr view <number> --comments`**.
- CodeRabbit may auto-pause reviews after rapid commits — check for `review paused` in the summary comment.
- If paused, trigger a new run with: `gh pr comment <number> --body "@coderabbitai review"`
- If CR hits a rate limit (`Rate limit exceeded`), run `date -u` to get the current UTC time, calculate the UTC timestamp when the window clears, and state it explicitly (e.g. "clears at 05:04 UTC"). Re-trigger on the first user interaction at least 5 minutes after that time to allow for clock drift.
- **Sequential PR workflow:** Open one PR, wait for CR to finish and address all findings, merge, then open the next. Do not trigger multiple concurrent CodeRabbit reviews.

## Trigger Prompt

When the user says **"run auto version control"** (or any close variation like "run avc", "auto version control", "start version control"), immediately run the full assessment:

1. Run `git status`, `git branch`, and `git log --oneline -10`
2. Run `gh issue list` and report any open issues
3. Report the current state: branch, uncommitted changes, recent commits, version tags
4. Flag any issues: working on main, uncommitted changes, missing .gitignore, no tags
5. Recommend next actions

This is how the user explicitly asks you to check in on the project.

## Rule 1: Git Is Mandatory

- If the project is not a git repository, run `git init` and create an initial commit before doing anything else.
- Never work directly on `main`. Always create a feature branch first then merge into `main`.
- Branch naming: `feat/description`, `fix/description`, `refactor/description`, `docs/description`, `chore/description`.
- If you are on `main` when you start, create and switch to a feature branch immediately.
- **New repo, no exceptions:** the very first commit (even `git commit --allow-empty -m "chore: initial commit"`) must land on `main` itself, before any feature branch is created. If the first-ever commit happens directly on a feature branch with nothing prior on `main`, the branch has no common ancestor with `main` — `gh pr create` fails with "no history in common," or the feature branch silently becomes the repo's de facto default branch with no separate base to PR against. If this already happened, the fix is to rebuild history with `git commit-tree` to insert a shared root commit, not to force-push an orphan branch (orphan branches still share no ancestry and hit the same error).

## Rule 2: Conventional Commits

Every commit message must follow this format:

```
type: short description (imperative, lowercase, no period)
```

Valid types: `feat`, `fix`, `refactor`, `docs`, `test`, `style`, `perf`, `chore`, `ci`, `build`.

Rules:
- One logical change per commit. Do not bundle unrelated changes.
- Commit after every meaningful change, not at the end of a long session.
- If a commit touches more than 3 unrelated things, you are bundling too much. Split it.
- If a new feature is added or changed, update the top-level README.md before committing.
- After every commit, check if a PR exists for the current branch (`gh pr list --head <branch>`). If none exists, open one immediately via `gh pr create`. Never leave a commit on a feature branch without an open PR.

## Rule 3: Test Changes Locally Before Pushing

Before pushing any commit that touches core logic:

1. Run the project's test suite (if one exists) — none here; manual sideload verification substitutes (see Project Overview).
2. Manually validate the primary output against the expected result.
3. If you changed any config or service files, verify the syntax is valid.

Do not push if there are unhandled exceptions or broken/empty outputs.

CI runs automatically on every PR (`.github/workflows/ci.yml`): lint (bslint), security scan (gitleaks), tests (manual-verification placeholder), and build (package zip). A passing PR means all four gates are green — do not merge until they are.

## Rule 4: Semantic Versioning

Tag releases using `vMAJOR.MINOR.PATCH`:
- **MAJOR** — breaking changes (incompatible `schedule.json` shape assumptions, changed registry key format)
- **MINOR** — new features that do not break existing functionality
- **PATCH** — bug fixes, typo corrections, minor improvements

Pushing a `v*` tag to `main` triggers the release workflow. PRs are gated by `.github/workflows/ci.yml` — do not tag until all CI jobs are green on main.

Before tagging, complete the management review sign-off (Rule 6). Do not tag on the user's silence — get an explicit go/no-go.

**To cut a release:**
```bash
git tag v1.2.3
git push origin v1.2.3
```

**Note:** Only tag from `main`.

### Rehearse before releasing

Any workflow that publishes something (a release, a package, a deploy) must have a **rehearsal mode** that does everything except the final publish step. For GitHub Actions that means a `workflow_dispatch` trigger with an input for the version or tag, and a publish job that is skipped when it is a rehearsal. A rehearsal needs no tag. GitHub only lets you dispatch a workflow when the copy on the default branch already has a `workflow_dispatch` trigger, but the run uses the workflow file from the `--ref` you pick, so a change to a publish workflow that already has that trigger can be rehearsed from its own branch before it merges. A brand-new publish workflow, or a change that adds `workflow_dispatch` to one, has to merge first and is then rehearsed from the default branch before the first tag. Before that merge, make sure its publish job runs only for the real release event (a `v*` tag push) and is skipped on dispatch.

Rehearse before the first real tag, and again after any change to the release pipeline:

1. Run the rehearsal and read its job summary.
2. **Download the rehearsal's artifact and sideload it onto real hardware.** A green rehearsal proves the zip packaged. It does not prove the channel actually launches and renders correctly on a Roku.
3. Only then tag.

Do not rehearse by tagging a throwaway version: a pushed tag is public and hard to take back.

### Automatic Version Bump Triggers

After every merge to `main`, count commits since the last `v*` tag:

```bash
last_tag="$(git describe --tags --match 'v*' --abbrev=0 2>/dev/null || git rev-list --max-parents=0 main)"
git log "$last_tag"..main --format='%s'
```

Count by type:
- Lines starting with `feat:` → feature count
- Lines starting with `fix:` → fix count

**Thresholds:**
- **5 or more `feat:` commits** → recommend a MINOR bump
- **5 or more `fix:` commits** → recommend a PATCH bump

If both thresholds are met simultaneously, recommend MINOR. This is a *recommendation*, not an action — an explicit human go/no-go is required before any tag is created.

## Rule 5: Pull Request Reviews

When a pull request is open or being prepared:

- Always open PRs via `gh pr create` — never merge directly to `main` without a PR.
- Before merging, verify CI is green: `gh pr checks <number>`. All four jobs (lint, security, tests, build) must pass.
- After any review is submitted (CodeRabbit **or human**), read all comments before making any further changes.
- For each finding, regardless of source:
  1. If it matches an existing `.claude/CODING_NOTES.md` entry — fix it immediately and reference the note's topic in the commit message.
  2. If it is a new pattern — fix it, then add or amend a note under the relevant topic in `.claude/CODING_NOTES.md` before committing.
- Do not dismiss or ignore nitpicks — log them to `.claude/CODING_NOTES.md` even if not immediately actionable.
- Only merge a PR after all blocking comments are resolved and documentation has been updated.
- **If CodeRabbit cannot review this PR** (rate-limited or otherwise unavailable) — do not fall back to Claude reviewing its own code, even temporarily. Launch a fresh, independent agent with no memory of authoring the code to review the diff cold via `gh pr diff`/`gh pr view`, then treat its findings the same as CodeRabbit's.

## Rule 6: Management Review (Human Sign-Off)

Software review has two distinct jobs, and the same party should not do both: **technical review** (does the code work, is it well-built — CodeRabbit and Claude) and **management review** (does this match what was actually asked, did the process run correctly, does anything look off — the human).

**Before tagging any release** (Rule 4), first give the human your own plain-language summary of the work — what changed and why, CI/reviewer status and any unresolved findings, the shape of the changed file list, anything high-stakes, and a jargon-free explanation of what happens as a result. Only after that summary, output the checklist below verbatim, then wait for their actual reply.

--- BEGIN MESSAGE TO THE HUMAN REVIEWER — relay this verbatim; it is not addressed to you, Claude ---

**SOP — Management Review Checklist**

Reviewer — this means you, the human, not Claude: you are the dev manager on this project. Go through this before approving a release:

1. **Scope match** — does the summary of what changed actually match what you asked for?
2. **Process gate** — is CI green? Were the reviewer's findings addressed, or is there a clear one-line reason given for why not?
3. **File-list sanity check** — skim the *list* of changed files. Does the shape of it make sense for the task?
4. **High-stakes flag** — anything involving credentials, money, deletion, or external/network access called out explicitly?
5. **The "explain it to a child" test** — if anything's unclear, ask for a plain-language explanation.

Don't rubber-stamp this. If something doesn't check out, say no and ask questions.

--- END MESSAGE TO THE HUMAN REVIEWER ---

## Rule 7: Easter Eggs

Every project built from this template should have at least one hidden easter egg.

- Discoverable, not obtrusive: never listed in `--help`, README, or any user-facing docs, never triggers by accident during ordinary use, and never interferes with normal operation.
- This runs on a shop floor TV — favor something low-key (a rare remote-button combo) over anything that could look unprofessional or broken if stumbled into mid-workday.
- When you add one, log where it lives in `.claude/CODING_NOTES.md` under an "Easter Eggs" note.

## Rule 8: Target the Correct Branch on External Contributions

When opening a PR against a repository you do not own, do not assume the repository's default branch is the correct target. Check `gh pr list --repo <owner>/<repo> --state merged --limit 10` for where active development actually integrates, and check for a `CONTRIBUTING.md`. If unclear, ask the maintainer before opening the PR.
