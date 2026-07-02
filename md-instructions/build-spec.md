# Webnovel Editor — Build Specification

**Project:** `webnovel-editor-main`
**Version:** 1.0 (Phase 1–7 roadmap)
**Status:** Pre-implementation. This document is the handoff spec for Claude Code.
**Maintained at:** `md-instructions/build-spec.md`
**Companion log:** `md-instructions/BRIEFING.md` — Claude Code must keep this updated after every session.

---

## Table of Contents

1. [Overview](#overview)
2. [Goals and Non-Goals](#goals-and-non-goals)
3. [Confirmed Repo Structure](#confirmed-repo-structure)
4. [Startup Scripts](#startup-scripts)
5. [Tech Stack](#tech-stack)
6. [GUI Requirements](#gui-requirements)
7. [Batch Processing Pipeline](#batch-processing-pipeline)
8. [Editing Rules — Shadow Slave](#editing-rules--shadow-slave)
9. [Novel-Index Protection System](#novel-index-protection-system)
10. [Multi-Novel Architecture](#multi-novel-architecture)
11. [Safeguards](#safeguards)
12. [Study-Examples Reference](#study-examples-reference)
13. [Test Assets](#test-assets)
14. [Skills](#skills)
15. [Implementation Phases](#implementation-phases)
16. [BRIEFING.md Maintenance Contract](#briefingmd-maintenance-contract)
17. [Risks and Open Questions](#risks-and-open-questions)

---

## Overview

This is a local desktop GUI application written in Python. Its purpose is batch editing of webnovel chapter PDFs. It reads input PDF files, extracts their text, applies a deterministic rule-based editorial pipeline, and writes clean new PDFs to a user-selected output folder.

The first supported novel is **Shadow Slave**. The repo structure, pipeline design, and rule system must be organized so additional novels can be onboarded later without restructuring the codebase.

The tool is strictly a mechanical editor. It does not rewrite, rephrase, paraphrase, or creatively alter the text. It corrects only objective errors in formatting, punctuation, grammar, spelling, and canonical naming.

**Intended workflow:**

```
Import PDFs → Select output folder → Click Run
→ Process each PDF sequentially
→ Save EDITED_<original_name>.pdf into selected output folder
→ Log success/failure per file
→ Display final run summary
```

---

## Goals and Non-Goals

### Goals

- Local-first desktop GUI, no internet dependency at runtime
- Batch process any number of PDFs in a single run
- User controls both input files and output folder via file dialogs
- Never modify original input PDFs
- Apply a deterministic rule-based pipeline to Shadow Slave chapters
- Load protected term lists from `novel-index/` text files before any correction
- Output one clean edited PDF per input file, named `EDITED_<original_name>.pdf`
- Log all replacements to a JSONL audit file alongside each output PDF
- Continue the batch run if one file fails; log the failure and move on
- Support addition of new novel profiles without rewriting core code
- Keep `md-instructions/BRIEFING.md` updated after every Claude Code session

### Non-Goals (v1)

- No cloud sync or network features
- No AI rewriting, paraphrasing, synonym replacement, or creative editing
- No SymSpell or external spell-check library in v1 Shadow Slave editor (rule dictionary only)
- No GUI preview, diff viewer, or rule-toggle UI in v1
- No auto-installation of Python if it is not present
- No support for image-only scanned PDFs in v1 (text-extractable PDFs only)

---

## Confirmed Repo Structure

> **✅ Path reconciliation — RESOLVED 2026-06-21 (Phase 1).** The live repo was mapped and
> reconciled with the user. Decision: **keep the on-disk layout, update this spec to match.**
> The tree below has been corrected to reflect the real working directory. Settled facts:
> - The instructions folder on disk is **`md-instructions/`** (plural). All references in this
>   spec now use `md-instructions/`. (Note: the kickoff prompt's `md-instruction/` singular was a typo.)
> - `novel-index/`, `study-examples/`, and `pdf-example-chapters/` live **inside `files/`**, not at
>   the repo root. The tree and explicit paths below reflect this. (Inline prose may still say
>   "the `novel-index/` system" conceptually — the real path is always `files/novel-index/`.)
> - Startup scripts on disk are **`Setup_and_Run.bat`** + **`Setup_and_Run.command`** (a single
>   self-contained pair), NOT the 3-file `.bat`/`.ps1`/`.sh` scheme this spec originally described.
>   The user chose to keep and adapt these two files. They were adapted in Phase 1 (entry point set
>   to `scripts/main.py`, requirements path `scripts/requirements.txt`, ffmpeg block removed).
> - Entry point is **`scripts/main.py`**; **`requirements.txt` lives in `scripts/`** (not repo root);
>   the virtual environment is **`.venv/`**.
> - Confirmed absolute paths on Home-PC:
>   - Test corpus: `...\webnovel_editor-main\files\pdf-example-chapters\webscraped_shadow_slave` (3,000 chapter PDFs, ~29 MB)
>   - Novel index: `...\webnovel_editor-main\files\novel-index` (only `shadow-slave.txt` populated; rest are empty placeholders)
>   - Prior editors: `...\webnovel_editor-main\files\study-examples`

The tree below reflects the **actual reconciled working repo** as of Phase 1 (2026-06-21).

```
webnovel-editor-main/
│
├── README.md
├── AI-WORKSPACE.md             ← global developer conventions (governs this build)
├── Setup_and_Run.bat           ← Windows setup + launcher (adapted Phase 1)
├── Setup_and_Run.command       ← macOS setup + launcher (adapted Phase 1)
├── .gitignore
│
├── .claude/skills/             ← six pulled-in skills (see Skills section)
├── .codex/skills/
│
├── md-instructions/
│   ├── BRIEFING.md             ← living AI handoff log (Claude Code maintains this)
│   ├── CHANGELOG.md            ← persistent, updated every phase/version
│   ├── EDITING-RULES.md        ← full editing rule reference (populated from this spec)
│   └── build-spec.md           ← this file (temporary; remove once fully implemented)
│
├── test-files/                 ← pinned pytest fixtures (added Phase 1)
│   └── shadow_slave/           ← ~10 representative chapter PDFs copied from the corpus
│
├── scripts/
│   ├── main.py                 ← entry point, launched by startup scripts
│   ├── requirements.txt        ← pinned deps (== ); startup scripts install from here
│   ├── verify.py               ← phase gate: pytest + pin-check + CHANGELOG-bump
│   ├── conftest.py             ← puts scripts/ on sys.path for tests
│   │
│   ├── gui/
│   │   ├── __init__.py
│   │   └── app.py              ← Tkinter main window and all GUI logic (Phase 2)
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── batch_runner.py     ← orchestrates the full batch loop
│   │   ├── replacement_log.py  ← ReplacementLog and ReplacementEntry dataclasses
│   │   └── protected_lexicon.py ← load, deduplicate, sort, mask, unmask
│   │
│   ├── pdf/
│   │   ├── __init__.py
│   │   ├── extractor.py        ← pdfplumber-based text extraction
│   │   └── builder.py          ← reportlab-based PDF output
│   │
│   ├── pipelines/
│   │   ├── __init__.py
│   │   └── shadow_slave.py     ← full SS pipeline: calls stages in order
│   │
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── unicode_cleanup.py
│   │   ├── ligature_cleanup.py
│   │   ├── junk_strip.py       ← NEW Stage 1.5: ad/URL/fingerprint removal (Tier 1 on)
│   │   ├── spacing_cleanup.py
│   │   ├── chapter_titles.py
│   │   ├── ocr_repair.py
│   │   ├── punctuation.py
│   │   ├── grammar.py
│   │   ├── em_dash.py
│   │   └── slash_replace.py
│   │
│   ├── profiles/
│   │   ├── __init__.py
│   │   └── shadow_slave/
│   │       ├── __init__.py
│   │       ├── canonical_names.py   ← SS_CANONICAL_NAMES frozenset
│   │       └── special_fixes.py     ← SS_SPECIAL_FIXES dict (forced substitutions)
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_utils.py       ← sanitize output filename, path helpers
│   │   └── logger.py           ← session log to file
│   │
│   └── tests/
│       ├── __init__.py
│       └── test_scaffold.py    ← Phase 1 wiring tests (per-rule tests added Phase 4+)
│
└── files/                      ← all assets and supporting data live under here
    ├── novel-index/
    │   ├── shadow-slave.txt    ← active (~5.6 KB, 392 terms)
    │   ├── circle-of-inevitability.txt   ← empty placeholder
    │   ├── lord-of-the-mysteries.txt     ← empty placeholder
    │   ├── re-monster.txt                ← empty placeholder
    │   ├── renegade-immortal.txt         ← empty placeholder
    │   ├── reverend-insanity.txt         ← empty placeholder
    │   ├── supreme-magus.txt             ← empty placeholder
    │   └── the-noble-queen.txt           ← empty placeholder
    │
    ├── pdf-example-chapters/
    │   └── webscraped_shadow_slave/      ← canonical test corpus (3,000 PDFs, ~29 MB)
    │
    └── study-examples/         ← TEMPORARY. Reference only. Delete after Phase 1 confirmed.
        ├── ss_pdf_editor-v1.py
        ├── sm_pdf_editor-v8.2.py
        ├── freewebnovel-webscraper.py
        ├── scrape_noble_queen_webnovel-v1.py
        ├── scrape_noble_queen-v3.py
        ├── Shadow_Slave_Instructions-1.txt
        └── <Novel>-Word_List_Index/      ← per-novel word-list reference subfolders
```

### Folder Responsibilities

`scripts/gui/` — All Tkinter window code, file dialogs, listbox, log widget, progress bar. No business logic here. GUI calls into `batch_runner.py` via a thread.

`scripts/core/` — Business logic that is shared across novel profiles. The batch runner loop, the replacement logger, and the protected lexicon loader all live here.

`scripts/pdf/` — Isolated PDF I/O. Extractor uses pdfplumber. Builder uses reportlab. Neither module knows about editing rules.

`scripts/pipelines/` — One file per novel. `shadow_slave.py` calls rule modules in the correct order for Shadow Slave. Adding a new novel means adding a new pipeline file.

`scripts/rules/` — Each rule category is its own module. Rules are stateless functions. They accept a string and return a string. They do not call each other directly; the pipeline orchestrates order.

`scripts/profiles/` — Per-novel constants: canonical name sets, forced substitution dicts, any novel-specific data that rules need to import.

`scripts/utils/` — Shared helpers with no dependencies on rules or GUI.

`scripts/tests/` — pytest-based. One test file per rule module minimum. Smoke test for the full pipeline.

---

## Startup Scripts

> **✅ RESOLVED 2026-06-21 (Phase 1) — supersedes the 3-file scheme described below.**
> The repo ships **two** self-contained launchers that the user chose to keep and adapt:
> - **`Setup_and_Run.bat`** (Windows) — Python detection (with user-scope/machine-scope choice
>   via winget only if Python is missing), SmartScreen note, creates/activates `.venv/`, installs
>   `scripts/requirements.txt`, launches `scripts/main.py`, pauses at end.
> - **`Setup_and_Run.command`** (macOS) — same flow via Homebrew/python.org, `.venv/`, `source` activate.
>
> Phase 1 adaptations made: entry point `scripts/launcher.py → scripts/main.py`; requirements path
> kept at `scripts/requirements.txt`; the ffmpeg setup block was removed (this tool never touches
> audio/video). The detailed `.bat`/`.ps1`/`.sh` description in this section is **historical** — it
> documents the originally-specified scheme and is retained for reference only. The actual files are
> the two above.

### Architecture (historical — original spec scheme, not built)

The Windows launcher was originally specified as a two-file pattern:

- `scan for libraries and run (batch file) - for windows11.bat` — thin launcher, hands off to PowerShell
- `setup_and_run_webnovel.ps1` — does all real logic

The Mac launcher is a single self-contained shell script.

### Windows — `.bat` File

Exact filename: `scan for libraries and run (batch file) - for windows11.bat`

Behavior:
- Sets working directory to its own location (`%~dp0`) so it works regardless of where the user double-clicked from
- Checks that `setup_and_run_webnovel.ps1` exists in the same folder. If missing: print a clear error naming both expected files, pause, exit.
- Checks that `scripts/main.py` exists in the expected relative path. If missing: print error, pause, exit.
- Hands off to PowerShell: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_and_run_webnovel.ps1"`
- Captures exit code. If non-zero: print exit code, pause so the user can read the output.

The `.bat` does nothing else. All actual setup logic lives in the `.ps1`.

### Windows — `setup_and_run_webnovel.ps1`

Behavior in order:

1. **Scan Python** — run `python --version` and `python3 --version`, capture output, identify which command works and what version is installed.
2. **Display scan results** — print what was found to the console in a readable format.
3. **Version check** — require Python 3.9 or later. If the version is lower, print a message explaining the requirement and stop.
4. **Python not found** — if neither `python` nor `python3` resolves, do not attempt silent installation. Print a message: "Python was not found. Please install Python 3.9 or later from https://www.python.org/downloads/ and re-run this script." Open the URL in the default browser using `Start-Process`. Pause and exit cleanly.
5. **Check pip** — verify pip is available. If not, attempt `python -m ensurepip --upgrade` once. If it still fails, instruct the user to reinstall Python with pip included.
6. **Virtual environment** — check for `venv/` in the repo root. If missing, create it: `python -m venv venv`. Print confirmation.
7. **Activate venv** — activate `venv/Scripts/Activate.ps1` for the duration of the script.
8. **Install dependencies** — run `pip install -r requirements.txt`. Print output. If this fails, display the error and exit without launching.
9. **Confirm installed packages** — print `pip list` filtered to the packages in requirements.txt.
10. **Launch app** — run `python scripts/main.py`.

On any non-zero exit from a critical step: print a clear message, pause, exit with that code.

**Do not attempt silent Python installation.** Realistic minimum friction means detecting the problem and guiding the user to fix it, not pretending it can always be automated safely.

### Mac — `scan for libraries and run (sh file) - for mac.sh`

Exact filename: `scan for libraries and run (sh file) - for mac.sh`

This file contains all logic (no companion `.ps1`).

Behavior in order:

1. `cd` to the script's own directory (`$(dirname "$0")`)
2. Detect `python3` with `command -v python3`. If not found: print message recommending `brew install python3` or visiting `https://www.python.org/downloads/`, then exit.
3. Check version: `python3 --version`. Require 3.9+. If lower: print requirement and exit.
4. Check for `venv/`. If missing: `python3 -m venv venv`.
5. Activate: `source venv/bin/activate`
6. `pip install -r requirements.txt`
7. `python scripts/main.py`

### `requirements.txt`

> **✅ RESOLVED 2026-06-21 (Phase 1).** Location is **`scripts/requirements.txt`** (matches both
> AI-WORKSPACE convention and the on-disk launchers), and every package is **exact-pinned (`==`)** to
> the versions resolved at first successful install on Python 3.12.10. The startup scripts install from
> `scripts/requirements.txt`.

Actual pinned contents (`scripts/requirements.txt`):

```
pdfplumber==0.11.10
reportlab==5.0.0
PyPDF2==3.0.1
pytest==9.1.1
```

Note: `tkinter` is bundled with standard Python on Windows and Mac. If it is absent (some Linux-stripped builds), the startup script should detect the import failure and print a message explaining how to install it for the user's OS. This is an edge case for v1.

---

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.10+ | Required. The codebase uses `str | None` union syntax. |
| GUI | Tkinter (`tkinter`, `tkinter.ttk`) | Bundled with Python, no extra install, sufficient for v1, confirmed working in study examples. |
| PDF extraction | pdfplumber | Confirmed in both study-example scripts. Best for text-based PDFs. Handles x_tolerance and y_tolerance tuning. |
| PDF output | reportlab | Confirmed in both study-example scripts. Handles Times-Roman body, Helvetica-Bold headings, justified layout. |
| PDF page manipulation | PyPDF2 | Confirmed in study examples for page filtering (remove single-heading orphan pages). |
| Threading | `threading.Thread` (daemon) | Confirmed pattern from sm_pdf_editor. Keeps GUI responsive during batch processing. |
| Replacement logging | JSON Lines (`.jsonl`) | Confirmed pattern from ss_pdf_editor and sm_pdf_editor. Auditable, appendable, one record per replacement. |
| Testing | pytest | Matches OCRmyPDF reference model. One test file per rule module. |
| Config | None in v1 | Hardcoded defaults are fine. If needed later, use a simple `config.ini` with `configparser`. |
| Packaging | Not in v1 scope | Future option: PyInstaller for single-exe distribution. |
| Spell correction | None in v1 | Rule dictionary + forced substitutions only. No SymSpell. Add later if needed. |

**Do not introduce a second PDF library.** PyMuPDF (`fitz`) was considered but the study examples already confirm pdfplumber + reportlab + PyPDF2 as a working stack. Stick to this for v1.

---

## GUI Requirements

### v1 Required

The GUI is a single window. Implementation reference: `sm_pdf_editor-v8.2.py`, class `WebnovelPDFEditor`, method `_build_ui`. Adapt for the webnovel editor context.

Window size: 820×700 minimum. Resizable.

**Sections (top to bottom):**

**File list panel** (`ttk.LabelFrame`, label: "PDF Files")
- Scrollable `tk.Listbox` with `selectmode=tk.EXTENDED`
- Vertical scrollbar bound to listbox
- Below listbox: three buttons in a row: "Add PDFs", "Remove Selected", "Clear All"
- "Add PDFs" opens `filedialog.askopenfilenames` filtered to `*.pdf`
- Duplicate paths are silently skipped (check `if path not in self.file_list`)

**Output folder panel** (`ttk.LabelFrame`, label: "Output Folder")
- Label displaying the currently selected path (default: empty or "Not selected")
- Button: "Choose Output Folder" — opens `filedialog.askdirectory`
- Selected path is stored and displayed

**Options panel** (`ttk.LabelFrame`, label: "Options") — checkboxes:
- "Write replacement log (JSONL alongside each output PDF)" — default: off
- "Save intermediate cleaned text (DEBUG_<name>.txt for inspection)" — default: off
- "Dry run (run full text pipeline, skip PDF output)" — default: off

**Log panel** (`ttk.LabelFrame`, label: "Log")
- `tk.Text` widget, read-only (`state=tk.DISABLED`), word wrap, scrollable
- Log messages are appended via `self.after(0, ...)` for thread safety
- Never block the main thread with processing

**Progress bar**
- `ttk.Progressbar`, mode `determinate`
- Maximum set to total file count at run start
- Incremented after each file completes (success or failure)

**Run button**
- `ttk.Button`, text: "Start Batch Processing"
- Disabled while processing runs; re-enabled when complete
- Validates: file list not empty, output folder selected. Show `messagebox.showwarning` if either is missing. Do not start the batch.
- Launches batch in a `threading.Thread(target=self.process_worker, daemon=True)`

**Summary**
- After batch completes, print to log: total files, succeeded count, failed count, output folder path
- On Windows and Mac, attempt to open the output folder automatically (`os.startfile` / `open` / `xdg-open`) and log if this fails

### v1 Output Naming

Output files are saved as `EDITED_<original_filename>.pdf` in the selected output folder. If a file with that name already exists, append a numeric suffix: `EDITED_<name>_2.pdf`, `EDITED_<name>_3.pdf`.

### Future GUI Features (Not v1)

These are recorded for later planning and must not be built in v1:

- Novel-profile dropdown (for multi-novel support)
- Rule toggles (enable/disable individual rule categories)
- Preview panel showing extracted text before PDF rebuild
- Diff viewer showing original vs edited text
- Manual review queue for low-confidence extractions
- Retry button for failed files
- Save/load project session (file list + output folder as JSON)

---

## Batch Processing Pipeline

### Run Sequence

This is the exact order of operations when the user clicks Run. This is implemented in `scripts/core/batch_runner.py`.

```
1. Validate inputs
   - File list is not empty
   - Output folder is selected and exists (create if it doesn't, or warn)
   - At least one valid .pdf path in the list

2. Load novel-index terms for the active profile (Shadow Slave)
   - Read files/novel-index/shadow-slave.txt
   - Parse into ProtectedLexicon (see Novel-Index section)
   - Log count of loaded terms

3. For each PDF in the file list (sequential, one at a time):

   a. Log: "Processing N/total: <filename>..."

   b. Detect PDF type
      - Attempt pdfplumber text extraction
      - If extracted text is empty or below a minimum character threshold
        (suggest: fewer than 100 characters across all pages):
        log a warning, mark file as failed, continue to next
      - Do not attempt OCR on image-only PDFs in v1

   c. Extract text from PDF
      - Use pdfplumber with x_tolerance=5, y_tolerance=3
      - Concatenate pages with "\n" between them

   d. Paragraph reconstruction (pre-rule stage)
      - Run false line-break repair
      - Run dehyphenation for layout-wrap hyphens
      - Run non-breaking and special-space normalization
      - Output: coherent paragraph-delimited text

   e. Masking (protect canonical terms before any repair)
      - Mask chapter heading lines with placeholders (__WE_CH_NNNNN__)
      - Mask protected lexicon terms with placeholders (__WE_P_NNNNN__)
      - Store both maps for later restoration

   f. Run editorial pipeline (rules applied in this exact order)
      i.   Unicode cleanup (invisible chars, zero-width chars)
      ii.  Ligature normalization (ﬁ→fi, ﬂ→fl, etc.)
      iii. Scanner junk and control symbol removal
      iv.  Repeated header/footer/page-number detection and removal
      v.   Repeated chapter-title contamination removal
      vi.  Page-boundary collision repair
      vii. OCR repair pass (targeted substitution dictionary)
      viii.Spurious-space repair (single-letter splits from pdfplumber)
      ix.  Contraction and article gluing repair

   g. Unmask placeholders (restore protected terms and chapter lines)

   h. Post-mask normalization
      i.   Chapter title format normalization
      ii.  Canonical Shadow Slave name normalization
      iii. Forced recurring typo substitutions
      iv.  Punctuation repairs
      v.   Grammar repairs
      vi.  Slash replacement (/ → " out of ")
      vii. Final dedicated spaced em-dash sweep (second pass mandatory)
      viii.Duplicate chapter title removal
      ix.  Chapter page-break insertion (for PDF builder)
      x.   Chapter heading validation (log any malformed headings)

   i. If dry run: skip PDF build. Log "Dry run: skipped PDF output."

   j. Build output PDF
      - Times-Roman 11pt justified body, 15pt leading, 6pt spacing
      - Helvetica-Bold 14pt left-aligned chapter headings, color #134252
      - 0.5 inch margins on all sides
      - Page breaks between chapters
      - Merged chapter+body split detection (heading not mixed with body text)

   k. Remove orphan single-heading pages from output PDF
      (pages where the only content is a chapter heading line)

   l. Save output PDF to chosen output folder as EDITED_<original_name>.pdf

   m. If replacement log enabled: write EDITED_<name>_replacements.jsonl
   n. If debug text enabled: write DEBUG_<name>.txt (intermediate cleaned text)
   o. Log result: ✓ success or ✗ failure with error message

4. After all files: log summary
   - "Batch complete. X of Y files processed successfully. Z failed."
   - List failed filenames if any
   - Attempt to open output folder
```

### Error Handling

- Each file is wrapped in its own `try/except` block
- A failure on one file logs the traceback and continues to the next
- Fatal errors (e.g., output folder cannot be written) halt the batch and display `messagebox.showerror`
- Low-confidence extraction (too little text extracted) is logged as a warning, not a crash

---

## Editing Rules — Shadow Slave

This section defines the complete rule set for the Shadow Slave pipeline. These rules are implemented across the modules in `scripts/rules/` and coordinated by `scripts/pipelines/shadow_slave.py`.

All rules are mechanical. No rule rewrites prose, improves style, changes tone, or makes judgment calls about meaning. When certainty is low, the rule leaves the text unchanged.

### Rule Application Order (Canonical)

Apply in exactly this order. Order matters because earlier stages expose issues that later stages fix.

```
1.  Unicode cleanup — invisible, zero-width, directional chars
2.  Ligature normalization
3.  Non-standard spacing normalization
4.  Scanner junk and control symbol removal
5.  Repeated header/footer/page-number removal
6.  Repeated chapter-title contamination removal
7.  Page-boundary collision repair
8.  Paragraph reconstruction (false line-break repair, dehyphenation)
9.  MASK chapter lines and protected terms
10. OCR repair dictionary pass
11. Spurious-space repair (pdfplumber extraction artifacts)
12. Contraction and article-gluing repair
13. UNMASK placeholders
14. Chapter title format normalization
15. Canonical name normalization
16. Forced recurring typo substitutions
17. Punctuation repairs
18. Grammar repairs
19. Slash replacement (/ → " out of ")
20. Final spaced em-dash sweep (mandatory second pass)
21. Duplicate chapter title removal
22. Chapter page-break insertion
23. Chapter heading validation (log only, no auto-fix)
```

---

### Stage 1 — Unicode Cleanup

**Module:** `scripts/rules/unicode_cleanup.py`

Remove invisibles:
- U+200B zero-width space
- U+200C zero-width non-joiner
- U+200D zero-width joiner
- U+FEFF zero-width no-break space (BOM)
- Any other directional or formatting invisible character that disrupts processing

Normalize Unicode form to NFC before rule application so visually identical characters do not behave as different tokens.

Convert irregular space-like characters that function as plain spaces to U+0020:
- U+00A0 non-breaking space → standard space
- U+2009 thin space → standard space
- U+2002 en space, U+2003 em space → standard space
- U+202F narrow no-break space → standard space
- U+205F medium mathematical space → standard space
- U+3000 ideographic space → standard space (unlikely in prose but handle it)

Normalize corrupted or inconsistent apostrophes and quotation marks to their correct Unicode forms when extraction created malformed or mismatched pairs. Preserve valid curly quotes that are internally consistent.

---

### Stage 2 — Ligature Normalization

**Module:** `scripts/rules/ligature_cleanup.py`

Before any spell or rule processing, normalize PDF ligature characters:

| Source | Replacement |
|---|---|
| `ﬁ` (U+FB01) | `fi` |
| `ﬂ` (U+FB02) | `fl` |
| `ﬀ` (U+FB00) | `ff` |
| `ﬃ` (U+FB03) | `ffi` |
| `ﬄ` (U+FB04) | `ffl` |
| `ﬅ` (U+FB05) | `st` |
| `ﬆ` (U+FB06) | `st` |

Apply globally. Run before any other text processing.

---

### Stage 3 — Non-Standard Spacing and Scanner Junk

**Module:** `scripts/rules/unicode_cleanup.py` (same module, separate functions)

**Scanner junk and control symbol removal:**
- Remove stray black squares (U+25A0, U+25A1)
- Remove replacement glyphs (U+FFFD)
- Remove stray null bytes and other non-printing control characters (U+0000–U+001F except U+000A newline and U+000D carriage return)
- Flag as extraction artifact, not prose error
- Do not guess at intended character — strip only

**Duplicate space collapse:**
- Replace two or more consecutive spaces with one space, except at paragraph boundaries

---

### Stage 4 — Header/Footer/Page-Number Removal

**Module:** `scripts/rules/spacing_cleanup.py`

**Current v0.6.1 safety decision:** This stage is a logged no-op until extraction preserves
per-page position metadata. Concatenated page text cannot safely identify headers, footers,
or page numbers without risking prose loss.

**Page-number removal:**
- Detect standalone integers on their own line that correspond to page numbers
- Remove when they appear in contexts consistent with PDF extraction (top or bottom of page-text blocks)

**Repeated header/footer removal:**
- Compare top and bottom lines across extracted page blocks
- A line that appears in the same position across the majority of pages (threshold: 60%+) is a header or footer artifact
- Remove those recurring lines from all pages
- This is a heuristic, not a guarantee; log when lines are removed this way

**Repeated chapter-title contamination:**
- Detect when the normalized chapter title appears more than once in the extracted text body (beyond its first occurrence)
- Remove all recurrences after the first canonical instance
- Implemented via `remove_duplicate_chapter_titles_global()` — direct port from `ss_pdf_editor-v1.py`

---

### Stage 5 — Page-Boundary Collision Repair

**Module:** `scripts/rules/spacing_cleanup.py`

PDF extraction sometimes fuses the last word of one page with the first word of the next, or splits a word across the page boundary.

- Detect words fused at page boundaries by checking if a long token contains a known word boundary that was dropped
- Detect mid-word breaks where a word is split into fragments by a page transition
- Repair when the intended word is obvious from the token
- Do not repair when the intended split is ambiguous

---

### Stage 6 — Paragraph Reconstruction

**Module:** `scripts/rules/spacing_cleanup.py`

**False line-break repair:**
- PDF layout breaks lines at fixed column widths, not at paragraph boundaries
- A line break that does not follow terminal punctuation (`.`, `!`, `?`, `:`) and is followed by a lowercase letter is a false break
- Join these with a space, not a paragraph break
- Preserve breaks that follow terminal punctuation or are followed by a capital letter that starts a new sentence or a chapter heading

**Dehyphenation:**
- Rejoin a wrapped hyphenated word while preserving the hyphen by default:
  `well-\nknown` → `well-known`
- Strip a hyphen only for an explicit known-safe wrap such as `sur-\nface` → `surface`
- Preserve legitimate compound hyphens: `three-storied`, `hand-to-hand`

**Single-letter split repair (pdfplumber artifact):**
- pdfplumber sometimes inserts spurious spaces: `d efending` → `defending`
- Pattern from `sm_pdf_editor-v8.2.py`, function `fix_spurious_spaces()`
- Handle the article-`a` exception: do not merge `a spell` into `aspell`
- Maintain explicit fix list for common cases (`would`, `could`, `should`, `into`, `only`, etc.)

---

### Stage 7 — Masking

**Module:** `scripts/core/protected_lexicon.py`

Before OCR repair and spellcheck-adjacent passes, protected terms and chapter headings must be masked with placeholder tokens so that repair passes cannot corrupt them.

**Chapter line masking:**
- Any line starting with `Chapter` (case-insensitive) + a digit is replaced with a placeholder token `__WE_CH_NNNNN__`
- A mapping dict stores `{placeholder: original_line}`
- Implement as direct adaptation of `mask_chapter_lines()` from study examples

**Protected term masking:**
- All terms from the loaded `ProtectedLexicon` are masked with `__WE_P_NNNNN__`
- Terms are sorted longest-first before masking so multi-word phrases are matched before their component words
- Single-word terms use letter-boundary matching (not `\b`) to catch terms adjacent to punctuation
- Multi-word terms use `\s+` between words for flexible whitespace
- Expand variants: add possessive (`Sunny's`, `Sunny\u2019s`) and plural (`Sunnys`) forms before masking
- A mapping dict stores `{placeholder: original_term}`

**Unmasking:**
- After all repair passes, restore protected terms first, then chapter lines
- Implement as adaptation of `unmask_placeholders()` from study examples

**Placeholder format:** `__WE_CH_NNNNN__` and `__WE_P_NNNNN__` (five-digit zero-padded index). Use `WE` prefix (Webnovel Editor) to avoid collision with the SM editor's `SM` prefixes if study-example patterns are copied.

---

### Stage 8 — OCR Repair

**Module:** `scripts/rules/ocr_repair.py`

Apply only inside non-placeholder segments. Never mutate placeholder tokens.

**Targeted substitution dictionary (extendable):**

| OCR error | Correction | Condition |
|---|---|---|
| `tbe` | `the` | standalone word |
| `tiie` | `the` | standalone word |
| `bis` | `his` | standalone word |
| `liis` | `his` | standalone word |
| `l am` | `I am` | start of sentence or after punctuation |
| `tlie` | `the` | standalone word |
| `0f` | `of` | standalone word |
| `0n` | `on` | standalone word |
| `t0` | `to` | standalone word |
| `0r` | `or` | standalone word |
| `0ne` | `one` | standalone word |
| `fi` (ligature missed) | `fi` | already handled in Stage 2, but catch residuals |

**Zero-to-O repair in words:**
- `t0wer` → `tower`, `b0dy` → `body`, `fl0or` → `floor`
- Pattern: a digit `0` between letter characters → `o`
- Port from `fix_zero_to_o()` in study examples

**L-to-I repair:**
- Standalone lowercase `l` where `I` (pronoun) is clearly intended (start of sentence, before apostrophe-m, etc.)
- Only apply when context is clear

**Dotted-word repair:**
- `h.i.p.s` → `hips`, sequences of letter-dot pairs → joined word
- Port from `fix_dotted_words()` in study examples

**Weird-character-in-word repair:**
- `|` between letters → `l` (pipe misread as lowercase L): `V|adion` → `Vladion`
- `\` between letters → `r`
- Port from `fix_weird_characters_in_words()` in study examples

This list grows over time as new recurring OCR errors are found. The module should be designed so new entries can be added to a dictionary without modifying logic.

---

### Stage 9–13 (Post-Unmask) — Editorial Rules

#### Chapter Title Normalization

**Module:** `scripts/rules/chapter_titles.py`

**Required format:**

```
Chapter N: Title.
```

Where:
- `Chapter` is capitalized normally
- `N` is the exact chapter number as written in the source — do not zero-pad, do not reformat unless a comma separator is appropriate for 1,000+
- There is a colon, a single space, then the title
- Title ends with a period
- No trailing spaces

**Allowed normalizations:**
- Fix capitalization of "Chapter" if wrong
- Insert colon if missing between number and title
- Insert closing period if missing
- Correct obvious formatting typos only if the intended word is already present
- Remove stray spaces around the chapter number

**Forbidden:**
- Do not invent a missing title
- Do not rename or rephrase a title for any reason
- Do not alter title wording unless correcting a clear mechanical typo

If a heading has no title, preserve it as `Chapter N` with no colon or period and log it as
a malformed heading. Do not invent punctuation.

**Detection regex** (IGNORECASE, MULTILINE):

```python
re.compile(r"^Chapter\s+(\d[\d,]*)\s*[:\-–—]?\s*(.+?)\.?\s*$", re.IGNORECASE | re.MULTILINE)
```

**Examples:**

| Input | Output |
|---|---|
| `chapter 1 awakening` | `Chapter 1: Awakening.` |
| `Chapter 10 The Castle` | `Chapter 10: The Castle.` |
| `Chapter 100: The Seventh Seal` | `Chapter 100: The Seventh Seal.` |
| `Chapter 1,000: The End of Dawn.` | `Chapter 1,000: The End of Dawn.` |
| `CHAPTER 287 - Into the Dark` | `Chapter 287: Into the Dark.` |

---

#### Canonical Name Normalization

**Module:** `scripts/profiles/shadow_slave/canonical_names.py`

The canonical name set is defined as a `frozenset[str]`. This is loaded from the profile, not from `novel-index/`. The `novel-index/` system handles user-maintained additions.

**Canonical names — source of truth for Shadow Slave:**

```python
SS_CANONICAL_NAMES: frozenset[str] = frozenset({
    # Main cast
    "Sunny", "Sunless", "Nephis", "Neph", "Cassie", "Cassia",
    "Kai", "Night", "Effie", "Jet", "Rain", "Rani",
    # Supporting
    "Ananke", "Gunlaug", "Caster", "Hector", "Athena", "Harper",
    "Bloodwave", "Tyris", "Roan", "Obel", "Dale", "Naomi", "Verne",
    "Luster", "Kim", "Kimmy", "Morgan", "Winter", "Samara", "Belle",
    "Dorn", "Quentin", "Seishan", "Beastmaster",
    "Dire Fang", "Silent Stalker", "Blood Sage", "Hollow", "Nightmare",
    "Song Seer", "Song Hunter", "Song Knight", "Mordret", "Asterion",
    "Anvil", "Broken Sword", "Smile of Heaven", "Weaver",
    "The Forgotten God", "War God", "Storm God", "Sun God", "Beast God",
    "Shadow God", "Saint", "Scavenger", "Goliath", "White Feather",
    "Iron Hand", "Black Lion", "Silver Fang", "Silent Blade",
    "Fallen Grace", "Mountain King", "Crimson Terror", "Winter Beast",
    "Fallen Devil", "Stone Saint", "Dread Lord", "Nightmare Steed",
    "Soul Devourer",
    "Felix", "Rin", "Mark", "Lucas", "Elliot", "Theo", "Noah",
    "Grace", "Iris", "Paul", "Mia", "Victor", "Leon", "Eric",
})
```

This set is the built-in floor. It is always loaded. The `files/novel-index/shadow-slave.txt` file adds terms on top of this.

---

#### Forced Recurring Typo Substitutions

**Module:** `scripts/profiles/shadow_slave/special_fixes.py`

Apply these while protected terms are still masked. They correct unprotected text without
ever altering a user-protected term.

```python
SS_SPECIAL_FIXES: dict[str, str] = {
    "Almanach": "Almanac",
    "carcassess": "carcasses",
    "threestoried": "three-storied",
    "tompost shelf": "topmost shelf",
    "Obers": "Obels",
}
```

Note on `Obers → Obels`: `Obel` is a canonical name (protected). `Obers` is a misprint of `Obels` (plural). This forced fix is distinct from the name protection.

This dict must be easy to extend. New entries are added here when recurring typos are identified across chapters.

---

#### Punctuation Repairs

**Module:** `scripts/rules/punctuation.py`

- Remove duplicate punctuation: `..` → `.`, `,,` → `,`, `??` → `?`, `?!.` → `?!` (or context-appropriate)
- Insert missing space after comma, period, semicolon, colon, `!`, `?` when absence is clearly accidental (`word,word` → `word, word`)
- Remove space incorrectly inserted before punctuation (`word ,` → `word,`)
- Repair fused sentence-end: `word.Word` → `word. Word` when clear sentence boundary
- Do not add commas for style. Only fix clear grammatical omissions.
- Parenthesis and quotation balancing: repair clearly broken closing punctuation only when the intended closure is obvious. Do not invent punctuation in ambiguous cases.

---

#### Grammar Repairs

**Module:** `scripts/rules/grammar.py`

Apply only when the correction is unambiguous:

- Article agreement: `a explosion` → `an explosion`, `an book` → `a book`
- Subject-verb agreement: `there was many` → `there were many` — only when subject is unambiguous
- Obvious pronoun mistakes when referent is clear from immediate context
- Tense consistency within the same sentence — do not rewrite across sentences
- Sentence fragments only when clearly accidental grammatical errors
- Run-ons only when mechanically broken, not deliberate long sentences
- Do not guess on ambiguous constructions. Leave unchanged.

**American English preference:**
When a correction requires choosing between variant spellings, use American English:
`centre` → `center`, `armour` → `armor`, `kilometres` → `kilometers`, `fervour` → `fervor`, `channelled` → `channeled`

Only apply when making a correction that requires choosing a variant. Do not mass-replace British spellings throughout the text.

---

#### Slash Replacement

**Module:** `scripts/rules/slash_replace.py`

Replace numeric ratios with ` out of `; do not apply any replacement to other slashes.

```python
X_OF_Y_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
# 6/7 → 6 out of 7
```

**Final rule (v0.6.1): numeric slash → "out of"; all other slashes preserved verbatim.**
Convert a digit/digit ratio only (`6/7` → `6 out of 7`, `10/20` → `10 out of 20`). Every
other slash — `and/or`, `his/her`, `yes/no`, any word/word form — is left **exactly as
written**, with no substitution and no mapping table, because its intended spoken form
cannot be inferred safely.

Exception: do not apply inside placeholder tokens. Apply only outside `__WE_CH_*` and `__WE_P_*` segments (use the non-placeholder segment wrapper).

---

#### Spaced Em-Dash Removal — Mandatory Two-Pass Rule

**Module:** `scripts/rules/em_dash.py`

**The character `—` with spaces on both sides must never appear in output.**

Replacement logic:

| Context | Replacement |
|---|---|
| Parenthetical interruption | `, ` |
| Closely related independent clauses | `; ` |
| Ends one sentence, starts another (next word capitalized) | `. ` |

Two-pass requirement:
- After all other edits, run a dedicated second pass searching exclusively for spaced em-dashes
- Every remaining instance must be replaced before producing final output
- This pass is non-negotiable and runs for every file without exception

Also handle:
- NBSP + em-dash + NBSP combinations
- En-dash (U+2013) surrounded by spaces (same treatment)
- Horizontal bar (U+2015) surrounded by spaces
- Two-em-dash (U+2E3A) surrounded by spaces

Unspaced dashes (`word—word`) are **not** affected by this rule.

Port the core logic from `remove_spaced_em_dashes()` in `ss_pdf_editor-v1.py`. That function is confirmed working.

---

## Novel-Index Protection System

### Purpose

The `novel-index/` folder contains user-maintained plain text files listing protected terms for each novel. Terms in these files are loaded before any spell correction or normalization runs and are shielded from unwanted alteration.

This is separate from the built-in canonical name sets in `scripts/profiles/`. The novel-index files are user-editable and grow over time as the user identifies new terms to protect.

### Folder Layout

```
novel-index/
  shadow-slave.txt        ← active, 6KB, has content
  circle-of-inevitability.txt
  lord-of-the-mysteries.txt
  re-monster.txt
  renegade-immortal.txt
  reverend-insanity.txt
  supreme-magus.txt
  the-noble-queen.txt
```

Each file corresponds to a novel profile. The filename (minus extension) maps to the profile key. As of this revision, **only `shadow-slave.txt` is populated (~5.6 KB)** — the other seven are intentional empty placeholders (0 bytes), reserved for novels not yet onboarded. The loader must treat an empty or missing index file as "no user terms for this novel" and fall back cleanly to the built-in canonical set, not error. Adding a new novel means populating its file here and adding a profile in `scripts/profiles/`.

If a set of protected terms is genuinely universal (e.g. terms that should never be altered in any novel), prefer keeping them in the relevant rule logic or a clearly-labeled shared list rather than copy-pasting into every per-novel index file. For v1, focus only on `shadow-slave.txt`.

### File Format

One protected term or phrase per line. Rules:
- Lines beginning with `#` are comments — ignored entirely
- Blank lines are ignored
- Case is preserved in storage
- Matching in code is case-aware: the term `Sunny` protects `Sunny` but not `sunny` unless the match logic explicitly covers case variants
- Multi-word phrases are supported: `The Forgotten God`, `Dire Fang`
- No duplicate entries (duplicates are deduplicated silently during load)

### Loading

Implemented in `scripts/core/protected_lexicon.py`.

Port `_load_terms_from_file()` from the study examples. This function:
- Reads UTF-8 text file
- Strips `#`-based comments from each line
- Skips blank lines
- Supports both `.txt` (one per line) and `.json` (list or `{"terms": [...]}`) formats

`load_protected_lexicon()` merges the built-in canonical names with file-loaded terms:
1. Start with built-in `SS_CANONICAL_NAMES` frozenset
2. Load `files/novel-index/shadow-slave.txt`
3. Deduplicate (preserve first occurrence)
4. Sort: multi-word phrases first (longest first), then single-word terms (longest first)
5. Return as `ProtectedLexicon(terms=tuple, term_set_lower=frozenset)`

Longest-first ordering is required so multi-word phrases are masked before their component words.

### Matching

During masking, protected terms use:
- For multi-word terms: `\s+` between words, case-insensitive match
- For single-word terms: letter-boundary matching (not `\b`) — `(?<![A-Za-z])(term)(?![A-Za-z])` with IGNORECASE — to catch terms adjacent to punctuation without missing them

Expand possessive and plural variants before masking:
- `Sunny` → also protect `Sunny's`, `Sunny\u2019s`, `Sunnys`

### Growth Over Time

The user adds new terms to `files/novel-index/shadow-slave.txt` as they are discovered. The system loads the file fresh every run, so additions take effect immediately without any code change.

Shadow Slave world-specific terms that should be in this file include (expand as chapters are processed):
- Named progression ranks and tiers
- Location names (Forgotten Shore, named dungeons, named regions)
- Named abilities and spell names
- Named artifacts and weapons
- Creature and faction names
- Story-specific capitalized abstract concepts

---

## Multi-Novel Architecture

The repo is designed from the start to support multiple novels. Only Shadow Slave is implemented in v1. The structure must not require refactoring when a second novel is added.

### How to Add a New Novel

1. Add `files/novel-index/<novel-name>.txt` with protected terms
2. Add `scripts/profiles/<novel-name>/canonical_names.py` with the name set
3. Add `scripts/profiles/<novel-name>/special_fixes.py` with forced substitutions
4. Add `scripts/pipelines/<novel-name>.py` implementing the pipeline for that novel
5. Update the GUI novel-profile dropdown (future v2 feature) to include the new profile
6. Add test files in `scripts/tests/` for the new profile

No core modules need to be modified. The pipeline is a per-novel file that calls shared rule modules.

### Profile Interface Convention

Every pipeline module (e.g., `shadow_slave.py`) must expose:

```python
def run_pipeline(text: str, lexicon: ProtectedLexicon, *, repl_log=None, gui_log=None, dry_run=False) -> str:
    ...
```

The batch runner calls `run_pipeline()` on whichever profile is active. Swapping profiles means swapping which module is imported.

### Universal vs. Novel-Specific Rules

Not every correction is tied to Shadow Slave. Many edits are **universal** — true for any webnovel regardless of series — and should be written so they can be reused across every novel without duplication:

- **Universal rules** (apply to all novels): Unicode/ligature cleanup, spacing repair, OCR-artifact repair (`fix_zero_to_o`, dotted-word repair, spurious single-letter splits), spaced em-dash removal, `X/Y → X of Y` slash normalization, generic punctuation and grammar fixes, duplicate-chapter-title removal, chapter-title formatting. These live in `scripts/rules/` as the shared, stateless functions they already are, and any novel's pipeline may call them.
- **Novel-specific data** (apply only to one novel): canonical character/place names, forced substitutions, and the protected-term list. These live in `scripts/profiles/<novel>/` (`canonical_names.py`, `special_fixes.py`) and `files/novel-index/<novel>.txt`. They are *data the universal rules consume*, not separate rule logic.

The design goal: a novel's pipeline file (`pipelines/<novel>.py`) is mostly a thin ordering of universal rules, parameterized by that novel's profile data. Adding a novel should rarely require new rule code — only new profile data — unless the novel has a genuinely unique formatting quirk, in which case a novel-specific rule may be added but kept clearly scoped to that profile. **Shadow Slave is the first profile, and its pipeline is the reference implementation** every later novel's pipeline is modeled on. When building the Shadow Slave pipeline, keep the universal/profile-data split clean so the second novel is a data exercise, not a refactor.

---

## Safeguards

- **Never overwrite originals.** The app only reads from input paths. Output is always written to a separate user-selected folder. Input files are never opened for writing.
- **Sanitize output filenames.** Strip or replace characters that are illegal in file paths on Windows and Mac. Limit filename length.
- **Continue on file failure.** Each file is wrapped in its own try/except. One failure does not stop the batch.
- **Log everything.** Per-file success/failure, pipeline stage completions, and warnings are logged to the GUI log widget and optionally to a session log file.
- **Keep the JSONL replacement log.** Optional but recommended. Every substitution made by the pipeline is logged with: original, replacement, context snippet, rule name, source category.
- **Keep protected terms separate from correction logic.** The `novel-index/` system only prevents unwanted changes. The `special_fixes` dict enforces required changes. These are different systems with different roles.
- **Validate extraction quality.** If a PDF yields fewer than 100 characters of text across all pages, log a low-confidence warning and skip rather than producing a malformed output.
- **Warn on non-normalized chapter headings.** After title normalization, scan for any line starting with `Chapter` that does not match the expected format. Log a warning. Do not crash.
- **Modular and testable rules.** Every rule function is a pure function: string in, string out. No side effects. No global state. This makes each rule independently testable with pytest.
- **Dry-run mode.** The full text pipeline runs but no PDF is written. Useful for testing rule changes without producing files.
- **Debug text output.** Intermediate cleaned text can be saved as `.txt` alongside output PDFs for human inspection.

---

## Study-Examples Reference

The `files/study-examples/` folder contains partial working scripts from earlier webnovel-editor attempts. These are reference material — they show the patterns and behaviors the user has already tried and what worked, so proven logic can be borrowed rather than re-derived. Read them to understand prior approaches before writing new code. The folder is reference-only; it is not part of the shipped product and may be deleted by the user after Phase 1 is confirmed working.

### What to Borrow

| File | What to take |
|---|---|
| `ss_pdf_editor-v1.py` | `remove_spaced_em_dashes()` — confirmed working two-pass em-dash removal. `normalize_x_of_y()` — slash replacement regex. `create_pdf_from_text()` — reportlab PDF builder (Times-Roman body, Helvetica-Bold headings, #134252 heading color, 0.5in margins, justified body). `remove_duplicate_chapter_titles_global()` — confirmed working. `SS_CANONICAL_NAMES` frozenset — canonical name list. `SS_SPECIAL_FIXES` dict — forced substitutions. `ReplacementLog` and `ReplacementEntry` — port directly. `ProtectedLexicon` dataclass — port directly. `_load_terms_from_file()` — port directly. |
| `sm_pdf_editor-v8.2.py` | `mask_chapter_lines()` — confirmed working placeholder masking. `mask_protected_terms()` — longest-first masking logic. `unmask_placeholders()` — restoration logic. `expand_lexicon_variants()` — possessive/plural expansion. `fix_spurious_spaces()` — pdfplumber single-letter split repair. `fix_weird_characters_in_words()` — pipe/slash/backslash in word repair. `fix_zero_to_o()` — OCR digit-to-letter repair. `fix_dotted_words()` — dotted letter sequence repair. `fix_merged_possessive_contraction()` — contraction space repair. GUI pattern: `threading.Thread`, `self.after(0, ...)` for thread-safe log updates, `ttk.Progressbar`, `ttk.LabelFrame` layout, `filedialog.askopenfilenames`, `filedialog.askdirectory`. `run_smoke_tests()` — adapt the smoke test pattern for SS pipeline. Extract function `extract_text_from_pdf()` — pdfplumber with `x_tolerance=5, y_tolerance=3`. |
| `Shadow_Slave_Instructions-1.txt` | Reference for the editorial intent. Rules in this spec supersede it where they conflict (e.g., the four-digit chapter number format in that file is overridden — use exact number as given). |
| `scrape_noble_queen_webnovel-v1.py` / `scrape_noble_queen-v3.py` / `freewebnovel-webscraper.py` | These are web scrapers, not editors. Not relevant to the build spec. Do not port any logic from them. They are in study-examples only for completeness. |

### What Not to Port

- SymSpell integration — not in SS v1 scope
- Profanity uncensoring maps — not in SS v1 scope
- `fix_ragnarok_name_artifacts()` — SM-specific, not SS
- Supreme Magus canonical names — wrong profile
- The SM editor's auto-output-folder-in-Downloads behavior — the webnovel editor uses user-selected output folder

---

## Test Assets

Real Shadow Slave chapter PDFs have been added for testing the pipeline against actual source material. Shadow Slave is the **first and primary target** for the editor, so this set defines exactly the kind of editing the tool must get right:

```
files/pdf-example-chapters/
    └── webscraped_shadow_slave/   ← full set of webscraped Shadow Slave chapter PDFs — the canonical test corpus
```

The `webscraped_shadow_slave/` folder holds the complete run of scraped chapters and is the **primary known-input corpus** for the build. Use these real PDFs — not synthetic text — whenever a phase calls for running chapters through the pipeline, and when writing pytest tests that need a real PDF. The output the tool produces from these chapters is the standard the Shadow Slave editing is measured against.

**How to use them:**

- **Phase 3 (extraction/output)** — run a handful from `webscraped_shadow_slave/` through extract → rebuild with no rules, confirm output PDFs are correct, named `EDITED_<name>.pdf`, and that originals are untouched.
- **Phase 4 (rule engine)** — run the full pipeline over a representative spread of these chapters and inspect output PDFs and JSONL logs against the expected Shadow Slave editing behavior.
- **Phase 6 (testing)** — wire a small, fixed subset into the pytest suite as committed fixtures so the smoke test and rule tests run against genuine extraction output, not hand-crafted strings.

**Before relying on them, inventory the folder.** List what is actually present in `webscraped_shadow_slave/`, note page counts and whether each is text-extractable (the v1 pipeline does not support image-only scanned PDFs — flag any that are scans). Pick a stable subset to pin as test fixtures so tests stay deterministic; do not assume a specific filename exists without checking. The folder may hold a large number of chapters — choose a representative spread (early, middle, late chapters), not all of them, for the committed fixture set.

If a chosen fixture PDF is large, consider whether it should be committed to the repo or gitignored and referenced locally — confirm with the user before committing large binaries. As more novels are onboarded later, additional `files/pdf-example-chapters/webscraped_<novel>/` folders are expected to follow the same convention.

---

## Skills

Before scaffolding the repo, the coding agent should draw on a local library of reusable skills to make setup faster and the editor itself more polished. These skills are a clone of the [`alirezarezvani/claude-skills`](https://github.com/alirezarezvani/claude-skills) GitHub repository, downloaded and unzipped locally.

### Skills Source

```
C:\Users\ematthew\Desktop\Apps\Coding\claude-skills-main
```

This is an unzipped download of `https://github.com/alirezarezvani/claude-skills`. It sits alongside the workspace roots, not inside this project. Treat it as **read-only** reference material — copy/adapt skills out of it into the project's own skills folder, but do not modify the source.

### What the Agent Must Do

1. **Discover.** Scan the skills source directory above and read each skill's `SKILL.md` (or equivalent descriptor) to learn what is actually available. List the folder and read the descriptors — do not assume contents.

2. **Match to the work.** Identify skills relevant to this project, specifically:
   - **Project setup and scaffolding** — repo structure, Python project layout, venv setup, startup scripts, `requirements.txt` conventions.
   - **GUI polish** — anything that improves the Tkinter editor's layout, usability, or visual quality so it feels more refined than a bare default window.
   - **PDF handling, text processing, testing, or packaging** — anything overlapping the extraction, rule-engine, pytest, or PyInstaller work in this spec.

3. **Pull into the project's skills folder.** Copy the genuinely useful skills into the agent's own skills directory in this repo (`.claude/skills/` for Claude Code, `.codex/skills/` for Codex), one folder per skill, each with its `SKILL.md`. This is done as a setup step **before** implementation begins.

4. **Use what fits, and report it.** When a skill applies to a task, use it rather than re-deriving the pattern. In the build plan and in `BRIEFING.md`, list which skills were pulled in and where each will be applied. If the scan turns up nothing useful, say so explicitly and proceed with this spec alone.

### Constraints

- This is a **best-effort enhancement layer, not a hard dependency.** If the skills folder is missing, empty, or irrelevant, the build proceeds normally on this spec alone. Never block on the skills library being present.
- Skills **supplement** this spec; they do not override it. Where a skill's pattern conflicts with an explicit instruction here (repo structure, tech stack, naming, editing rules), this spec wins.
- Do not adopt heavy dependencies or frameworks from a skill just because the skill uses them. Honor the locked tech stack (Tkinter, pdfplumber, reportlab, PyPDF2, pytest — no second PDF library, no SymSpell in v1).

---

## Implementation Phases

### Phase 1 — Repo Scaffold and Startup Scripts

Deliverables:
- **Map the live repo first** and reconcile any drift from the Confirmed Repo Structure with the user (folder names like `md-instruction/` vs `md-instructions/`, and the `files/` nesting of `novel-index`, `study-examples`, `pdf-example-chapters`)
- **Pull relevant skills** from the skills source into `.claude/skills/` (and `.codex/skills/` for Codex) per the [Skills](#skills) section, and note which were pulled in `BRIEFING.md`
- Complete folder structure as specified above (all `__init__.py` files, all stub modules)
- `requirements.txt` with correct package versions
- `scan for libraries and run (batch file) - for windows11.bat`
- `setup_and_run_webnovel.ps1`
- `scan for libraries and run (sh file) - for mac.sh`
- `README.md` with project description and basic usage
- `md-instructions/BRIEFING.md` updated with Phase 1 completion status
- `md-instructions/EDITING-RULES.md` populated from this spec's editing rules section

Test: double-click the `.bat` on Windows 11 and confirm it scans Python, creates venv, installs requirements, and launches `scripts/main.py` (which can be a stub that prints "Hello" for now).

After Phase 1 is confirmed working: `study-examples/` can be deleted.

### Phase 2 — GUI Shell

Deliverables:
- `scripts/gui/app.py` — full Tkinter window with all v1 UI elements
- `scripts/main.py` — launches the GUI
- File list with Add/Remove/Clear
- Output folder picker
- Options checkboxes (replacement log, debug text, dry run)
- Log widget and progress bar
- Run button (wired to placeholder `process_worker` that logs "Would process N files")
- Summary message after mock run

Test: launch the app, add several PDF files, choose an output folder, click Run, confirm log output and progress bar work correctly. Confirm the GUI does not freeze.

### Phase 3 — PDF Extraction and Output Generation

Deliverables:
- `scripts/pdf/extractor.py` — pdfplumber extraction, low-confidence detection
- `scripts/pdf/builder.py` — reportlab PDF builder (port `create_pdf_from_text()` from study examples)
- `scripts/core/batch_runner.py` — full batch loop (extract → no rules yet → rebuild PDF)
- Output: `EDITED_<name>.pdf` saved to selected output folder
- Low-confidence extraction warning in log

Test: run several real chapter PDFs from `files/pdf-example-chapters/` through the app with no rules applied and confirm the output PDFs are generated, named correctly, saved to the right folder, and originals are untouched.

### Phase 4 — Shadow Slave Rule Engine

Deliverables:
- All rule modules in `scripts/rules/`
- `scripts/profiles/shadow_slave/canonical_names.py`
- `scripts/profiles/shadow_slave/special_fixes.py`
- `scripts/pipelines/shadow_slave.py` — full 23-stage pipeline
- `scripts/core/replacement_log.py` — `ReplacementLog` and `ReplacementEntry`
- JSONL log output when option is enabled
- Debug text output when option is enabled

Test: run the full pipeline on five representative Shadow Slave chapters from `files/pdf-example-chapters/`. Review output PDFs for correctness. Review JSONL logs for expected replacements. Confirm em-dash removal, slash replacement, chapter title normalization, and name preservation all work correctly.

### Phase 5 — Novel-Index Protection System

Deliverables:
- `scripts/core/protected_lexicon.py` — full `load_protected_lexicon()`, `mask_protected_terms()`, `unmask_placeholders()`, `expand_lexicon_variants()`
- Integration with Shadow Slave pipeline
- `files/novel-index/shadow-slave.txt` populated with initial content

Test: add a term to `files/novel-index/shadow-slave.txt` that would otherwise be altered by a rule. Run a chapter through the pipeline and confirm the term is preserved unchanged.

### Phase 6 — Testing and Packaging

Deliverables:
- Pytest test suite covering all rule modules
- Smoke test for the full pipeline
- All tests pass on both Windows 11 and Mac
- `BRIEFING.md` updated with test status

Optional Phase 6 deliverable (not required for v1 release):
- PyInstaller spec file for single-exe packaging

### Phase 7 — Multi-Novel Expansion Support

Deliverables:
- Novel-profile dropdown in GUI
- Second novel profile scaffolded (whichever is chosen next)
- `files/novel-index/<second-novel>.txt` populated
- Pipeline for second novel implemented
- Tests for second novel pipeline

---

## BRIEFING.md Maintenance Contract

Claude Code must update `md-instructions/BRIEFING.md` at the end of every work session. This is not optional.

The file follows this structure and is appended/updated in place:

```markdown
# Webnovel Editor — Project Briefing

## Last Updated
[Date] — [Phase N]

## Current Phase
[Current phase name and number]

## What Was Just Built or Changed
- [bullet list of files created or significantly modified]

## What Is Working
- [bullet list of confirmed working components, with brief note on how tested]

## Skills Pulled / Used
- [skills pulled into .claude/skills or .codex/skills from the skills library, and where applied — or "none relevant found"]

## What Is Broken or Incomplete
- [bullet list of known issues, partial implementations, or missing pieces]

## Open Questions / Decisions Needed
- [anything requiring human input before the next session can proceed]

## Files Changed in Last Session
- [explicit list of paths]

## Next Steps
- [what the next Claude Code session or human should tackle first]
```

This file is used by:
- The project owner to understand current status at a glance
- Claude Code at the start of a new session to restore context without re-reading all source files
- Cursor IDE to understand active issues and recent changes
- Any other AI tool brought in to assist at any point in the project

Write it so a fresh AI with zero prior context can read it and immediately understand what the project is, where it is in the roadmap, and what needs to happen next.

---

## Risks and Open Questions

**PDF extraction quality variance**
Different PDF sources extract differently. pdfplumber with `x_tolerance=5, y_tolerance=3` works well for the study examples but may need tuning per source. Log extraction character counts and monitor.

**Chapter title detection edge cases**
Chapter title regex needs to handle variations found in real chapter PDFs. The study-example regex patterns are a good starting point but will need refinement once real files are tested.

**Novel-index file encoding**
All novel-index files must be UTF-8. The loader should handle encoding errors gracefully and log them rather than crashing.

**Tkinter on Mac**
Tkinter on macOS can have rendering issues depending on the Python build. Test the GUI on Mac early. If problems arise, consider bundling a Tcl/Tk-aware Python or documenting the known limitations.

**PyPDF2 deprecation**
PyPDF2 is in maintenance mode. `pypdf` is the maintained fork. For v1, PyPDF2 is fine since it is already confirmed working in study examples. In a future phase, consider migrating to `pypdf`.

**Requirements.txt versioning**
Lock package versions as tightly as practical. `pdfplumber>=0.10.0` is fine but test the install against the exact version available at launch time.

**`study-examples/` deletion timing**
Phase 1 spec says the folder can be deleted after Phase 1 is confirmed. Do not delete it before confirming the startup scripts work end-to-end, as the scripts may be needed for reference during early Phase 2 work.

**Chapter number comma formatting**
The title rule says to preserve the exact number as written. If the source writes `1000` without a comma and the spec example shows `1,000`, the rule should not add commas automatically. Preserve exactly as written unless the source is clearly inconsistent within the same document.

---

## Additional Review Notes (revision 2026-05-24)

These are gaps and improvement areas identified in review that the original spec did not cover. They are flagged for the user's decision, not auto-implemented.

> **✅ DECISIONS RESOLVED 2026-06-21 (Phase 1):**
> - **requirements.txt location** → `scripts/requirements.txt` (matches AI-WORKSPACE + on-disk launchers).
> - **venv naming** → `.venv/` (launchers use it; gitignored).
> - **verify gate** → added as `scripts/verify.py` (pytest + pin-check + CHANGELOG-bump).
> - **CHANGELOG.md** → maintained in `md-instructions/`, updated per phase.
> - **`==` pinning** → all deps exact-pinned to versions resolved at first install.
> - **EDITED_ collisions** → numeric suffix (`EDITED_<name>_2.pdf`); paired JSONL log uses the same suffix.
> - **Empty/zero-text extraction** → skip + log clear reason + continue; never write a garbage PDF (`MIN_CHARS=100`).
> - **Output/debug encoding** → UTF-8.
> - **Worker-thread exceptions** → caught per-file, logged via `self.after(0, …)`, batch continues.
> - **NEW: ad/URL/fingerprint junk-strip** → `scripts/rules/junk_strip.py`, Stage 1.5, Tier 1 ON / Tier 2 built-but-off, every removal logged to JSONL. (Finalized in Phase 4 against real samples.)
> Each item's original note is retained below for context.

**`requirements.txt` location vs. AI-WORKSPACE convention.** This spec places `requirements.txt` at the repo root and the startup scripts install from there. The global AI-WORKSPACE convention is to keep it inside `scripts/`. These conflict. The startup scripts and any `verify` step must agree on one location — confirm which to use, then make the `.ps1`/`.sh` path match. (Project-level spec normally wins over the global default; just be deliberate, not accidental.)

**`venv/` vs `.venv/` naming.** The startup scripts create `venv/`, but the AI-WORKSPACE `.gitignore` list ignores `.venv/`. Whichever name is used, make sure `.gitignore` actually ignores it, or the virtual environment will get committed. Add `venv/` to `.gitignore` if that is the chosen name.

**`verify` gate is absent.** The AI-WORKSPACE workflow expects a single `verify` step (run pytest, check all deps pinned, check CHANGELOG bumped) as the definition of "done" for each phase. This spec relies on per-phase manual "Test:" steps only. Consider adding a small `verify` script (or documenting the equivalent manual checks) so each phase has a mechanical gate, not just an eyeball check.

**Dependencies are not exact-pinned.** The spec's `requirements.txt` uses `>=` (e.g. `pdfplumber>=0.10.0`). The AI-WORKSPACE rule is to pin every package to an exact version (`==`) so a later install cannot silently pull a breaking newer release. Pin to the exact versions resolved at first successful install.

**CHANGELOG.md is not in the plan.** The AI-WORKSPACE workflow expects a persistent `CHANGELOG.md` updated every version/phase, alongside `BRIEFING.md`. This spec only mandates `BRIEFING.md` and `EDITING-RULES.md`. Consider adding `CHANGELOG.md` to the instructions folder and updating it per phase.

**Output filename collisions.** `EDITED_<original_name>.pdf` will overwrite a prior run's output if the same file is processed twice into the same folder. Decide intended behavior: silently overwrite, skip, or de-duplicate with a numeric suffix. The JSONL audit log written alongside should follow the same rule so logs and PDFs stay paired.

**Empty / failed extraction handling.** The spec logs low-confidence extraction, but the pipeline behavior on a *zero-text* extraction (e.g. an image-only scanned PDF, which is a stated non-goal) should be explicit: skip the file, log a clear reason, and continue the batch — never write an empty or garbage PDF.

**Encoding of output and debug text.** Confirm output PDFs and the optional `DEBUG_<name>.txt` are written UTF-8, consistent with the novel-index UTF-8 requirement, to avoid mojibake on smart quotes, em dashes, and non-ASCII names.

**Threading/exception propagation.** When a worker thread hits an unexpected exception mid-batch, ensure it is caught, logged to the GUI log via the thread-safe `self.after(0, ...)` path, and the run continues to the next file — the GUI must never silently freeze or die on one bad PDF.
