# Web Novel Editor

**Version: v0.4.0 — Offline Script-Only Modernization; see GitHub Releases for publication status.**

Web Novel Editor is a desktop app that cleans web-novel chapter PDFs and UTF-8 TXT files so they
read well and sound right in text-to-speech tools (the primary target is the Microsoft Edge Neural
voice). It applies a careful, deterministic set of editing rules and saves clean PDF, TXT, or both.

**Everything runs on your computer.** Editing never uses AI, a model, an account or the internet,
and your chapter files are never modified — cleaned copies are written to a new folder.

## Setup and run

You never need to open a terminal.

- **Windows:** double-click `Setup_and_Run-Web-Novel-Editor.bat`
- **macOS:** double-click `Setup_and_Run-Web-Novel-Editor.command`

The first run creates a private `.venv` folder inside the program folder and installs the exact
package versions it needs; that first setup needs an internet connection. After that, a normal
launch checks the environment **offline** in a couple of seconds and opens the app. Running the
launcher again is also the repair path: missing packages are reinstalled and a damaged `.venv` is
rebuilt. The launcher window shows what it is doing and waits for Enter before it closes; setup
logs are kept in `files/runtime-data/logs`.

Python 3.10 or newer is required. The launcher finds an installed Python (it never uses the
Microsoft Store "python" shortcut or Apple's built-in stub). If none is installed it asks first:
on Windows it can install Python 3.13 for your user account only (no administrator rights);
on macOS it opens the official python.org download page. Nothing system-wide is changed silently.

If your computer warns that the launcher came from the internet, choose "More info → Run anyway"
(Windows) or "Open Anyway" in Privacy & Security (macOS). This only happens once.

## Using the app

The window has four numbered groups on the left and a large Activity log on the right (drag the
divider to resize).

1. **Sources** — *Add Files…* (PDF or TXT) and *Add Folder…* build one queue. New imports are
   sorted in reading order (1, 2, 10); *Move Up/Down*, *Remove* and *Clear All* adjust it.
   *Include subfolders* controls folder imports. Keyboard: Ctrl/Cmd+A select all, Delete or
   Backspace remove, Alt+Up/Down move, Ctrl/Cmd+O add files.
2. **Novel & Editing** — choose the novel (**Universal** works for any novel). The app shows how
   many protected names it keeps exactly as written.
3. **Output** — PDF, TXT, or both (both come from the same cleaned text). Shows where runs are
   saved. Optional *Edit audit (JSONL)*, *Debug full text* and *Dry run* apply to this session only.
4. **Run** — *Start*, *Pause/Continue* and *Stop* (the current file always finishes first),
   *Resume Run…*, *Resume Recent* and *Retry Failed*, with progress, completed/failed/skipped
   counts and elapsed time.

The **Activity** pane has a *Summary* tab (run start, one line per file, warnings, totals) and a
*Detailed* tab (timings, edit categories, mappings). *Clear Log* only clears the window. The
status bar holds the **Dark mode** toggle (remembered), **Preferences & Data** and **Open Log
Folder**.

## Where files go

Each run gets a new numbered folder: by default `Downloads/PDF-Editor-Outputs/<novel>-1`, then
`-2`, and so on. In **Preferences & Data** you can choose a different folder; numbered runs are then
created directly inside it. Output files keep their original names and the imported folder
structure. An existing file is never overwritten. Each run folder contains a `run-manifest.json`
that makes the run resumable.

## Resume and recovery

*Resume Run…* continues a stopped or interrupted run in its original folder with its original
settings (changing preferences never affects an existing run). Before skipping anything it checks
the source files and finished outputs by content hash. *Retry Failed* re-runs only failed items.
Changed sources, edited outputs, unclear ownership and old-format runs are refused rather than
overwritten. These are single-computer guarantees; folders synced by cloud services and several
computers writing the same run are not supported.

## What it fixes — and what it never touches

- PDF extraction spacing, line-wrap, ligature and Unicode artifacts; scraper junk and URLs
- Conservative OCR repairs (for example `l'm` → `I'm`), punctuation and `a`/`an`
- Numeric ratios (`6/7` → `6 out of 7`) and chapter-title formatting
- Spaced em/en dashes, converted for natural speech; unspaced dashes are kept
- Typography: clearly paired straight double quotes become “curly”, and `don't`/`it's` get ’.
  Anything uncertain is left exactly as written.

It never rewrites style or grammar by guesswork, never changes pronouns, and never changes a
protected name or the words and punctuation around it (for example *Clan Valor* always stays
*Clan Valor*).

## Upgrading from the earlier AI versions (v0.12 / v0.13)

All AI editing (local Ollama and the Gemini/Groq cloud providers) has been removed. If you used
those versions, an API key may still be saved on your computer — in
`%LOCALAPPDATA%\WebNovelEditor\secrets.json`, in a `.env` file in the program folder, or in the
`GEMINI_API_KEY` / `GROQ_API_KEY` environment variables. **This version never reads, uses, moves
or deletes them.** Delete them yourself and revoke the keys in each provider's console. Unfinished
cloud runs cannot be resumed (their files are left untouched); start a new run instead.

## Privacy, settings and logs

Preferences are stored per user (`%LOCALAPPDATA%\WebNovelEditor\settings.json` on Windows,
`~/Library/Application Support/WebNovelEditor/settings.json` on macOS). *Reset Preferences*
removes only that file. Each session writes one diagnostic log to `files/runtime-data/logs`
(file names, counts, timings and errors — never chapter text); the latest 20 are kept.

## Platform support

Windows 11 is the tested platform. The macOS launcher in this version has static and simulated
checks only; it has not yet been run on a Mac for this release. First-time setup downloads
packages and is not an offline installer.

## For developers

- Source: `scripts/` (launch chain `bootstrap.py` → `launcher.py` → `main.py`); shipped runtime
  data under `scripts/resources/`
- Editing rules: `md-instructions/EDITING-RULES.md` and `scripts/resources/Novel-Edits-Details/`
- Project state: `md-instructions/BRIEFING.md` · Decisions: `md-instructions/DECISIONS.md` ·
  Changes: `md-instructions/CHANGELOG.md`
- Tests: `files/tests/` (development only)
- Verification gate: `.venv\Scripts\python.exe scripts\verify.py` (Windows) or
  `.venv/bin/python scripts/verify.py`
