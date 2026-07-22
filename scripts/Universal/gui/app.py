"""Tkinter main window and all GUI logic.

This is the single-window UI: a two-mode Input card (Upload PDFs / Select Folder),
three option checkboxes, a log widget, a progress bar, and Run + Pause/Continue
buttons (pause holds the batch between files — the current file always finishes). The output
location is not user-chosen (v0.11.0): every batch writes into a fresh auto-numbered
`Downloads\\<novel>-x` folder — flat in upload mode, mirroring the selected folder's
structure in folder mode — with original filenames kept.

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
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.batch_runner import run_batch
from core.input_scanner import scan_folder
from core.novel_registry import DEFAULT_NOVEL, available_novels, clean_novel_name
from utils.file_utils import (
    downloads_dir,
    kebab_case,
    next_numbered_output_dir,
    open_in_file_manager,
)

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

# Spacing — 8pt grid.
PAD_S = 8
PAD_M = 16
PAD_L = 24

MIN_WIDTH = 820
MIN_HEIGHT = 700


class WebnovelEditorApp(tk.Tk):
    """The single main application window."""

    def __init__(self) -> None:
        super().__init__()
        # Paired product-family naming with the sibling web-novel-scraper
        # ("Web Novel Scraper"); the two apps read as one family (Phase 7).
        self.title("Web Novel Editor")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.geometry(f"{MIN_WIDTH}x{MIN_HEIGHT}")
        self.configure(bg=WINDOW_BG)

        # State
        self.file_paths: list[str] = []       # upload mode: user-ordered flat list
        self.folder_files: list[Path] = []    # folder mode: resolved natural-order scan
        self.input_folder = ""                # folder mode: the selected root folder
        self._running = False
        # Cooperative pause gate shared with run_batch: SET = run, cleared = pause
        # requested. Consulted between files only, so the current file always finishes.
        # Session-only state — a fresh batch (and app start) always begins un-paused.
        self.pause_gate = threading.Event()
        self.pause_gate.set()

        self._init_fonts()
        self._configure_styles()
        self._build_ui()

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
        root.columnconfigure(0, weight=1)
        # The log row expands; everything else is fixed height. The log sits at the
        # bottom (above only the thin status strip), with the run controls above it —
        # mirroring the sibling web-novel-scraper's layout (Phase 7). No output-folder
        # card since v0.11.0: output goes to an auto-numbered Downloads folder.
        root.rowconfigure(5, weight=1)

        self._build_header(root, row=0)
        self._build_novel_panel(root, row=1)
        self._build_file_panel(root, row=2)
        self._build_options_panel(root, row=3)
        self._build_run_row(root, row=4)
        self._build_log_panel(root, row=5)
        self._build_status_bar(root, row=6)

        self._refresh_status()
        self._log("Ready. Upload PDFs or select a folder, then start the batch — "
                  "results are saved to a new folder in your Downloads.", "muted")

    def _build_header(self, parent: ttk.Frame, row: int) -> None:
        header = ttk.Frame(parent, style="Header.TFrame")
        header.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
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
        # scripts/Universal/resources/novel-index/, profile-less novels marked "no
        # profile yet". Display strings may carry that marker, so every selection is
        # passed through clean_novel_name before it reaches run_batch's novel_name ->
        # pipeline dispatch or the output-folder naming.
        roster = available_novels()
        default = DEFAULT_NOVEL if DEFAULT_NOVEL in roster else (roster[0] if roster else "")
        self.novel_var = tk.StringVar(value=default)
        self.novel_combo = ttk.Combobox(
            frame, textvariable=self.novel_var, values=roster, state="readonly",
            font=self.font_body,
        )
        self.novel_combo.grid(row=0, column=1, sticky="w")
        self.novel_combo.bind("<<ComboboxSelected>>", self._on_novel_changed)

        ttk.Label(
            frame,
            text="Universal applies the standard cleanup to any novel. Choosing a novel "
                 "layers its specific edits on top; novels marked “no profile yet” "
                 "run the same universal cleanup until a profile is added.",
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
            modes, text="Upload PDFs", value="upload", variable=self.input_mode_var,
            command=self._on_input_mode_changed,
        ).pack(side="left")
        ttk.Radiobutton(
            modes, text="Select Folder", value="folder", variable=self.input_mode_var,
            command=self._on_input_mode_changed,
        ).pack(side="left", padx=(PAD_M, 0))

        list_wrap = ttk.Frame(frame, style="Panel.TFrame")
        list_wrap.grid(row=1, column=0, sticky="ew")
        list_wrap.columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_wrap, selectmode=tk.EXTENDED, height=6, activestyle="none",
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
        self.add_button = ttk.Button(btns, text="Add PDFs", command=self._add_pdfs)
        self.add_button.grid(row=0, column=0)
        self.remove_button = ttk.Button(btns, text="Remove Selected",
                                        command=self._remove_selected)
        self.remove_button.grid(row=0, column=1, padx=(PAD_S, 0))
        self.clear_button = ttk.Button(btns, text="Clear All", command=self._clear_all)
        self.clear_button.grid(row=0, column=2, padx=(PAD_S, 0))

        self.choose_folder_button = ttk.Button(btns, text="Choose Folder…",
                                               command=self._choose_input_folder)
        self.choose_folder_button.grid(row=0, column=4, sticky="e")

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

        ttk.Checkbutton(
            frame, text="Write replacement log (JSONL alongside each output PDF)",
            variable=self.opt_replacement_log,
        ).pack(anchor="w")
        ttk.Checkbutton(
            frame, text="Save intermediate cleaned text (DEBUG_<name>.txt for inspection)",
            variable=self.opt_debug_text,
        ).pack(anchor="w", pady=(PAD_S, 0))
        ttk.Checkbutton(
            frame, text="Dry run (run full text pipeline, skip PDF output)",
            variable=self.opt_dry_run,
        ).pack(anchor="w", pady=(PAD_S, 0))

    def _build_log_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="Log", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, PAD_M))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            frame, wrap="word", state=tk.DISABLED, height=10, bg=PANEL_BG,
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
        self.run_button = ttk.Button(bar, text="Start Batch Processing",
                                     style="Accent.TButton", command=self._start_batch)
        self.run_button.grid(row=0, column=2, sticky="e")

    def _build_status_bar(self, parent: ttk.Frame, row: int) -> None:
        self.status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").grid(row=row, column=0, sticky="ew")

    # -- input mode -------------------------------------------------------------
    def _on_input_mode_changed(self, log: bool = True) -> None:
        """Flip which mode's controls are live and re-show that mode's file order."""
        folder_mode = self.input_mode_var.get() == "folder"
        upload_state = tk.DISABLED if folder_mode else tk.NORMAL
        folder_state = tk.NORMAL if folder_mode else tk.DISABLED
        for button in (self.add_button, self.remove_button, self.clear_button):
            button.configure(state=upload_state)
        self.choose_folder_button.configure(state=folder_state)

        self._refresh_file_list()
        if log:
            mode_label = "Select Folder" if folder_mode else "Upload PDFs"
            self._log(f"Input mode: {mode_label}", "info")
        self._refresh_status()

    def _choose_input_folder(self) -> None:
        directory = filedialog.askdirectory(title="Select the folder of PDFs to process")
        if directory:
            self._apply_input_folder(directory)

    def _apply_input_folder(self, directory: str) -> None:
        """Scan ``directory`` (recursive, natural order) and display the result."""
        try:
            self.folder_files = scan_folder(directory)
        except (NotADirectoryError, OSError) as exc:
            self._log(f"Could not scan folder: {exc}", "error")
            return
        self.input_folder = directory
        self.folder_var.set(directory)
        self._refresh_file_list()
        self._log(
            f"Scanned folder: {directory} — {len(self.folder_files)} PDF(s) in "
            "processing order.", "info")
        if not self.folder_files:
            self._log("No PDF files found in that folder.", "warn")
        self._refresh_status()

    def _refresh_file_list(self) -> None:
        """Re-render the shared list with the active mode's resolved order."""
        self.file_listbox.delete(0, tk.END)
        if self.input_mode_var.get() == "folder":
            root = Path(self.input_folder) if self.input_folder else None
            for path in self.folder_files:
                label = path.relative_to(root).as_posix() if root else str(path)
                self.file_listbox.insert(tk.END, label)
        else:
            for path in self.file_paths:
                self.file_listbox.insert(tk.END, os.path.basename(path))

    # -- file list actions ------------------------------------------------------
    def _add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select PDF files", filetypes=[("PDF files", "*.pdf")])
        added = 0
        for path in paths:
            if path not in self.file_paths:   # silently skip duplicates
                self.file_paths.append(path)
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
            del self.file_paths[index]
        self._refresh_file_list()
        self._log(f"Removed {len(selection)} file(s).", "info")
        self._refresh_status()

    def _clear_all(self) -> None:
        if not self.file_paths:
            return
        count = len(self.file_paths)
        self.file_paths.clear()
        self._refresh_file_list()
        self._log(f"Cleared {count} file(s).", "info")
        self._refresh_status()

    # -- run / worker -----------------------------------------------------------
    def _start_batch(self) -> None:
        if self._running:
            return
        if self.input_mode_var.get() == "folder":
            if not self.folder_files:
                messagebox.showwarning(
                    "No files",
                    "Select a folder containing at least one PDF before running.")
                return
            files = [str(p) for p in self.folder_files]
            mirror_root = self.input_folder
        else:
            files = list(self.file_paths)
            mirror_root = None
            if not files:
                messagebox.showwarning("No files",
                                       "Add at least one PDF file before running.")
                return

        # Map the display selection to its clean novel name BEFORE it reaches dispatch
        # or folder naming: the "no profile yet" marker is display-only ("Universal"
        # passes through and kebab-cases to universal-x).
        novel = clean_novel_name(self.novel_var.get())

        # Forced output location: a fresh auto-numbered Downloads\<novel>-x folder,
        # named for the current selection. Only named here — run_batch creates it
        # when the batch actually starts (and not at all on a dry run).
        name = kebab_case(novel) or "output"
        output_dir = str(next_numbered_output_dir(downloads_dir(), name))

        # Per-batch snapshot state: the worker thread reads only these plain
        # attributes, never Tk variables (Tk objects are not thread-safe).
        self._batch_files = files
        self._batch_output_dir = output_dir
        self._batch_mirror_root = mirror_root
        self._batch_novel = novel
        self._batch_replacement_log = self.opt_replacement_log.get()
        self._batch_debug_text = self.opt_debug_text.get()
        self._batch_dry_run = self.opt_dry_run.get()

        self._running = True
        self.run_button.configure(state=tk.DISABLED)
        self.pause_gate.set()  # a new batch always starts un-paused
        self.pause_button.configure(state=tk.NORMAL, text="Pause")
        self.progress.configure(maximum=len(files), value=0)
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
                pause_gate=self.pause_gate,

                gui_log=lambda message, level="info": self.after(
                    0, self._log, message, level),
                progress=lambda value: self.after(0, self._set_progress, value),
            )
        except Exception as exc:  # defensive: keep the UI responsive on any crash
            self.after(0, self._on_error, exc)
            return
        self.after(0, self._on_done, summary)

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

    def _on_done(self, summary: dict) -> None:
        self._running = False
        self.run_button.configure(state=tk.NORMAL)
        self._reset_pause_control()
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

        messagebox.showinfo(
            "Batch complete",
            f"Processed {summary['total']} file(s).\n"
            f"Succeeded: {summary['succeeded']}   "
            f"Failed: {summary['failed']}   Skipped: {skipped}\n"
            f"Output folder: {summary['output_dir']}",
        )

    def _on_error(self, exc: Exception) -> None:
        self._running = False
        self.run_button.configure(state=tk.NORMAL)
        self._reset_pause_control()
        self._log(f"Batch aborted: {type(exc).__name__}: {exc}", "error")
        messagebox.showerror("Batch error", f"{type(exc).__name__}: {exc}")

    # -- helpers ----------------------------------------------------------------
    def _set_progress(self, value: int) -> None:
        self.progress.configure(value=value)

    def _log(self, message: str, level: str = "info") -> None:
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
        out_label = (f"Downloads\\{kebab_case(novel_label) or 'output'}-x (auto)"
                     if novel is not None else "Downloads (auto)")
        if getattr(self, "input_mode_var", None) and self.input_mode_var.get() == "folder":
            mode_label = "folder"
            queued = len(self.folder_files)
        else:
            mode_label = "upload"
            queued = len(self.file_paths)
        self.status_var.set(
            f"novel: {novel_label}   |   input: {mode_label}   |   "
            f"{queued} file(s) queued   |   output: {out_label}")


def launch() -> None:
    """Create and run the main application window."""
    app = WebnovelEditorApp()
    app.mainloop()
