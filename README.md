# Webnovel Editor

Webnovel Editor is a local desktop app that turns webscraped webnovel chapter PDFs into
clean, TTS-ready PDFs. It is designed for listening with text-to-speech tools such as
Kokoro or Microsoft voices.

The app extracts text from selected PDFs, applies a careful mechanical editing pipeline,
and writes `EDITED_<original_name>.pdf` files to the folder you choose. It never changes
your original PDFs.

The app has a Tkinter window where you pick a novel from a dropdown, choose chapter PDFs,
select an output folder, optionally enable replacement logs or debug text, and start a
batch. A progress bar and live log show what happened to each file.

Shadow Slave is the first fully-supported novel and applies its complete editing profile.
The dropdown also lists other novels; until one of them has its own profile, it is edited
with the universal cleanup rules only (grammar, spacing, Unicode, em-dash sweep, and so on)
and never has another novel's specific fixes applied to it.

## What it fixes

- PDF extraction spacing, line-wrap, ligature, and Unicode artifacts
- Known scraper markers and URLs
- Conservative OCR, punctuation, and grammar mistakes
- Numeric ratios and selected spoken slash forms
- Chapter title formatting and PDF heading layout
- Protected names and terms, which are kept byte-for-byte unchanged

## Setup and run (Commands)

You do not need to open a terminal or install project dependencies by hand.

- Windows: double-click `Setup_and_Run.bat`
- macOS: double-click `Setup_and_Run.command`

The launcher checks Python, creates a self-contained `.venv` folder in the project,
installs the pinned dependencies, and opens the app. If your computer warns that the
launcher came from the internet, follow the on-screen instructions to allow the first run.

Python 3.10 or later is required. If Python is missing or too old, the launcher stops with
a plain-language message and explains what to do next.

## Status

Version 0.9.0 includes the complete Shadow Slave editing pipeline, protected-term support,
the desktop batch-processing GUI with a novel-selection dropdown, output PDFs, audit logs,
and the verification gate. The dropdown is driven by a novel → pipeline dispatch registry:
Shadow Slave runs its full profile, and any other novel falls back to universal-only
editing. Adding a real profile for another novel is a data exercise, not a code change.

## For developers

- Source: `scripts/`
- Editing rules: `md-instructions/EDITING-RULES.md`
- Project state: `md-instructions/BRIEFING.md`
- Verification gate: `.venv\Scripts\python.exe scripts\verify.py` on Windows, or
  `python scripts/verify.py` after activating the project virtual environment.
