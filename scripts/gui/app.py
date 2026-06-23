"""Tkinter main window and all GUI logic.

This is the single-window v1 UI: a file list with Add/Remove/Clear, an output-folder
picker, three option checkboxes, a log widget, a progress bar, and a Run button.

The Run button drives the real `core.batch_runner.run_batch` (Phase 3): extract each
PDF and rebuild it as `EDITED_<name>.pdf`. The editorial rule pipeline is still a Phase 4
no-op, so Phase 3 output is a clean extract -> rebuild round-trip. The worker runs on a
daemon thread and posts every UI update back through `self.after(0, ...)`, so the window
never freezes.

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
from tkinter import filedialog, messagebox, ttk

from core.batch_runner import run_batch
from utils.file_utils import open_in_file_manager

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
        self.title("Webnovel Editor")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.geometry(f"{MIN_WIDTH}x{MIN_HEIGHT}")
        self.configure(bg=WINDOW_BG)

        # State
        self.file_paths: list[str] = []
        self._running = False

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

        style.configure("Accent.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor="#dbe2e7", bordercolor=BORDER, lightcolor=ACCENT,
                        darkcolor=ACCENT)

    # -- layout -----------------------------------------------------------------
    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="TFrame", padding=PAD_M)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        # The log row expands; everything else is fixed height.
        root.rowconfigure(4, weight=1)

        self._build_header(root, row=0)
        self._build_file_panel(root, row=1)
        self._build_output_panel(root, row=2)
        self._build_options_panel(root, row=3)
        self._build_log_panel(root, row=4)
        self._build_run_row(root, row=5)
        self._build_status_bar(root, row=6)

        self._refresh_status()
        self._log("Ready. Add PDF files and choose an output folder to begin.", "muted")

    def _build_header(self, parent: ttk.Frame, row: int) -> None:
        header = ttk.Frame(parent, style="Header.TFrame")
        header.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        ttk.Label(header, text="Webnovel Editor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Batch-clean webscraped chapter PDFs into TTS-ready documents.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

    def _build_file_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="PDF Files", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        frame.columnconfigure(0, weight=1)

        list_wrap = ttk.Frame(frame, style="Panel.TFrame")
        list_wrap.grid(row=0, column=0, sticky="ew")
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
        btns.grid(row=1, column=0, sticky="w", pady=(PAD_M, 0))
        ttk.Button(btns, text="Add PDFs", command=self._add_pdfs).pack(side="left")
        ttk.Button(btns, text="Remove Selected", command=self._remove_selected).pack(
            side="left", padx=(PAD_S, 0))
        ttk.Button(btns, text="Clear All", command=self._clear_all).pack(
            side="left", padx=(PAD_S, 0))

    def _build_output_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="Output Folder", style="Card.TLabelframe",
                               padding=PAD_M)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        frame.columnconfigure(0, weight=1)

        self.output_var = tk.StringVar(value="Not selected")
        ttk.Label(frame, textvariable=self.output_var, style="PathValue.TLabel",
                  anchor="w").grid(row=0, column=0, sticky="ew", padx=(0, PAD_M))
        ttk.Button(frame, text="Choose Output Folder",
                   command=self._choose_output).grid(row=0, column=1, sticky="e")

    def _build_options_panel(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Labelframe(parent, text="Options", style="Card.TLabelframe",
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
        bar.grid(row=row, column=0, sticky="ew", pady=(0, PAD_S))
        bar.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(bar, mode="determinate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, PAD_M))
        self.run_button = ttk.Button(bar, text="Start Batch Processing",
                                     style="Accent.TButton", command=self._start_batch)
        self.run_button.grid(row=0, column=1, sticky="e")

    def _build_status_bar(self, parent: ttk.Frame, row: int) -> None:
        self.status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").grid(row=row, column=0, sticky="ew")

    # -- file list actions ------------------------------------------------------
    def _add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select PDF files", filetypes=[("PDF files", "*.pdf")])
        added = 0
        for path in paths:
            if path not in self.file_paths:   # silently skip duplicates
                self.file_paths.append(path)
                self.file_listbox.insert(tk.END, os.path.basename(path))
                added += 1
        if added:
            self._log(f"Added {added} file(s).", "info")
        self._refresh_status()

    def _remove_selected(self) -> None:
        selection = list(self.file_listbox.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self.file_listbox.delete(index)
            del self.file_paths[index]
        self._log(f"Removed {len(selection)} file(s).", "info")
        self._refresh_status()

    def _clear_all(self) -> None:
        if not self.file_paths:
            return
        count = len(self.file_paths)
        self.file_listbox.delete(0, tk.END)
        self.file_paths.clear()
        self._log(f"Cleared {count} file(s).", "info")
        self._refresh_status()

    def _choose_output(self) -> None:
        directory = filedialog.askdirectory(title="Choose output folder")
        if directory:
            self.output_dir = directory
            self.output_var.set(directory)
            self._log(f"Output folder set: {directory}", "info")
            self._refresh_status()

    # -- run / worker -----------------------------------------------------------
    def _start_batch(self) -> None:
        if self._running:
            return
        if not self.file_paths:
            messagebox.showwarning("No files", "Add at least one PDF file before running.")
            return
        if not getattr(self, "output_dir", ""):
            messagebox.showwarning("No output folder",
                                   "Choose an output folder before running.")
            return

        self._running = True
        self.run_button.configure(state=tk.DISABLED)
        self.progress.configure(maximum=len(self.file_paths), value=0)
        dry = self.opt_dry_run.get()
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
                list(self.file_paths),
                self.output_dir,
                write_replacement_log=self.opt_replacement_log.get(),
                write_debug_text=self.opt_debug_text.get(),
                dry_run=self.opt_dry_run.get(),
                gui_log=lambda message, level="info": self.after(
                    0, self._log, message, level),
                progress=lambda value: self.after(0, self._set_progress, value),
            )
        except Exception as exc:  # defensive: keep the UI responsive on any crash
            self.after(0, self._on_error, exc)
            return
        self.after(0, self._on_done, summary)

    def _on_done(self, summary: dict) -> None:
        self._running = False
        self.run_button.configure(state=tk.NORMAL)
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
        out = getattr(self, "output_dir", "")
        out_label = out if out else "not selected"
        self.status_var.set(
            f"{len(self.file_paths)} file(s) queued   |   output: {out_label}")


def launch() -> None:
    """Create and run the main application window."""
    app = WebnovelEditorApp()
    app.mainloop()
