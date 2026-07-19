# Web Novel Editor

Web Novel Editor is a local desktop app that turns webscraped webnovel chapter PDFs into
clean, TTS-ready PDFs. It is designed for listening with text-to-speech tools such as
Kokoro or Microsoft voices (the primary target is the Microsoft Edge Neural voice).

The app extracts text from your chapter PDFs, applies a careful mechanical editing
pipeline, and saves the cleaned copies — under their original filenames — into a fresh,
automatically numbered folder in your Downloads (for example `Downloads\universal-1`).
It never changes your original PDFs, and a re-run never overwrites an earlier batch.

The app has a Tkinter window where you pick an editing profile from a dropdown
("Universal" is the default and works for any novel), then either upload individual
PDFs or select a whole folder — folders are processed in natural reading order
(1, 2, 10 — not 1, 10, 2) and the output mirrors the folder's structure. You can pause
and continue a batch between files. A progress bar and a one-line-per-file log show
what happened to each file, with a summary at the end.

**Shadow Slave, Supreme Magus, and The Noble Queen** are fully supported and apply their own
editing profiles (protected names + novel-specific fixes). The dropdown also lists other
novels; until one of them has its own profile it is edited in **Basic Edit Mode** — the
universal cleanup rules only (grammar, spacing, Unicode, junk/URL strip, em-dash sweep, and so
on) — and never has another novel's specific fixes applied to it.

## What it fixes

- PDF extraction spacing, line-wrap, ligature, and Unicode artifacts
- Known scraper markers and URLs
- Conservative OCR, punctuation, and grammar mistakes
- Numeric ratios and selected spoken slash forms
- Chapter title formatting and PDF heading layout
- Protected names and terms, which are kept byte-for-byte unchanged

## Setup and run

You do not need to open a terminal or install project dependencies by hand.

- Windows: double-click `Setup_and_Run.bat`
- macOS: double-click `Setup_and_Run.command`

Each launcher runs four numbered steps — checks Python, creates (or self-heals) a
self-contained `.venv` folder in the project, installs the pinned dependencies (skipped when
the environment is already healthy), and opens the app. If your computer warns that the
launcher came from the internet, follow the on-screen instructions to allow the first run.

Python 3.10 or later is required. If Python is missing or too old, the launcher stops with
a plain-language message and explains what to do next.

**Platform support:** Windows is the primary, fully-tested platform. The macOS
`Setup_and_Run.command` is verified — a real macOS clean-room bootstrap plus a Finder
double-click (confirmed 2026-07-16). The `scripts/MacOS/` folder is a structural placeholder
only (there is no macOS-exclusive code today).

## Status

Version 0.11.0 adds the overhauled batch flow: two input modes (upload PDFs / select a
folder with natural-order recursive scanning), automatic mirrored output into an
auto-numbered Downloads folder with original filenames, **"Universal" as the default
dropdown choice** (novels without their own profile are marked "no profile yet"),
a pause/continue control, a condensed one-line-per-file log, and a decorative-divider
sweep (`* * *`, `~~~`) so TTS never reads symbol runs aloud.

The editing pipeline itself is unchanged from 0.10.0: **three real per-novel profiles**
(Shadow Slave, Supreme Magus, The Noble Queen), universal-only editing for every other
novel, hardened scraper-junk/URL/watermark removal, protected-term support, audit logs,
and the verification gate. The dropdown is driven by a novel → pipeline dispatch
registry: a profiled novel runs its full profile, and any other novel (and "Universal")
runs universal-only editing. Adding a real profile for another novel is a data exercise,
not a code change. The two dirtier local corpora (Noble Queen, Supreme Magus) are local
QA evidence, not files that ship with the app.

## For developers

- Source: `scripts/Universal/` (entry point `scripts/Universal/main.py`); shipped runtime data
  under `scripts/Universal/resources/`
- Editing rules: `md-instructions/EDITING-RULES.md`
- Project state: `md-instructions/BRIEFING.md` · Decisions: `md-instructions/DECISIONS.md`
- Tests: `files/tests/` (dev-only)
- Verification gate: `.venv\Scripts\python.exe scripts\verify.py` on Windows, or
  `python scripts/verify.py` after activating the project virtual environment.
