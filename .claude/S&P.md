# Standards & Practices — CodeRabbit Review Log

This file records CodeRabbit recommendations so they can be applied to future changes.
Review this file before making changes to the codebase.

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
   - Docstring referenced "Schurman Machine" — contradicts the PR goal of removing hardcoded names
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
