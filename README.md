# Webnovel Editor

Webnovel Editor is a local desktop app that turns webscraped webnovel chapter PDFs into
clean, TTS-ready PDFs. It is designed for listening with text-to-speech tools such as
Kokoro or Microsoft voices.

The app extracts text from selected PDFs, applies a careful mechanical editing pipeline,
and writes `EDITED_<original_name>.pdf` files to the folder you choose. It never changes
your original PDFs.

The first supported novel is Shadow Slave. The app has a Tkinter window where you choose
chapter PDFs, select an output folder, optionally enable replacement logs or debug text,
and start a batch. A progress bar and live log show what happened to each file.

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

The launcher checks Python, creates a self-contained `.venv` folder in the project,
installs the pinned dependencies, and opens the app. If your computer warns that the
launcher came from the internet, follow the on-screen instructions to allow the first run.

Python 3.10 or later is required. If Python is missing or too old, the launcher stops with
a plain-language message and explains what to do next.

## Status

Version 0.7.0 includes the complete Shadow Slave editing pipeline, protected-term support,
the desktop batch-processing GUI, output PDFs, audit logs, and the verification gate. The
multi-novel architecture is validated and ready for additional novel profiles.

## For developers

- Source: `scripts/`
- Editing rules: `md-instructions/EDITING-RULES.md`
- Project state: `md-instructions/BRIEFING.md`
- Verification gate: `.venv\Scripts\python.exe scripts\verify.py` on Windows, or
  `python scripts/verify.py` after activating the project virtual environment.
