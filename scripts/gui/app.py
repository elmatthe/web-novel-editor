"""Tkinter main window and all GUI logic.

This is the single-window UI, laid out in **two columns since v0.13.0**: the controls
on the left (a two-mode Input card, three option checkboxes, a progress bar and
Run + Pause/Continue/Stop buttons) and the log on the right, spanning their rows. It used to be one column with the log at the bottom, which
meant the window had to be tall enough for every control *plus* the log — more than a
1080p desktop offers — so the log and the status strip were clipped off the bottom.
The log's content and its condensed one-line-per-file format are unchanged; only where
it sits moved. Pause and stop are honored between files — the current file always
finishes. Phase 02A adds one mixed PDF/TXT queue, selected output formats and explicit
run-folder recovery. Fresh numbered runs default to `Downloads/PDF-Editor-Outputs/`;
a custom output root replaces that root. Imported folder structure is preserved.

Editing is deterministic and script-only: nothing in this window contacts a model or
any network service (Phase 01A removed the optional AI card and every provider control).

The Run button drives the real `core.batch_runner.run_batch`: extract each PDF, run
the editorial pipeline, and rebuild it under its original name. The worker runs on a
daemon thread and posts every UI update back through `self.after(0, ...)`, so the
window never freezes.

Design note: the visual system (palette, spacing, type hierarchy, state feedback) applies
the *principles* of the ui-design-system skill translated into native ttk — no web/CSS
framework. The accent color is the same `#134252` used for PDF chapter headings, tying the
app to its output. The `clam` ttk theme is used because it honors custom widget colors
(the default Windows `vista` theme ignores most of them).
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from tkinter import filedialog, messagebox, ttk

from core.batch_runner import run_batch
from core.input_scanner import scan_folder, scan_upload, natural_order
from core.output_plan import reserve_run_dir, plan_outputs
from core.run_manifest import read_manifest, manifest_path, find_resumable_run
from core.run_lock import StaleLock
from core.novel_registry import DEFAULT_NOVEL, available_novels, clean_novel_name
from utils.file_utils import (
    downloads_dir,
    kebab_case,
    next_numbered_output_dir,
    open_in_file_manager,
)
from utils.pace import compute_rate, format_rate

# ---------------------------------------------------------------------------
# Design tokens (translated from the ui-design-system skill into ttk constants)
# ---------------------------------------------------------------------------
# Colors — an intentional, limited palette anchored on the spec's heading color.
ACCENT = "#134252"          # primary accent (matches PDF chapter-heading color)
ACCENT_HOVER = "#1d5d72"    # accent hover
ACCENT_ACTIVE = "#0d2f3a"   # accent pressed
WINDOW_BG = "#eef1f4"       # app background (light neutral surface)
PANEL_BG = "#ffffff"        # raised panel/card surface
BORDER = "#d3dae0"          # subtle border
TEXT = "#1f2933"            # primary text / headings
TEXT_BODY = "#3e4c59"       # body text
TEXT_MUTED = "#7b8794"      # secondary / muted text
# Semantic colors for log levels (WCAG-AA readable on the white log surface).
COL_SUCCESS = "#1f7a3d"
COL_WARN = "#b45309"
COL_ERROR = "#b91c1c"
COL_INFO = "#3e4c59"
# Semantic colors per log level.
LEVEL_COLORS = {
    "success": COL_SUCCESS,
    "warn": COL_WARN,
    "error": COL_ERROR,
    "info": COL_INFO,
    "muted": TEXT_MUTED,
}

# Spacing — 8pt grid.
PAD_S = 8
PAD_M = 16
PAD_L = 24

# Two columns since v0.13.0: controls on the left, the log on the right.
#
# The log used to be a bottom row, which meant the window had to be tall enough for
# every control *plus* the log — over 1200px — while a 1080p desktop offers roughly
# 990px. `minsize` then overrode the screen-aware opening geometry and the log and the
# status strip were simply clipped off the bottom. Moving the log sideways takes its
# height out of the vertical budget entirely; it now grows horizontally instead, which
# is where the spare room actually was.
#
# Both constants are pinned by tests: the controls' per-row heights must fit inside
# MIN_HEIGHT, MIN_HEIGHT must fit a 1080p desktop, and both columns must fit inside
# MIN_WIDTH.
CONTROL_COLUMN_WIDTH = 780      # the left column's floor, so cards never get crushed
LOG_COLUMN_WIDTH = 400          # the log's floor; everything above it goes to the log
MIN_WIDTH = CONTROL_COLUMN_WIDTH + LOG_COLUMN_WIDTH + PAD_M + 2 * PAD_M
MIN_HEIGHT = 960
# Opening height when the display allows it. The log stretches to fill whatever the
# window has, so there is no longer any reason to open taller than the controls need.
PREFERRED_HEIGHT = 980


def _novel_combo_width(roster: list[str]) -> int:
    """Character width (font-average units) for the novel dropdown.

    Sized from the *actual* roster so the longest label — e.g. "Circle of
    Inevitability — universal rules only" — is never truncated in either the closed
    display or the open list, and so onboarding a longer novel name keeps the
    widget correct without a hand-tuned constant. The +2 leaves room beside the
    dropdown arrow.
    """
    longest = max((len(label) for label in roster), default=0)
    return longest + 2


class WebnovelEditorApp(tk.Tk):
    """The single main application window."""

    def __init__(self) -> None:
        super().__init__()
        # Paired product-family naming with the sibling web-novel-scraper
        # ("Web Novel Scraper"); the two apps read as one family (Phase 7).
        self.title("Web Novel Editor")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        # Open big enough to show every control, but never taller than the screen —
        # a window that opens off the bottom of a small display hides the Start
        # button, which is the one control the user must be able to find.
        usable = max(MIN_HEIGHT, self.winfo_screenheight() - 90)
        self.geometry(f"{MIN_WIDTH}x{min(PREFERRED_HEIGHT, usable)}")
        self.configure(bg=WINDOW_BG)

        # State
        self.file_paths: list[str] = []       # upload mode: user-ordered flat list
        self.folder_files: list[Path] = []    # folder mode: resolved natural-order scan
        self.input_folder = ""                # folder mode: the selected root folder
        self.import_roots: dict[str, str] = {}
        self._exit_when_done = False
        self._running = False
        # Cooperative pause gate shared with run_batch: SET = run, cleared = pause
        # requested. Consulted between files only, so the current file always finishes.
        # Session-only state — a fresh batch (and app start) always begins un-paused.
        self.pause_gate = threading.Event()
        self.pause_gate.set()
        self.stop_event = threading.Event()
        # Batch pace, for the running-average / ETA readout. None = not tracking.
        self._batch_started: float | None = None
        self._batch_total = 0
        self._init_fonts()
        self._configure_styles()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- styling ----------------------------------------------------------------
    def _init_fonts(self) -> None:
        import tkinter.font as tkfont

        available = {f.lower() for f in tkfont.families(self)}

        def pick(prefs: list[str]) -> str:
            for fam in prefs:
                if fam.lower() in available:
                    return fam
            return prefs[-1]

        sans = pick(["Segoe UI", "Helvetica Neue", "Helvetica", "Arial"])
        mono = pick(["Consolas", "DejaVu Sans Mono", "Menlo", "Courier New"])
        # Type hierarchy (skill principle: distinct, scaled type roles).
        self.font_title = (sans, 16, "bold")
        self.font_subtitle = (sans, 10)
        self.font_section = (sans, 10, "bold")
        self.font_body = (sans, 10)
        self.font_button = (sans, 10, "bold")
        self.font_log = (mono, 9)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        # 'clam' honors custom colors; the native vista theme ignores most of them.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=WINDOW_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("Header.TFrame", background=WINDOW_BG)

        style.configure("TLabel", background=WINDOW_BG, foreground=TEXT_BODY,
                        font=self.font_body)
        style.configure("Title.TLabel", background=WINDOW_BG, foreground=TEXT,
                        font=self.font_title)
        style.configure("Subtitle.TLabel", background=WINDOW_BG, foreground=TEXT_MUTED,
                        font=self.font_subtitle)
        style.configure("Panel.TLabel", background=PANEL_BG, foreground=TEXT_BODY,
                        font=self.font_body)
        style.configure("PathValue.TLabel", background=PANEL_BG, foreground=TEXT_MUTED,
                        font=self.font_body)
        style.configure("Status.TLabel", background=WINDOW_BG, foreground=TEXT_MUTED,
                        font=self.font_subtitle)

        # LabelFrame as a titled "card".
        style.configure("Card.TLabelframe", background=PANEL_BG, bordercolor=BORDER,
                        relief="solid", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=WINDOW_BG, foreground=ACCENT,
                        font=self.font_section)

        # Buttons — secondary (neutral) and primary (accent) with state feedback.
        style.configure("TButton", font=self.font_body, padding=(PAD_M, PAD_S),
                        background="#e3e8ec", foreground=TEXT, bordercolor=BORDER,
                        focuscolor=ACCENT)
        style.map("TButton",
                  background=[("active", "#d3dae0"), ("disabled", "#eef1f4")],
                  foreground=[("disabled", TEXT_MUTED)])

        style.configure("Accent.TButton", font=self.font_button, padding=(PAD_L, PAD_S + 2),
                        background=ACCENT, foreground="#ffffff", bordercolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("active", ACCENT_HOVER), ("pressed", ACCENT_ACTIVE),
                              ("disabled", "#9bb0b8")],
                  foreground=[("disabled", "#eef1f4")])

        style.configure("TCheckbutton", background=PANEL_BG, foreground=TEXT_BODY,
                        font=self.font_body, focuscolor=ACCENT)
        style.map("TCheckbutton", background=[("active", PANEL_BG)])

        style.configure("TRadiobutton", background=PANEL_BG, foreground=TEXT_BODY,
                        font=self.font_body, focuscolor=ACCENT)
        style.map("TRadiobutton", background=[("active", PANEL_BG)])

        style.configure("Accent.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor="#dbe2e7", bordercolor=BORDER, lightcolor=ACCENT,
                        darkcolor=ACCENT)

    # -- layout -----------------------------------------------------------------
    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="TFrame", padding=PAD_M)
        root.pack(fill="both", expand=True)
        # Column 0 holds the controls at their natural size and never flexes, so no
        # card can be squeezed however the window is resized. Column 1 is the log, and
        # it takes every pixel of horizontal slack. Row 5 is an empty spacer that takes
        # the vertical slack on the left, which lets the log stretch through its
        # rowspan without stretching any control.
        root.columnconfigure(0, weight=0, minsize=CONTROL_COLUMN_WIDTH)
        root.columnconfigure(1, weight=1, minsize=LOG_COLUMN_WIDTH)
        root.rowconfigure(5, weight=1)

        self._build_header(root, row=0)
        self._build_novel_panel(root, row=1)
        self._build_file_panel(root, row=2)
        self._build_options_panel(root, row=3)
        self._build_run_row(root, row=4)
        self._build_log_panel(root, row=1, column=1, rowspan=5)
        self._build_status_bar(root, row=6)

        self._refresh_status()
        self._log("Ready. Upload PDFs or select a folder, then start the batch — "
                  "results are saved to a new folder in your Downloads.", "muted")

    def _build_header(self, parent: ttk.Frame, row: int) -> None:
        header = ttk.Frame(parent, style="Header.TFrame")
        header.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, PAD_M))
        ttk.Label(header, text="Web Novel Editor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Batch-clean webscraped chapter PDFs into TTS-ready documents.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

    def _build_novel_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="Novel", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Editing profile:", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, PAD_S))

        # Roster: "Universal" first (the default), then one entry per index file under
        # scripts/resources/novel-index/, profile-less novels marked "no
        # profile yet". Display strings may carry that marker, so every selection is
        # passed through clean_novel_name before it reaches run_batch's novel_name ->
        # pipeline dispatch or the output-folder naming.
        roster = available_novels()
        default = DEFAULT_NOVEL if DEFAULT_NOVEL in roster else (roster[0] if roster else "")
        self.novel_var = tk.StringVar(value=default)
        # Width is measured from the real roster so the longest label shows in full
        # in both the closed display and the open dropdown list. The list itself is a
        # native override-redirect popup that draws in front of the card content, so
        # it correctly covers (never collides behind) the description below — no
        # z-order handling is needed once the width is right.
        self.novel_combo = ttk.Combobox(
            frame, textvariable=self.novel_var, values=roster, state="readonly",
            font=self.font_body, width=_novel_combo_width(roster),
        )
        self.novel_combo.grid(row=0, column=1, sticky="w")
        self.novel_combo.bind("<<ComboboxSelected>>", self._on_novel_changed)

        ttk.Label(
            frame,
            text="Universal applies the standard cleanup to any novel. Choosing a novel "
                 "layers its own specific edits on top. “Names protected” means the "
                 "novel has no extra edits of its own yet, but its names and places are "
                 "still kept exactly as written; “universal rules only” means it has "
                 "neither yet.",
            style="PathValue.TLabel", wraplength=720, justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(PAD_S, 0))

    def _on_novel_changed(self, _event=None) -> None:
        self._log(f"Novel selected: {self.novel_var.get()}", "info")
        self._refresh_status()

    def _build_file_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="Input", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        frame.columnconfigure(0, weight=1)

        # Two mutually exclusive input modes (Plan 1 Phase 1). The radio pair flips
        # which mode's controls are enabled; the shared list below always shows the
        # resolved processing order for the active mode.
        self.input_mode_var = tk.StringVar(value="upload")
        modes = ttk.Frame(frame, style="Panel.TFrame")
        modes.grid(row=0, column=0, sticky="w", pady=(0, PAD_S))
        ttk.Radiobutton(
            modes, text="PDF / TXT files", value="upload", variable=self.input_mode_var,
            command=self._on_input_mode_changed,
        ).pack(side="left")
        ttk.Radiobutton(
            modes, text="Select Folder", value="folder", variable=self.input_mode_var,
            command=self._on_input_mode_changed,
        ).pack(side="left", padx=(PAD_M, 0))
        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(modes, text="Include subfolders", variable=self.recursive_var).pack(side="left", padx=(PAD_M, 0))

        list_wrap = ttk.Frame(frame, style="Panel.TFrame")
        list_wrap.grid(row=1, column=0, sticky="ew")
        list_wrap.columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_wrap, selectmode=tk.EXTENDED, height=4, activestyle="none", exportselection=False,
            bg=PANEL_BG, fg=TEXT_BODY, font=self.font_body, relief="solid",
            borderwidth=1, highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT, selectbackground=ACCENT, selectforeground="#ffffff",
        )
        self.file_listbox.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(list_wrap, orient="vertical",
                               command=self.file_listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.file_listbox.configure(yscrollcommand=scroll.set)

        btns = ttk.Frame(frame, style="Panel.TFrame")
        btns.grid(row=2, column=0, sticky="ew", pady=(PAD_M, 0))
        btns.columnconfigure(3, weight=1)
        self.add_button = ttk.Button(btns, text="Add Files", command=self._add_pdfs)
        self.add_button.grid(row=0, column=0)
        self.remove_button = ttk.Button(btns, text="Remove Selected",
                                        command=self._remove_selected)
        self.remove_button.grid(row=0, column=1, padx=(PAD_S, 0))
        self.clear_button = ttk.Button(btns, text="Clear All", command=self._clear_all)
        self.clear_button.grid(row=0, column=2, padx=(PAD_S, 0))
        self.up_button = ttk.Button(btns, text="Move Up", command=lambda: self._move_selected(-1))
        self.up_button.grid(row=0, column=3, padx=(PAD_S // 2, 0))
        self.down_button = ttk.Button(btns, text="Move Down", command=lambda: self._move_selected(1))
        self.down_button.grid(row=0, column=4, padx=(PAD_S // 2, 0))

        self.choose_folder_button = ttk.Button(btns, text="Choose Folder…",
                                               command=self._choose_input_folder)
        self.choose_folder_button.grid(row=0, column=5, sticky="e", padx=(PAD_S // 2, 0))

        self.folder_var = tk.StringVar(value="No folder selected")
        ttk.Label(frame, textvariable=self.folder_var, style="PathValue.TLabel",
                  anchor="w").grid(row=3, column=0, sticky="ew", pady=(PAD_S, 0))

        self._on_input_mode_changed(log=False)

    def _build_options_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="Advanced Options", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))

        self.opt_replacement_log = tk.BooleanVar(value=False)
        self.opt_debug_text = tk.BooleanVar(value=False)
        self.opt_dry_run = tk.BooleanVar(value=False)
        self.opt_pdf = tk.BooleanVar(value=True)
        self.opt_txt = tk.BooleanVar(value=False)

        # Two columns rather than three stacked rows: the same three options, one row
        # of height cheaper. Every pixel here is one the Start button was being pushed
        # down by.
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            frame, text="Write replacement log (JSONL beside outputs)",
            variable=self.opt_replacement_log,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            frame, text="Dry run (full text pipeline, no output files)",
            variable=self.opt_dry_run,
        ).grid(row=0, column=1, sticky="w", padx=(PAD_M, 0))
        ttk.Checkbutton(
            frame, text="Save intermediate cleaned text (DEBUG_<name>.txt)",
            variable=self.opt_debug_text,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(PAD_S, 0))
        formats = ttk.Frame(frame, style="Panel.TFrame")
        formats.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(PAD_S, 0))
        ttk.Checkbutton(formats, text="PDF output", variable=self.opt_pdf).pack(side="left")
        ttk.Checkbutton(formats, text="TXT output", variable=self.opt_txt).pack(side="left", padx=(PAD_M, 0))
        ttk.Button(formats, text="Output root…", command=self._choose_output_root).pack(side="right")
        self.output_root_var = tk.StringVar(value="")

    def _build_log_panel(self, parent: ttk.Frame, row: int, *, column: int = 0,
                         rowspan: int = 1) -> None:
        """The log, as the right-hand column (v0.13.0).

        It keeps the condensed one-line-per-file format exactly as Plan 1 Phase 4 set
        it — this is a layout change only, and nothing about what gets written here or
        how verbose it is has moved. What changed is that the log no longer competes
        with the controls for vertical space: it spans their rows and takes the
        horizontal slack, so it can show more lines than it ever could at the bottom.
        """
        frame = ttk.Labelframe(parent, text="Log", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=column, rowspan=rowspan, sticky="nsew",
                   padx=(PAD_M, 0), pady=(0, PAD_M))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            frame, wrap="word", state=tk.DISABLED, height=10, width=44, bg=PANEL_BG,
            fg=COL_INFO, font=self.font_log, relief="solid", borderwidth=1,
            highlightthickness=1, highlightbackground=BORDER, padx=PAD_S, pady=PAD_S,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(frame, orient="vertical",
                                   command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # Semantic color tags for log levels.
        self.log_text.tag_configure("info", foreground=COL_INFO)
        self.log_text.tag_configure("muted", foreground=TEXT_MUTED)
        self.log_text.tag_configure("accent", foreground=ACCENT, font=self.font_log)
        self.log_text.tag_configure("success", foreground=COL_SUCCESS)
        self.log_text.tag_configure("warn", foreground=COL_WARN)
        self.log_text.tag_configure("error", foreground=COL_ERROR)

    def _build_run_row(self, parent: ttk.Frame, row: int) -> None:
        bar = ttk.Frame(parent, style="TFrame")
        bar.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        bar.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(bar, mode="determinate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, PAD_M))
        # Pause ⇄ Continue: enabled only while a batch runs. Pausing holds the worker
        # between files (the current file always finishes — see run_batch's pause_gate).
        self.pause_button = ttk.Button(bar, text="Pause", command=self._toggle_pause,
                                       state=tk.DISABLED)
        self.pause_button.grid(row=0, column=1, sticky="e", padx=(0, PAD_S))
        self.stop_button = ttk.Button(
            bar, text="Stop", command=self._request_stop, state=tk.DISABLED
        )
        self.stop_button.grid(row=0, column=2, sticky="e", padx=(0, PAD_S))
        self.run_button = ttk.Button(bar, text="Start Batch Processing",
                                     style="Accent.TButton", command=self._start_batch)
        self.run_button.grid(row=0, column=3, sticky="e")

        # Observed pace of the running batch (Plan 2a Phase 7): a plain running
        # average over the chapters finished so far, and what it implies for the
        # rest. Blank until the first chapter completes — an ETA from zero
        # samples would be a guess dressed up as information.
        self.rate_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.rate_var, style="Subtitle.TLabel",
                  anchor="w").grid(row=1, column=0, columnspan=4, sticky="ew",
                                   pady=(PAD_S // 2, 0))
        recovery = ttk.Frame(bar)
        recovery.grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Button(recovery, text="Resume Run…", command=self._resume_run).pack(side="left")
        ttk.Button(recovery, text="Retry Failed…", command=lambda: self._resume_run(retry_failed=True)).pack(side="left", padx=(PAD_S, 0))
        ttk.Button(recovery, text="Find Recent Run", command=self._resume_recent).pack(side="left", padx=(PAD_S, 0))

    def _build_status_bar(self, parent: ttk.Frame, row: int) -> None:
        self.status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").grid(row=row, column=0, columnspan=2, sticky="ew")

    # -- input mode -------------------------------------------------------------
    def _on_input_mode_changed(self, log: bool = True) -> None:
        """Flip which mode's controls are live and re-show that mode's file order."""
        folder_mode = self.input_mode_var.get() == "folder"
        upload_state = tk.DISABLED if folder_mode else tk.NORMAL
        folder_state = tk.NORMAL if folder_mode else tk.DISABLED
        self.add_button.configure(state=upload_state)
        self.choose_folder_button.configure(state=folder_state)

        self._refresh_file_list()
        if log:
            mode_label = "Select Folder" if folder_mode else "Upload PDFs"
            self._log(f"Input mode: {mode_label}", "info")
        self._refresh_status()

    def _choose_input_folder(self) -> None:
        directory = filedialog.askdirectory(title="Add a folder of PDF/TXT files to the queue")
        if directory:
            self._apply_input_folder(directory)

    def _apply_input_folder(self, directory: str) -> None:
        """Scan ``directory`` (recursive, natural order) and display the result."""
        try:
            self.folder_files = scan_folder(directory, recursive=self.recursive_var.get(),
                                            exclude=self._batch_output_dir if self._running else self._output_root(),
                                            warn=lambda m: self._log(m, "warn"))
        except (ValueError, NotADirectoryError, OSError) as exc:
            self._log(f"Could not scan folder: {exc}", "error")
            return
        self.input_folder = directory
        existing = {os.path.normcase(str(Path(p).resolve())) for p in self.file_paths}
        for path in self.folder_files:
            key = os.path.normcase(str(path.resolve()))
            if key not in existing:
                self.file_paths.append(str(path))
                self.import_roots[str(path)] = directory
                existing.add(key)
        self.folder_var.set(directory)
        self._refresh_file_list()
        self._log(
            f"Scanned folder: {directory} — {len(self.folder_files)} PDF/TXT file(s) in "
            "processing order.", "info")
        if not self.folder_files:
            self._log("No PDF/TXT files found in that folder.", "warn")
        self._refresh_status()

    def _refresh_file_list(self) -> None:
        """Refresh the shared queue while retaining surviving selections and focus."""
        previous = getattr(self, "_display_paths", ())
        selected = {previous[i] for i in self.file_listbox.curselection() if i < len(previous)}
        active = self.file_listbox.index(tk.ACTIVE)
        focused = previous[active] if active < len(previous) else None
        self.file_listbox.delete(0, tk.END)
        for index, path in enumerate(self.file_paths):
            imported = self.import_roots.get(path)
            label = Path(path).relative_to(Path(imported).parent).as_posix() if imported else Path(path).name
            self.file_listbox.insert(tk.END, label)
            if path in selected:
                self.file_listbox.selection_set(index)
            if path == focused:
                self.file_listbox.activate(index)
        self._display_paths = tuple(self.file_paths)

    # -- file list actions ------------------------------------------------------
    def _add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select PDF/TXT files", filetypes=[("PDF / TXT files", "*.pdf *.txt")])
        try:
            paths = natural_order(scan_upload(paths))
        except (OSError, ValueError) as exc:
            self._log(f"Could not add files: {exc}", "error")
            return
        added = 0
        existing = {os.path.normcase(str(Path(p).resolve())) for p in self.file_paths}
        for path in paths:
            key = os.path.normcase(str(path.resolve()))
            if key not in existing:
                self.file_paths.append(str(path))
                existing.add(key)
                added += 1
        self._refresh_file_list()
        if added:
            self._log(f"Added {added} file(s).", "info")
        self._refresh_status()

    def _remove_selected(self) -> None:
        selection = list(self.file_listbox.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self.import_roots.pop(self.file_paths.pop(index), None)
        self._refresh_file_list()
        self._log(f"Removed {len(selection)} file(s).", "info")
        self._refresh_status()

    def _clear_all(self) -> None:
        if not self.file_paths:
            return
        count = len(self.file_paths)
        self.file_paths.clear()
        self.import_roots.clear()
        self._refresh_file_list()
        self._log(f"Cleared {count} file(s).", "info")
        self._refresh_status()

    # -- run / worker -----------------------------------------------------------
    def _move_selected(self, direction):
        selected = set(self.file_listbox.curselection())
        active = self.file_listbox.index(tk.ACTIVE)
        for index in sorted(selected, reverse=direction > 0):
            other = index + direction
            if 0 <= other < len(self.file_paths) and other not in selected:
                self.file_paths[index], self.file_paths[other] = self.file_paths[other], self.file_paths[index]
                selected.remove(index)
                selected.add(other)
                if active == index:
                    active = other
                elif active == other:
                    active = index
        self._refresh_file_list()
        for index in sorted(selected):
            self.file_listbox.selection_set(index)
        self.file_listbox.activate(active)
        if selected:
            self.file_listbox.see(active)

    def _output_root(self):
        value = self.output_root_var.get()
        return Path(value) if value else downloads_dir() / "PDF-Editor-Outputs"

    def _choose_output_root(self):
        directory = filedialog.askdirectory(title="Choose output root (numbered runs go directly inside)")
        if directory:
            self.output_root_var.set(directory)
            self._log(f"Output root: {directory}", "info")
            self._refresh_status()

    def _resume_recent(self):
        if self._running:
            return
        offer = find_resumable_run(self._output_root())
        if offer.available:
            self._resume_run(directory=offer.output_dir)
        else:
            messagebox.showinfo("Resume Run", offer.reason)

    def _resume_run(self, *, retry_failed=False, directory=None, recover=False):
        if self._running:
            return
        directory = directory or filedialog.askdirectory(title="Select the original run folder")
        if not directory:
            return
        try:
            saved = read_manifest(manifest_path(directory))
        except Exception as exc:
            messagebox.showerror("Resume refused", str(exc))
            return
        self._begin(files=saved["queue"], output_dir=saved["output_dir"],
                    mirror_root=None, novel=saved["run"]["novel"], saved=saved,
                    retry_failed=retry_failed, recover=recover)

    def _start_batch(self) -> None:
        if self._running:
            return
        files = list(self.file_paths)
        mirror_root = None
        if not files:
            messagebox.showwarning("No files", "Add PDF/TXT files or a folder before running.")
            return
        if not self.opt_pdf.get() and not self.opt_txt.get():
            messagebox.showwarning("No output format", "Select PDF, TXT, or both before starting.")
            return

        # Map the display selection to its clean novel name BEFORE it reaches dispatch
        # or folder naming: the roster markers are display-only ("Universal" passes
        # through and kebab-cases to universal-x).
        novel = clean_novel_name(self.novel_var.get())

        # Forced output location: a fresh auto-numbered Downloads\<novel>-x folder,
        # named for the current selection. Only named here — run_batch creates it
        # when the batch actually starts (and not at all on a dry run).
        name = kebab_case(novel) or "output"
        try:
            proposed = next_numbered_output_dir(self._output_root(), name)
            plan_outputs(files, proposed, formats=tuple(fmt for fmt, enabled in (
                ("pdf", self.opt_pdf.get()), ("txt", self.opt_txt.get())) if enabled),
                import_roots=self.import_roots, debug=self.opt_debug_text.get(), audit=self.opt_replacement_log.get())
            output_dir = str(proposed if self.opt_dry_run.get()
                             else reserve_run_dir(self._output_root(), name))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Output allocation failed", str(exc))
            return
        return self._begin(
            files=files, output_dir=output_dir, mirror_root=mirror_root, novel=novel)

    def _begin(self, *, files, output_dir, mirror_root, novel, saved=None, retry_failed=False, recover=False) -> None:
        """Commit to one batch and start the worker."""
        # Per-batch snapshot state: the worker thread reads only these plain
        # attributes, never Tk variables (Tk objects are not thread-safe).
        self._batch_files = tuple(files)
        self._batch_output_dir = output_dir
        self._batch_mirror_root = mirror_root
        self._batch_novel = novel
        self._batch_replacement_log = self.opt_replacement_log.get()
        self._batch_debug_text = self.opt_debug_text.get()
        self._batch_dry_run = self.opt_dry_run.get()
        self._batch_formats = tuple(fmt for fmt, enabled in (("pdf", self.opt_pdf.get()), ("txt", self.opt_txt.get())) if enabled)
        self._batch_roots = dict(self.import_roots)
        self._batch_resume = saved is not None
        self._batch_retry = retry_failed
        self._batch_recover = recover
        if saved:
            options = saved["run"]["options"]
            self._batch_formats = tuple(options["formats"])
            self._batch_replacement_log = options["write_replacement_log"]
            self._batch_debug_text = options["write_debug_text"]
            self._batch_dry_run = False

        self._running = True
        self.run_button.configure(state=tk.DISABLED)
        self.pause_gate.set()  # a new batch always starts un-paused
        self.stop_event.clear()
        self.pause_button.configure(state=tk.NORMAL, text="Pause")
        self.stop_button.configure(state=tk.NORMAL)
        self.progress.configure(maximum=len(files), value=0)
        self._begin_rate_tracking(len(files))
        dry = self._batch_dry_run
        self._log(
            "--- Starting batch ---" + (" (dry run, no PDF output)" if dry else ""),
            "accent",
        )

        thread = threading.Thread(target=self._process_worker, daemon=True)
        thread.start()

    def _process_worker(self) -> None:
        """Runs on a daemon thread. All UI updates go through self.after(0, ...)."""
        try:
            summary = run_batch(
                self._batch_files,
                self._batch_output_dir,
                write_replacement_log=self._batch_replacement_log,
                write_debug_text=self._batch_debug_text,
                dry_run=self._batch_dry_run,
                novel_name=self._batch_novel,  # the clean (marker-stripped) selection
                mirror_root=self._batch_mirror_root,
                output_formats=self._batch_formats,
                import_roots=self._batch_roots,
                resume=self._batch_resume,
                retry_failed=self._batch_retry,
                recover_stale=self._batch_recover,
                pause_gate=self.pause_gate,
                stop_event=self.stop_event,
                gui_log=lambda message, level="info": self.after(
                    0, self._log, message, level),
                progress=lambda value: self.after(0, self._set_progress, value),
            )
        except StaleLock:
            self.after(0, self._confirm_stale_recovery)
            return
        except Exception as exc:  # defensive: keep the UI responsive on any crash
            self.after(0, self._on_error, exc)
            return
        self.after(0, self._on_done, summary)

    def _confirm_stale_recovery(self):
        self._running = False
        self.run_button.configure(state=tk.NORMAL)
        self._reset_pause_control()
        self._reset_stop_control()
        self._end_rate_tracking()
        if self._exit_when_done:
            self.destroy()
            return
        if messagebox.askyesno("Recover stale run?", "The former owner is proven exited or its process identity differs. Preserve its ownership record and recover this run?"):
            self._resume_run(directory=self._batch_output_dir, retry_failed=self._batch_retry, recover=True)

    def _on_close(self):
        if not self._running:
            self.destroy()
        elif messagebox.askyesno("Stop and exit?", "Finish the current file safely, save the checkpoint, then exit?"):
            self._exit_when_done = True
            self._request_stop()

    def _toggle_pause(self) -> None:
        """Pause ⇄ Continue. Pausing clears the gate; the worker holds between files
        (the current file always finishes first), so this can never corrupt an output."""
        if not self._running:
            return
        if self.pause_gate.is_set():
            self.pause_gate.clear()
            self.pause_button.configure(text="Continue")
            self._log("Pause requested — the current file will finish first.", "warn")
        else:
            self.pause_gate.set()
            self.pause_button.configure(text="Pause")

    def _reset_pause_control(self) -> None:
        """Back to idle: gate open, button disabled and relabelled for the next batch."""
        self.pause_gate.set()
        self.pause_button.configure(state=tk.DISABLED, text="Pause")

    def _request_stop(self) -> None:
        """Request a clean stop after the currently in-flight file."""
        if not self._running:
            return
        self.stop_event.set()
        # Release a between-files pause so the worker can observe the stop request.
        self.pause_gate.set()
        self.pause_button.configure(text="Pause")
        self.stop_button.configure(state=tk.DISABLED)
        self._log("Stop requested — the current file will finish first.", "warn")

    def _reset_stop_control(self) -> None:
        self.stop_event.clear()
        self.stop_button.configure(state=tk.DISABLED)

    def _on_done(self, summary: dict) -> None:
        self._running = False
        if self._exit_when_done:
            self.destroy()
            return
        self.run_button.configure(state=tk.NORMAL)
        self._reset_pause_control()
        self._reset_stop_control()
        self._end_rate_tracking()
        skipped = summary.get("skipped", 0)

        # Auto-open the output folder so the user lands on their results (spec GUI
        # requirement). Only when real files were written; log if it could not open.
        if summary.get("outputs"):
            if open_in_file_manager(summary["output_dir"]):
                self._log(f"Opened output folder: {summary['output_dir']}", "muted")
            else:
                self._log(
                    f"Could not open the output folder automatically. "
                    f"It is here: {summary['output_dir']}", "warn")

        if summary.get("stopped"):
            title = "Batch stopped"
        elif summary.get("finished_with_errors"):
            title = "Finished with errors"
        elif summary.get("run_complete") is False:
            title = "Run incomplete"
        else:
            title = "Batch complete"
        messagebox.showinfo(
            title,
            f"Processed {summary['total']} file(s).\n"
            f"Completed: {summary.get('completed_total', summary['succeeded'])}   "
            f"Failed: {summary.get('failed_total', summary['failed'])}   Skipped: {summary.get('skipped_total', skipped)}\n"
            f"Output folder: {summary['output_dir']}",
        )

    def _on_error(self, exc: Exception) -> None:
        self._running = False
        if self._exit_when_done:
            self._log(f"Stopped with error: {type(exc).__name__}: {exc}", "error")
            messagebox.showerror("Stopped with error", str(exc))
            self.destroy()
            return
        self.run_button.configure(state=tk.NORMAL)
        self._reset_pause_control()
        self._reset_stop_control()
        self._end_rate_tracking()
        self._log(f"Batch aborted: {type(exc).__name__}: {exc}", "error")
        messagebox.showerror("Batch error", f"{type(exc).__name__}: {exc}")

    # -- helpers ----------------------------------------------------------------
    def _begin_rate_tracking(self, total: int) -> None:
        """Start (or restart) the pace clock, clearing any previous run's readout."""
        self._batch_total = max(0, int(total))
        self._batch_started = time.monotonic()
        self.rate_var.set("")

    def _end_rate_tracking(self) -> None:
        self._batch_started = None

    def _update_rate(self, completed: int) -> None:
        started = self._batch_started
        if started is None or not self._batch_total:
            return
        rate = compute_rate(
            completed, self._batch_total, time.monotonic() - started)
        self.rate_var.set(format_rate(rate))

    def _set_progress(self, value: int) -> None:
        self.progress.configure(value=value)
        self._update_rate(value)

    def _thread_log(self, message: str, level: str = "info") -> None:
        """Log from a worker thread. Tk objects are not thread-safe, so every
        message is marshalled back onto the UI thread exactly as run_batch's own
        gui_log callback already does."""
        self.after(0, self._log, message, level)

    def _log(self, message: str, level: str = "info") -> None:
        # The single GUI log sink: everything shown in the panel goes through here.
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", level)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _refresh_status(self) -> None:
        if not hasattr(self, "status_var"):
            return  # called during panel construction, before the status bar exists
        novel = getattr(self, "novel_var", None)
        # Status shows the clean name; the output label kebabs the clean name too, so a
        # marked selection never leaks "-no-profile-yet" into the folder preview.
        novel_label = clean_novel_name(novel.get()) if novel is not None else "—"
        out_label = f"{self._output_root().name}/{kebab_case(novel_label) or 'output'}-N"
        mode_label = "mixed queue"
        queued = len(self.file_paths)
        self.status_var.set(
            f"novel: {novel_label}   |   input: {mode_label}   |   "
            f"{queued} file(s) queued   |   output: {out_label}")


def launch() -> None:
    """Create and run the main application window."""
    app = WebnovelEditorApp()
    app.mainloop()
