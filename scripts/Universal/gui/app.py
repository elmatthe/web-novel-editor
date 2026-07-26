"""Tkinter main window and all GUI logic.

This is the single-window UI, laid out in **two columns since v0.13.0**: the controls
on the left (a two-mode Input card, three option checkboxes, an optional AI editorial
pass card, a progress bar and Run + Pause/Continue/Stop buttons) and the log on the
right, spanning their rows. It used to be one column with the log at the bottom, which
meant the window had to be tall enough for every control *plus* the log — more than a
1080p desktop offers — so the log and the status strip were clipped off the bottom.
The log's content and its condensed one-line-per-file format are unchanged; only where
it sits moved. Pause and stop are honored between files — the current file always
finishes. The output location is not user-chosen (v0.11.0): every batch writes into a
fresh auto-numbered `Downloads\\<novel>-x` folder — flat in upload mode, mirroring the
selected folder's structure in folder mode — with original filenames kept.

The AI card (Plan 2a Phase 7) is strictly opt-in and always comes up OFF, so an ordinary
launch is deterministic script-only editing that constructs no provider and contacts no
service. Turning it on is the only thing that ever probes the local AI service, and the
status line it shows is the provider's own `ProviderStatus` — see `gui.ai_settings`.

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

from ai.redaction import redact
from core.batch_runner import run_batch
from core.input_scanner import scan_folder
from core.novel_registry import DEFAULT_NOVEL, available_novels, clean_novel_name
from core.run_manifest import RunCheckpoint, find_resumable_run
from gui import ai_settings, cloud_ui
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
# The AI status line reuses the log's semantic levels so one provider state reads the
# same whether it lands in the status line or the log.
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
    Inevitability — no profile yet" — is never truncated in either the closed
    display or the open list, and so onboarding a longer novel name keeps the
    widget correct without a hand-tuned constant. The +2 leaves room beside the
    dropdown arrow.
    """
    longest = max((len(label) for label in roster), default=0)
    return longest + 2


class _QuotaStopRelay:
    """Passes Phase 4's quota stop to Phase 5's checkpoint, and then to the log.

    The limiter takes one ``on_quota_stop`` callback and the checkpoint provides one, so
    the GUI needs somewhere to hang its own line without either layer growing a second
    callback. This is that somewhere: it is duck-typed exactly like a ``RunCheckpoint``
    (``build_provider_factory`` only ever reads ``.on_quota_stop``), so neither
    ``rate_limits.py`` nor ``run_manifest.py`` changes shape to accommodate it.

    Order matters. The checkpoint writes the manifest and sets the stop event first, so
    the run is already durably stopped before anything is drawn; the log line then
    reports what happened. A logging fault can never cost the user the checkpoint.
    """

    def __init__(self, checkpoint, log):
        self._checkpoint = checkpoint
        self._log = log

    def on_quota_stop(self, stop) -> None:
        self._checkpoint.on_quota_stop(stop)
        try:
            record = stop.as_dict()
        except Exception:  # pragma: no cover - defensive against a foreign object
            record = {}
        message, level = cloud_ui.quota_stop_message(record)
        self._log(message, level)


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
        # Resolved AI defaults (in-code < config.toml < per-user settings). `enabled`
        # is always False here — the opt-in switch is deliberately session-only, so no
        # persisted choice can bring the app up with the AI pass already on.
        # A broken/absent config must never stop the app opening.
        try:
            self.ai_prefs = ai_settings.load_ai_preferences()
        except Exception:
            self.ai_prefs = {"enabled": False, "model": "",
                             "provider": cloud_ui.local_provider(),
                             "policy": ai_settings.DEFAULT_POLICY}

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
        # Column 0 holds the controls at their natural size and never flexes, so no
        # card can be squeezed however the window is resized. Column 1 is the log, and
        # it takes every pixel of horizontal slack. Row 6 is an empty spacer that takes
        # the vertical slack on the left, which lets the log stretch through its
        # rowspan without stretching any control.
        root.columnconfigure(0, weight=0, minsize=CONTROL_COLUMN_WIDTH)
        root.columnconfigure(1, weight=1, minsize=LOG_COLUMN_WIDTH)
        root.rowconfigure(6, weight=1)

        self._build_header(root, row=0)
        self._build_novel_panel(root, row=1)
        self._build_file_panel(root, row=2)
        self._build_options_panel(root, row=3)
        self._build_ai_panel(root, row=4)
        self._build_run_row(root, row=5)
        self._build_log_panel(root, row=1, column=1, rowspan=6)
        self._build_status_bar(root, row=7)

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
        # scripts/Universal/resources/novel-index/, profile-less novels marked "no
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
            list_wrap, selectmode=tk.EXTENDED, height=4, activestyle="none",
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

        # Two columns rather than three stacked rows: the same three options, one row
        # of height cheaper. Every pixel here is one the Start button was being pushed
        # down by.
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            frame, text="Write replacement log (JSONL beside each PDF)",
            variable=self.opt_replacement_log,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            frame, text="Dry run (full text pipeline, no PDF output)",
            variable=self.opt_dry_run,
        ).grid(row=0, column=1, sticky="w", padx=(PAD_M, 0))
        ttk.Checkbutton(
            frame, text="Save intermediate cleaned text (DEBUG_<name>.txt)",
            variable=self.opt_debug_text,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(PAD_S, 0))

    # -- AI editorial pass ------------------------------------------------------
    def _build_ai_panel(self, parent: ttk.Frame, row: int) -> None:
        """The optional AI pass (Plan 2a Phase 7).

        Always off at launch. While it is off every control below is disabled and
        no provider is constructed, health checked, or contacted — the app behaves
        exactly as it did before this card existed.
        """
        frame = ttk.Labelframe(parent, text="AI Editorial Pass (optional)",
                               style="Card.TLabelframe", padding=(PAD_M, PAD_S))
        frame.grid(row=row, column=0, sticky="ew", pady=(0, PAD_M))
        frame.columnconfigure(4, weight=1)

        self.opt_ai_enabled = tk.BooleanVar(value=False)
        self.opt_ai_dry_run = tk.BooleanVar(value=False)
        self.ai_model_var = tk.StringVar(value=str(self.ai_prefs.get("model", "")))
        self.ai_policy_var = tk.StringVar(
            value=str(self.ai_prefs.get("policy", ai_settings.DEFAULT_POLICY)))
        self.ai_status_var = tk.StringVar(value="")
        # Provider selection (Plan 2b Phase 6). The rows themselves — including which
        # ones may be picked and the plain sentence explaining any that may not — are
        # decided in `gui.cloud_ui`; this widget only renders them.
        self._provider_options: tuple = ()
        self._provider_labels: dict[str, str] = {}
        self._provider_by_label: dict[str, str] = {}
        # Which provider the model dropdown's current values belong to. See
        # `_refresh_model_choices` — this is what stops one provider's models being
        # left on screen after a switch to another.
        self._model_choices_provider: str | None = None
        self._ai_provider = str(
            self.ai_prefs.get("provider") or cloud_ui.local_provider())
        self.ai_provider_var = tk.StringVar(value="")

        self.ai_enable_check = ttk.Checkbutton(
            frame,
            text="Run an AI proofreading pass after the scripted editing",
            variable=self.opt_ai_enabled, command=self._on_ai_toggled,
        )
        self.ai_enable_check.grid(row=0, column=0, columnspan=4, sticky="w")
        self.ai_check_button = ttk.Button(frame, text="Check service",
                                          command=self._check_ai_service)
        self.ai_check_button.grid(row=0, column=4, sticky="e")

        ttk.Label(frame, text="Provider:", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(PAD_M, PAD_S), pady=(PAD_S, 0))
        self.ai_provider_combo = ttk.Combobox(
            frame, textvariable=self.ai_provider_var, values=[], state=tk.DISABLED,
            font=self.font_body, width=26,
        )
        self.ai_provider_combo.grid(row=1, column=1, sticky="w", pady=(PAD_S, 0))
        self.ai_provider_combo.bind("<<ComboboxSelected>>", self._on_ai_provider_changed)

        # Cloud keys are entered here (Phase 6 gap-fill). One button acting on the
        # selected provider, not two permanent ones: the keys stay entirely
        # independent — separate storage entries, separate save and separate forget —
        # and a second always-visible button would cost a card row for nothing.
        self.ai_key_button = ttk.Button(frame, text="Key…",
                                        command=self._open_key_dialog, width=6)
        self.ai_key_button.grid(row=1, column=2, sticky="w",
                                padx=(PAD_S, 0), pady=(PAD_S, 0))

        ttk.Label(frame, text="Model:", style="Panel.TLabel").grid(
            row=1, column=3, sticky="e", padx=(PAD_M, PAD_S), pady=(PAD_S, 0))
        # Local: the values are filled only from a live list of installed tags, and no
        # model tag is hardcoded in this UI. Cloud: the values come from the reviewed
        # [[ai.approved_models]] records and never from a live "list models" call — a
        # list endpoint reports availability, not free-tier eligibility for this account.
        self.ai_model_combo = ttk.Combobox(
            frame, textvariable=self.ai_model_var, values=[], state=tk.DISABLED,
            font=self.font_body, width=28,
        )
        self.ai_model_combo.grid(row=1, column=4, sticky="w", pady=(PAD_S, 0))
        self.ai_model_combo.bind("<<ComboboxSelected>>", self._on_ai_model_changed)

        policy_wrap = ttk.Frame(frame, style="Panel.TFrame")
        policy_wrap.grid(row=2, column=0, columnspan=4, sticky="w",
                         padx=(PAD_M, 0), pady=(PAD_S, 0))
        ttk.Label(policy_wrap, text="If the AI is unavailable:",
                  style="Panel.TLabel").pack(side="left", padx=(0, PAD_S))
        self.ai_policy_radios = []
        for label, value in (
            ("Use the scripted result", ai_settings.POLICY_PREFER_AI),
            ("Stop the batch", ai_settings.POLICY_AI_REQUIRED),
        ):
            radio = ttk.Radiobutton(
                policy_wrap, text=label, value=value, variable=self.ai_policy_var,
                command=self._on_ai_policy_changed, state=tk.DISABLED,
            )
            radio.pack(side="left", padx=(0, PAD_M))
            self.ai_policy_radios.append(radio)

        # The provider dropdown (Phase 6) needed a row of its own, so the dry-run
        # checkbox shares the policy row rather than growing the card: the card's fixed
        # height is pinned against MIN_HEIGHT by a test, and a taller window would push
        # the Start button toward the bottom of a 1080p screen.
        self.ai_dry_run_check = ttk.Checkbutton(
            frame, text="Also use the AI in dry runs",
            variable=self.opt_ai_dry_run, state=tk.DISABLED,
        )
        self.ai_dry_run_check.grid(row=2, column=4, sticky="e", pady=(PAD_S, 0))

        self.ai_status_label = ttk.Label(
            frame, textvariable=self.ai_status_var, style="Panel.TLabel",
            wraplength=760, justify="left",
        )
        self.ai_status_label.grid(row=3, column=0, columnspan=5, sticky="w",
                                  pady=(PAD_S, 0))

        self._refresh_provider_options()
        self._set_ai_status(ai_settings.STATUS_UNCHECKED)
        self._refresh_ai_children()

    # -- provider selection -----------------------------------------------------
    def _settings_file(self):
        return ai_settings.default_settings_file()

    def _refresh_provider_options(self) -> None:
        """Re-read every provider's status. Pure policy — nothing is contacted."""
        try:
            options = cloud_ui.provider_options(
                ai_table=self.ai_prefs,
                selected=self._ai_provider,
                model_id=self.ai_model_var.get().strip(),
                settings_file=self._settings_file(),
                **self._key_locations(),
            )
        except Exception:
            # A broken config must never stop the panel rendering; the local path is
            # always available and is what the app falls back to.
            options = ()
        if not options:
            options = (cloud_ui.provider_option(cloud_ui.local_provider()),)

        self._provider_options = options
        # An unselectable row is still shown, with the marker and the reason, so the
        # user learns *why* rather than finding a provider silently missing.
        self._provider_labels = {
            opt.provider: (opt.label if opt.selectable
                           else f"{opt.label} — unavailable")
            for opt in options
        }
        self._provider_by_label = {v: k for k, v in self._provider_labels.items()}
        self.ai_provider_combo.configure(values=list(self._provider_labels.values()))
        self.ai_provider_var.set(
            self._provider_labels.get(self._ai_provider,
                                      self._provider_labels[cloud_ui.local_provider()])
        )
        self._refresh_model_choices()

    def _provider_option(self, name: str):
        for option in self._provider_options:
            if option.provider == name:
                return option
        return None

    def _refresh_model_choices(self) -> None:
        """Keep the model list owned by the provider it was built for.

        The invariant: **a model list never outlives the provider it belongs to.** It
        is enforced by remembering whose models are currently in the box, rather than
        by clearing on every refresh — several callers refresh options for unrelated
        reasons (a saved key, an accepted disclosure) and must not wipe a list the
        local probe has just filled in.

        Cloud values come from the reviewed records and are known immediately. Local
        tags are only knowable by asking the service, so the honest interim list is
        **empty** — never the previous provider's, which would leave a cloud model ID
        selectable while the local provider is active.
        """
        if self._model_choices_provider == self._ai_provider:
            return
        self._model_choices_provider = self._ai_provider

        if not cloud_ui.is_cloud_provider(self._ai_provider):
            self.ai_model_combo.configure(values=[])
            return
        option = self._provider_option(self._ai_provider)
        choices = list(option.models) if option is not None else []
        self.ai_model_combo.configure(values=choices)
        if self.ai_model_var.get().strip() not in choices:
            self.ai_model_var.set(choices[0] if len(choices) == 1 else "")

    def _on_ai_provider_changed(self, _event=None) -> None:
        chosen = self._provider_by_label.get(self.ai_provider_var.get(), "")
        option = self._provider_option(chosen)
        if option is not None and not option.selectable:
            # Refused, with the reason — never a silently ignored click.
            self.ai_provider_var.set(self._provider_labels[self._ai_provider])
            self._set_ai_status_text(option.reason, "warn")
            self._log(option.reason, "warn")
            return
        if not chosen or chosen == self._ai_provider:
            return
        self._ai_provider = chosen
        self.ai_model_var.set("")
        self._refresh_provider_options()
        self._persist_ai_choices()
        if cloud_ui.is_cloud_provider(chosen):
            self._publish_provider_status()
            return
        # Local: the installed tags have to be asked for. This is the same probe the
        # opt-in checkbox already triggers — reused, not duplicated. Without it the
        # model list only ever repopulated when the checkbox was toggled, which is
        # what made switching back to the local provider look broken.
        self._set_ai_status(ai_settings.STATUS_UNCHECKED)
        self._check_ai_service()

    # -- cloud API keys ---------------------------------------------------------
    def _secrets_file(self):
        """The per-user secrets location, from Phase 1. Never a path built here."""
        from ai.secrets import default_secrets_file

        return default_secrets_file()

    def _key_locations(self) -> dict:
        """Where keys are looked for, resolved here and passed on explicitly.

        Phase 1's readers default these internally, which is right for production but
        leaves the panel silently depending on module-level defaults it never named.
        Resolving them once and handing them over — the same seam `_settings_file`
        already provides — keeps every key lookup the panel makes pointed at one
        agreed location.
        """
        from ai.secrets import DEFAULT_DOTENV_PATH

        return {"secrets_file": self._secrets_file(), "dotenv_path": DEFAULT_DOTENV_PATH}

    def _apply_key_entry(self, provider: str, key: str) -> None:
        """Save one key and re-publish the provider's status.

        The value is handed straight to Phase 1's storage and is never held, echoed,
        or logged here — only the outcome sentence, which by construction contains no
        key. The status afterwards comes from Phase 6's existing provider logic, so a
        key saved in-app reads exactly like one found in an environment variable.
        """
        outcome = cloud_ui.save_key(provider, key, secrets_file=self._secrets_file())
        self._log(outcome.message, outcome.level)
        self._refresh_provider_options()
        self._publish_provider_status()

    def _forget_key(self, provider: str) -> None:
        """Remove the saved copy of one key, so both storage paths can be tested."""
        outcome = cloud_ui.forget_key(provider, secrets_file=self._secrets_file())
        self._log(outcome.message, outcome.level)
        self._refresh_provider_options()
        self._publish_provider_status()

    def _build_key_dialog(self, provider: str):
        """Construct the masked key dialog. Returns a handle so tests can inspect it.

        Deliberately thin: every decision (what to say, whether a saved key exists to
        forget, which source currently wins) is `cloud_ui.key_prompt`'s.
        """
        prompt = cloud_ui.key_prompt(provider, **self._key_locations())
        if prompt is None:
            return None

        window = tk.Toplevel(self)
        window.title(prompt.title)
        window.configure(bg=WINDOW_BG)
        window.transient(self)
        window.resizable(False, False)

        body = ttk.Frame(window, style="TFrame", padding=PAD_M)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text=prompt.body, style="Panel.TLabel", wraplength=460,
                  justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text=prompt.current, style="PathValue.TLabel", wraplength=460,
                  justify="left").grid(row=1, column=0, sticky="w", pady=(PAD_S, 0))

        # Masked while typing. The variable is local to this dialog and is cleared
        # below as soon as the value has been handed to storage.
        entry_var = tk.StringVar(value="")
        entry = ttk.Entry(body, textvariable=entry_var, show="•", width=52,
                          font=self.font_body)
        entry.grid(row=2, column=0, sticky="ew", pady=(PAD_M, 0))
        entry.focus_set()

        buttons = ttk.Frame(body, style="TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(PAD_M, 0))
        buttons.columnconfigure(1, weight=1)

        def _close() -> None:
            entry_var.set("")
            window.destroy()

        def _save() -> None:
            value = entry_var.get()
            entry_var.set("")          # out of the widget before anything else runs
            self._apply_key_entry(provider, value)
            window.destroy()

        def _forget() -> None:
            self._forget_key(provider)
            _close()

        forget_button = ttk.Button(buttons, text="Forget saved key", command=_forget)
        forget_button.grid(row=0, column=0, sticky="w")
        if not prompt.can_forget:
            forget_button.configure(state=tk.DISABLED)
        ttk.Button(buttons, text="Cancel", command=_close).grid(
            row=0, column=1, sticky="e", padx=(0, PAD_S))
        ttk.Button(buttons, text="Save", style="Accent.TButton",
                   command=_save).grid(row=0, column=2, sticky="e")

        window.bind("<Return>", lambda _event: _save())
        window.bind("<Escape>", lambda _event: _close())
        window.protocol("WM_DELETE_WINDOW", _close)

        return SimpleNamespace(window=window, entry=entry, prompt=prompt,
                               save=_save, forget=_forget, cancel=_close)

    def _open_key_dialog(self) -> None:
        dialog = self._build_key_dialog(self._ai_provider)
        if dialog is None:
            return
        dialog.window.grab_set()
        dialog.window.wait_window()

    def _publish_provider_status(self) -> None:
        """Show the selected provider's own sentence, or fall back to the local flow."""
        option = self._provider_option(self._ai_provider)
        if option is None or not option.is_cloud:
            self._set_ai_status(ai_settings.STATUS_UNCHECKED)
            return
        if option.ready:
            message, level = ai_settings.describe_status(
                option.status, model=self.ai_model_var.get().strip())
            self._set_ai_status_text(message, level)
        else:
            self._set_ai_status_text(option.reason, option.level)

    def _current_ai_prefs(self) -> dict:
        """The resolved defaults with the panel's live choices layered on top."""
        prefs = dict(self.ai_prefs)
        prefs["provider"] = self._ai_provider
        prefs["model"] = self.ai_model_var.get().strip()
        prefs["policy"] = self.ai_policy_var.get()
        return prefs

    def _refresh_ai_children(self, *, locked: bool = False) -> None:
        """Enable the AI controls only while the pass is on and no batch is running."""
        live = self.opt_ai_enabled.get() and not locked
        for combo in (self.ai_model_combo, self.ai_provider_combo):
            combo.configure(state="readonly" if live else tk.DISABLED)
        for widget in (self.ai_check_button, self.ai_dry_run_check,
                       *self.ai_policy_radios):
            widget.configure(state=tk.NORMAL if live else tk.DISABLED)
        # Only a cloud provider has a key to enter.
        self.ai_key_button.configure(
            state=tk.NORMAL
            if live and cloud_ui.is_cloud_provider(self._ai_provider)
            else tk.DISABLED)

    def _set_ai_controls_running(self, running: bool) -> None:
        self.ai_enable_check.configure(state=tk.DISABLED if running else tk.NORMAL)
        self._refresh_ai_children(locked=running)

    def _set_ai_status(self, status: str) -> None:
        """Show one provider state verbatim — never a flattened 'unavailable'."""
        message, level = ai_settings.describe_status(
            status, model=self.ai_model_var.get().strip())
        self._set_ai_status_text(message, level)

    def _set_ai_status_text(self, message: str, level: str = "info") -> None:
        """Publish a status sentence that already reads as plain English.

        Cloud readiness produces its own exact sentence (which key is missing, which
        model is not approved, that consent is outstanding), so there is nothing for
        this layer to re-word — it would only blur it.
        """
        self.ai_status_var.set(message)
        self.ai_status_label.configure(
            foreground=LEVEL_COLORS.get(level, TEXT_BODY))

    def _on_ai_toggled(self) -> None:
        self._refresh_ai_children()
        if self.opt_ai_enabled.get():
            self._refresh_provider_options()
            if cloud_ui.is_cloud_provider(self._ai_provider):
                self._publish_provider_status()
                return
            self._log("AI editorial pass on — checking the local AI service…", "info")
            self._check_ai_service()
        else:
            self._set_ai_status(ai_settings.STATUS_UNCHECKED)
            self._log("AI editorial pass off — scripted editing only.", "muted")

    def _on_ai_model_changed(self, _event=None) -> None:
        self._persist_ai_choices()
        if cloud_ui.is_cloud_provider(self._ai_provider):
            # A cloud model choice changes readiness (consent, approval), not service
            # health — and nothing is contacted until the run actually starts.
            self._refresh_provider_options()
            self._publish_provider_status()
            return
        self._set_ai_status(ai_settings.STATUS_UNCHECKED)
        self._check_ai_service()

    def _on_ai_policy_changed(self) -> None:
        self._persist_ai_choices()

    def _persist_ai_choices(self) -> None:
        """Remember the model and policy for next time; the switch is never saved.

        A non-writable profile folder is not an error worth interrupting anyone
        over — the choices simply do not survive the session.
        """
        if not ai_settings.save_ai_preferences(self._current_ai_prefs()):
            self._log("Could not save your AI choices — they apply to this "
                      "session only.", "muted")

    def _check_ai_service(self) -> None:
        """Ask the provider for its real health and installed models, off the UI
        thread (it talks to the service and can block up to the timeout).

        For a cloud provider this is refused until every rail is already satisfied.
        Listing models sends no chapter text, but contacting a company the user has not
        yet consented to talk to — before the disclosure has even been shown — is not
        the app's call to make. Until then the panel reports the readiness reason, which
        is the thing the user actually has to act on anyway.
        """
        if not self.opt_ai_enabled.get() or self._running:
            return
        if cloud_ui.is_cloud_provider(self._ai_provider):
            self._refresh_provider_options()
            option = self._provider_option(self._ai_provider)
            if option is None or not option.ready:
                self._publish_provider_status()
                return
        prefs = self._current_ai_prefs()
        self.ai_check_button.configure(state=tk.DISABLED)

        def worker() -> None:
            probe = ai_settings.probe_provider(prefs)
            self.after(0, self._apply_probe, probe)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_probe(self, probe) -> None:
        """Publish one probe result: the available models, and the provider's status."""
        if cloud_ui.is_cloud_provider(self._ai_provider):
            # A live list is availability, not eligibility: it is used only to detect a
            # retired model, never to widen what the picker offers.
            self._refresh_provider_options()
            option = cloud_ui.provider_option(
                self._ai_provider,
                ai_table=self.ai_prefs,
                model_id=self.ai_model_var.get().strip(),
                settings_file=self._settings_file(),
                discovered_ids=tuple(probe.models),
                **self._key_locations(),
            )
            self._set_ai_status_text(
                option.reason or ai_settings.describe_status(
                    option.status, model=self.ai_model_var.get().strip())[0],
                option.level,
            )
        else:
            self.ai_model_combo.configure(values=list(probe.models))
            self._set_ai_status(probe.status)
        self._refresh_ai_children(locked=self._running)

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

    # -- cloud run preflight ----------------------------------------------------
    def _offer_resume(self):
        """Offer to continue an unfinished run, if there is one. Never raises.

        Only cloud runs write a manifest (Plan 2b reverses Plan 1's session-only
        decision *for cloud runs specifically*), so a purely local user never sees this
        dialog. Declining is not a call into the manifest layer at all — it simply takes
        the normal fresh-run path, which allocates the next `<novel>-N` folder as usual.
        """
        try:
            offer = find_resumable_run(downloads_dir())
        except Exception:
            return None
        if not offer.available:
            return None
        accepted = messagebox.askyesno(
            "Resume unfinished run?", cloud_ui.resume_prompt(offer))
        plan = cloud_ui.resume_decision(offer, accepted=bool(accepted))
        self._log(plan.message, "accent" if plan.resumed else "muted")
        return plan if plan.resumed else None

    def _consent_for(self, provider: str) -> bool:
        """Show the privacy/billing disclosure if it is owed, and record the answer.

        Owed means: never acknowledged, or acknowledged at an older disclosure version.
        Only the version is recorded — never chapter text, never the key. Cancelling is
        a first-class outcome, not an error: the run simply does not start, and the user
        is told the two ways to carry on without sending anything anywhere.
        """
        need = cloud_ui.disclosure_requirement(
            provider, settings_file=self._settings_file())
        if not need.required:
            return True
        accepted = messagebox.askokcancel(
            need.title, f"{need.body}\n\n{need.accept_label}?", icon="warning")
        if not accepted:
            self._log(
                "Cloud editing cancelled — no chapter text was sent. Choose the local "
                "provider to edit on this computer, or turn the AI pass off for "
                "script-only editing.", "warn")
            self._set_ai_status_text(need.cancel_label, "warn")
            return False
        if not cloud_ui.accept_disclosure(provider, settings_file=self._settings_file()):
            self._log(
                "Could not save the cloud disclosure acknowledgement — it will be "
                "asked again next time.", "muted")
        self._refresh_provider_options()
        return True

    def _confirm_cloud_estimate(self, provider, model, remaining, fallback_rate) -> bool:
        """Show the labelled estimate prominently, before the run starts.

        Deliberately not a log line: this is where the user finds out that a free tier
        may not be able to finish what they queued. The estimate says plainly which of
        its inputs are unknown rather than inventing a number for them.
        """
        try:
            settings = cloud_ui.provider_settings(self.ai_prefs, provider)
        except Exception:
            settings = None
        estimate = cloud_ui.estimate_run(
            provider=provider,
            model_id=model,
            remaining_files=remaining,
            settings=settings,
            fallback_rate=fallback_rate,
        )
        self.rate_var.set(estimate.headline)
        return bool(messagebox.askokcancel("Start cloud run?", estimate.as_text()))

    # -- run / worker -----------------------------------------------------------
    def _start_batch(self) -> None:
        if self._running:
            return
        # A resume supplies its own file list and its own output folder, so it is asked
        # about before the input checks a fresh run has to pass.
        resume = self._offer_resume()
        if resume is not None:
            return self._begin(
                files=list(resume.run_kwargs["pdf_paths"]),
                output_dir=resume.run_kwargs["output_dir"],
                mirror_root=resume.run_kwargs["mirror_root"],
                novel=resume.run_kwargs["novel_name"] or clean_novel_name(
                    self.novel_var.get()),
                resume=resume,
            )
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
        return self._begin(
            files=files, output_dir=output_dir, mirror_root=mirror_root, novel=novel)

    def _begin(self, *, files, output_dir, mirror_root, novel, resume=None) -> None:
        """Commit to one batch: consent, checkpoint, editor, estimate, then run."""
        # The AI pass is opt-in per run. When it is off, nothing below constructs a
        # provider and run_batch receives ai_editor=None — the exact script-only path.
        ai_editor = None
        use_ai_in_dry_run = False
        checkpoint = None
        provider = self._ai_provider
        is_cloud = self.opt_ai_enabled.get() and cloud_ui.is_cloud_provider(provider)

        if self.opt_ai_enabled.get():
            model = self.ai_model_var.get().strip()
            if not model:
                messagebox.showwarning(
                    "No AI model selected",
                    "The AI editorial pass is on, but no model is selected.\n\n"
                    "Pick one of the models offered for the selected provider, "
                    "or turn the AI pass off to run the scripted editing only.")
                return
            if is_cloud:
                if not self._consent_for(provider):
                    return
                option = self._provider_option(provider)
                if option is not None and not option.ready:
                    messagebox.showwarning("Cloud provider not ready", option.reason)
                    self._set_ai_status_text(option.reason, option.level)
                    return
                if not self._confirm_cloud_estimate(
                    provider, model, len(files),
                    resume.fallback_rate if resume is not None else None,
                ):
                    self._log("Cloud run cancelled before it started.", "muted")
                    return

            prefs = self._current_ai_prefs()
            if is_cloud and not self.opt_dry_run.get():
                # A checkpoint is written for cloud runs only, so a daily quota stop is
                # resumable tomorrow. Plan 1's session-only behaviour for local runs is
                # deliberately untouched.
                checkpoint_kwargs = (
                    dict(resume.checkpoint_kwargs) if resume is not None
                    else {
                        "output_dir": output_dir,
                        "queue": list(files),
                        "novel": novel,
                        "mirror_root": mirror_root,
                        "provider": provider,
                        "model_id": model,
                        "prompt_version": str(prefs.get("prompt_version") or ""),
                        "gate_version": str(prefs.get("gate_version") or ""),
                        "ai_policy": str(prefs.get("policy") or ""),
                    }
                )
                checkpoint = RunCheckpoint(
                    checkpoint_kwargs.pop("output_dir"),
                    checkpoint_kwargs.pop("queue"),
                    stop_event=self.stop_event,
                    **checkpoint_kwargs,
                )

            try:
                ai_editor = ai_settings.build_ai_editor(
                    prefs,
                    checkpoint=(_QuotaStopRelay(checkpoint, self._thread_log)
                                if checkpoint else None),
                    stop_event=self.stop_event,
                    pause_gate=self.pause_gate,
                    settings_file=self._settings_file(),
                )
            except Exception as exc:
                # The Phase 7a spend guard runs inside this call for a cloud provider,
                # before the adapter exists and before the batch thread starts. A
                # refusal stops the run here and is shown in full — not logged and
                # stepped over. There is deliberately no "run anyway" button: the guard
                # refuses only when the app cannot confirm the run stays free.
                reason = str(exc) or (
                    "The cloud run was refused before anything was sent.")
                messagebox.showerror("Cloud run refused", reason)
                self._log(reason, "error")
                self._set_ai_status_text(reason, "error")
                return
            use_ai_in_dry_run = self.opt_ai_dry_run.get()

        # Per-batch snapshot state: the worker thread reads only these plain
        # attributes, never Tk variables (Tk objects are not thread-safe).
        self._batch_files = files
        self._batch_output_dir = output_dir
        self._batch_mirror_root = mirror_root
        self._batch_novel = novel
        self._batch_replacement_log = self.opt_replacement_log.get()
        self._batch_debug_text = self.opt_debug_text.get()
        self._batch_dry_run = self.opt_dry_run.get()
        self._batch_ai_editor = ai_editor
        self._batch_use_ai_in_dry_run = use_ai_in_dry_run
        self._batch_checkpoint = checkpoint

        self._running = True
        self.run_button.configure(state=tk.DISABLED)
        self.pause_gate.set()  # a new batch always starts un-paused
        self.stop_event.clear()
        self.pause_button.configure(state=tk.NORMAL, text="Pause")
        self.stop_button.configure(state=tk.NORMAL)
        self._set_ai_controls_running(True)
        self.progress.configure(maximum=len(files), value=0)
        self._begin_rate_tracking(len(files))
        dry = self._batch_dry_run
        self._log(
            "--- Starting batch ---" + (" (dry run, no PDF output)" if dry else ""),
            "accent",
        )
        if ai_editor is not None:
            fallback = (
                "stop the batch"
                if ai_editor.options.policy.value == ai_settings.POLICY_AI_REQUIRED
                else "keep the scripted result"
            )
            self._log(
                f"AI editorial pass on — model {ai_editor.options.model_id}; "
                f"if the AI is unavailable, {fallback}.", "accent")
            # Condensed log: provider and model are run-scoped facts and cannot change
            # mid-run, so they extend the run header rather than repeating on every
            # per-file line. The `[i/total] name — outcome` line is untouched.
            header = cloud_ui.cloud_run_header(
                self._ai_provider, ai_editor.options.model_id)
            if header is not None:
                self._log(*header)

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
                stop_event=self.stop_event,
                ai_editor=self._batch_ai_editor,
                use_ai_in_dry_run=self._batch_use_ai_in_dry_run,
                checkpoint=getattr(self, "_batch_checkpoint", None),

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
        self.run_button.configure(state=tk.NORMAL)
        self._reset_pause_control()
        self._reset_stop_control()
        self._set_ai_controls_running(False)
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
        self._reset_stop_control()
        self._set_ai_controls_running(False)
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
        rate = ai_settings.compute_rate(
            completed, self._batch_total, time.monotonic() - started)
        self.rate_var.set(ai_settings.format_rate(rate))

    def _set_progress(self, value: int) -> None:
        self.progress.configure(value=value)
        self._update_rate(value)

    def _thread_log(self, message: str, level: str = "info") -> None:
        """Log from a worker thread. Tk objects are not thread-safe, so every
        message is marshalled back onto the UI thread exactly as run_batch's own
        gui_log callback already does."""
        self.after(0, self._log, message, level)

    def _log(self, message: str, level: str = "info") -> None:
        # The single GUI log sink, and therefore the place credentials would surface
        # if anything upstream ever put one in a message. Everything written to the
        # panel goes through the one redaction boundary (Plan 2b Phase 1) — never
        # bypass this by writing to log_text directly.
        message = redact(message)
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
