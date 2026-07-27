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

**v0.13.0 — complete, awaiting final sign-off.** This version lets the optional AI proofreading pass
run on a **cloud** model (Google Gemini or Groq) instead of your own machine, if you want it to. Four
things are worth knowing before you do:

- **It is opt-in every single time.** There is no default cloud provider and the app does not remember
  the one you used last. Local stays the normal path, and the AI pass as a whole is still off unless
  you switch it on.
- **Your chapter text leaves your computer** when you use a cloud provider. The app asks you to
  confirm that once, in plain language, before the first cloud request it ever makes, and offers to
  cancel and stay local instead.
- **It is built to avoid costing you money, and it tells you the truth about that.** The app never
  enables billing, never upgrades an account, and never intentionally picks a paid or preview model —
  it only calls exact models reviewed and listed in `config.toml`. But no desktop app can *guarantee*
  a key you supply can never be charged, so use a key from a project with billing disabled and confirm
  it in the provider's own console. If the app cannot confirm a run will stay free, it stops and says
  why rather than proceeding.
- **Free tiers are small.** Roughly thirty chapters a day on Groq's free plan. When the daily quota
  runs out the app saves its place, tells you so, and you can close it and pick up tomorrow with
  **Resume incomplete run**. For a whole novel, the local option is still the practical one.

Your protected names and the chapter structure are guaranteed byte-for-byte by exactly the same strict
gate whichever engine you choose — the cloud path is not a looser path.

**Shipped: v0.12.0.** This version adds an **optional local AI proofreading pass** that runs after the
scripted editing and before the PDF is written. It is **opt-in and OFF by default** — with it off, the
output is exactly the same as the scripted result in v0.11.0. When switched on it runs entirely on your
own machine via a local Ollama model (default `qwen3:14b`), makes only tiny high-confidence grammar/OCR
corrections, and is held by a strict gate that keeps your protected names and the chapter's structure
byte-for-byte intact — anything it is not sure about is left unchanged. Because it is off by default,
the program behaves exactly as before unless you deliberately turn it on.

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
