"""Web Novel Editor main window (Phase 02B compact desktop).

Layout (Master Plan §7.1): four numbered control groups on the left — 1. Sources,
2. Novel & Editing, 3. Output, 4. Run — and a large, horizontally resizable Activity pane on
the right with Summary/Detailed tabs. A bottom status bar holds the persistent Light/Dark
toggle, Preferences & Data and Open Log Folder. No navigation sidebar.

Threading: the worker thread receives an immutable :class:`RunRequest` and only calls
``Activity.emit``; it never touches a widget or calls Tk (not even ``after``). The Tk thread
drains events with :class:`gui.activity.ActivityPump`. Window close during a run requests a
safe-boundary stop and destroys Tk only after the worker has reported completion.

Editing is deterministic and script-only: nothing in this window contacts a model or any
network service.
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.batch_runner import run_batch
from core.input_scanner import natural_order, scan_folder, scan_upload
from core.novel_registry import DEFAULT_NOVEL, NOVEL_INDEX_DIR, available_novels, clean_novel_name, resolve_dispatch
from core.output_plan import plan_outputs, reserve_run_dir
from core.protected_lexicon import load_protected_lexicon
from core.run_lock import StaleLock
from core.run_manifest import find_resumable_run, manifest_path, read_manifest
from gui import appearance as look
from gui.activity import (DEFAULT_LOG_RETENTION, ERROR, INFO, WARNING, Activity, ActivityEvent, ActivityPump,
                          SessionLog, bridge_event, default_log_dir)
from utils import settings as prefs_store
from utils.file_utils import downloads_dir, kebab_case, next_numbered_output_dir, open_in_file_manager
from utils.pace import compute_rate, format_rate

APP_TITLE = "Web Novel Editor"
DEFAULT_OUTPUT_FOLDER = "PDF-Editor-Outputs"
MIN_WIDTH, MIN_HEIGHT = 900, 620
OPEN_WIDTH, OPEN_HEIGHT = 1220, 760
CONTROL_PANE_WIDTH = 520
EDITING_DESCRIPTION = ("Conservative universal editing: extraction artifacts, spacing, punctuation and "
                       "known OCR errors are cleaned; protected names and ambiguous prose stay exactly "
                       "as written. Everything runs on this computer; nothing is sent online.")


@dataclass(frozen=True)
class RunRequest:
    """Everything the worker needs, frozen when Start/Resume is accepted (no Tk objects)."""

    files: tuple[str, ...]
    output_dir: str
    novel: str
    formats: tuple[str, ...]
    write_replacement_log: bool
    write_debug_text: bool
    dry_run: bool
    import_roots: tuple[tuple[str, str], ...] = ()
    resume: bool = False
    retry_failed: bool = False
    recover: bool = False
    previously_completed: int = 0
    started: float = field(default_factory=time.monotonic)


def _job(kind: str, value=None, *, coalesce: str | None = None) -> ActivityEvent:
    return ActivityEvent("batch", kind="job", payload=(kind, value), coalesce_key=coalesce)


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


class WebnovelEditorApp(tk.Tk):
    """The single main application window."""

    def __init__(self, *, log_dir: str | Path | None = None,
                 log_retention: int = DEFAULT_LOG_RETENTION) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        width = min(OPEN_WIDTH, max(MIN_WIDTH, self.winfo_screenwidth() - 80))
        height = min(OPEN_HEIGHT, max(MIN_HEIGHT, self.winfo_screenheight() - 90))
        self.geometry(f"{width}x{height}")

        self.preferences, preference_notes = prefs_store.load_preferences()
        self.bundle = look.apply_appearance(self, self.preferences["appearance"])
        self.configure(background=self.bundle["colors"]["window"])
        self.log_dir = Path(log_dir) if log_dir is not None else default_log_dir()
        self.log_retention = log_retention

        # Queue state (Tk thread only).
        self.file_paths: list[str] = []
        self.import_roots: dict[str, str] = {}
        self._display_paths: tuple[str, ...] = ()
        # Run state.
        self._running = False
        self._exit_when_done = False
        self._request: RunRequest | None = None
        self._last_run_dir: str | None = None
        self._last_run_has_failures = False
        self.pause_gate = threading.Event()
        self.pause_gate.set()
        self.stop_event = threading.Event()
        self._counts = {"completed": 0, "failed": 0, "skipped": 0}
        self._elapsed_job = None
        self._batch_started: float | None = None
        self._batch_total = 0
        self._preferences_dialog = None
        self._term_counts: dict[str, int] = {}
        self._preference_save_warned = False

        self._build_ui()
        self.activity = Activity(session_log=SessionLog(self.log_dir, keep=log_retention),
                                 on_render=self._render, job_sink=self._on_job)
        self.pump = ActivityPump(self.activity, self.after, self.after_cancel, lambda: self._running)
        if not self.activity.session_log.open():
            self.activity.note_log_open_failure()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_status()
        self._report("Ready. Add PDF/TXT files or a folder, choose the novel and outputs, then Start. "
                     "Nothing is sent online.", tone="muted", summary=True)
        for note in preference_notes:
            self._report(note, WARNING)
        if self.activity.session_log.pruned:
            self._report(f"Removed {len(self.activity.session_log.pruned)} old session log(s) "
                         f"(keeping the latest {log_retention}).", tone="muted")

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        pad = look.METRICS["content_pad"]
        self._build_status_bar()  # packed first so it is never squeezed out at minimum size
        root = ttk.Frame(self, padding=(pad, pad, pad, 0))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, look.METRICS["gap_md"]))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Offline, deterministic cleanup of web-novel chapter PDF/TXT files for "
                               "reading and TTS.", style="Secondary.TLabel").pack(side="left", padx=(12, 0))

        self.paned = ttk.Panedwindow(root, orient="horizontal")
        self.paned.grid(row=1, column=0, sticky="nsew")
        controls = ttk.Frame(self.paned, width=CONTROL_PANE_WIDTH)
        controls.columnconfigure(0, weight=1)
        self.paned.add(controls, weight=0)
        activity = ttk.Frame(self.paned)
        self.paned.add(activity, weight=1)

        self._build_sources(controls, 0)
        self._build_novel(controls, 1)
        self._build_output(controls, 2)
        self._build_run(controls, 3)
        controls.rowconfigure(0, weight=1)  # the source list takes spare height
        self._build_activity(activity)
        self._repaint_raw_widgets()

    def _group(self, parent, row: int, title: str) -> ttk.Labelframe:
        frame = ttk.Labelframe(parent, text=title)
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, look.METRICS["section_gap"]),
                   padx=(0, look.METRICS["gap_md"]))
        frame.columnconfigure(0, weight=1)
        return frame

    def _build_sources(self, parent, row: int) -> None:
        frame = self._group(parent, row, "1. Sources")
        frame.rowconfigure(0, weight=1)
        wrap = ttk.Frame(frame)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self.file_listbox = tk.Listbox(wrap, selectmode=tk.EXTENDED, height=6, activestyle="dotbox",
                                       exportselection=False, relief="solid", borderwidth=1,
                                       highlightthickness=1, font=self.bundle["fonts"]["body"])
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.file_listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.file_listbox.configure(yscrollcommand=scroll.set)

        info = ttk.Frame(frame)
        info.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        info.columnconfigure(0, weight=1)
        self.count_var = tk.StringVar(value="No files queued")
        ttk.Label(info, textvariable=self.count_var, style="Secondary.TLabel").grid(row=0, column=0, sticky="w")
        self.recursive_var = tk.BooleanVar(value=self.preferences["include_subfolders"])
        ttk.Checkbutton(info, text="Include subfolders", variable=self.recursive_var,
                        command=self._on_recursive_changed).grid(row=0, column=1, sticky="e")

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.add_button = ttk.Button(buttons, text="Add Files…", command=self._add_files)
        self.add_folder_button = ttk.Button(buttons, text="Add Folder…", command=self._choose_input_folder)
        self.up_button = ttk.Button(buttons, text="Move Up", command=lambda: self._move_selected(-1))
        self.down_button = ttk.Button(buttons, text="Move Down", command=lambda: self._move_selected(1))
        self.remove_button = ttk.Button(buttons, text="Remove", command=self._remove_selected)
        self.clear_button = ttk.Button(buttons, text="Clear All", command=self._clear_all)
        for column, button in enumerate((self.add_button, self.add_folder_button, self.up_button,
                                         self.down_button, self.remove_button, self.clear_button)):
            button.grid(row=0, column=column, padx=(0 if column == 0 else 4, 0))

    def _build_novel(self, parent, row: int) -> None:
        frame = self._group(parent, row, "2. Novel & Editing")
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Novel:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        roster = available_novels()
        self.novel_var = tk.StringVar(value=self._roster_label(roster, self.preferences["novel"]))
        self.novel_combo = ttk.Combobox(frame, textvariable=self.novel_var, values=roster, state="readonly",
                                        width=max((len(r) for r in roster), default=20) + 2)
        self.novel_combo.grid(row=0, column=1, sticky="w")
        self.novel_combo.bind("<<ComboboxSelected>>", self._on_novel_changed)
        self.terms_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.terms_var, style="Secondary.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Label(frame, text=EDITING_DESCRIPTION, style="Secondary.TLabel", wraplength=CONTROL_PANE_WIDTH - 40,
                  justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._update_term_count()

    def _build_output(self, parent, row: int) -> None:
        frame = self._group(parent, row, "3. Output")
        frame.columnconfigure(0, weight=0)
        frame.columnconfigure(1, weight=1)
        formats = set(self.preferences["output_formats"])
        self.opt_pdf = tk.BooleanVar(value="pdf" in formats)
        self.opt_txt = tk.BooleanVar(value="txt" in formats)
        ttk.Label(frame, text="Formats:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        fmt = ttk.Frame(frame)
        fmt.grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(fmt, text="PDF", variable=self.opt_pdf, command=self._on_formats_changed).pack(side="left")
        ttk.Checkbutton(fmt, text="TXT", variable=self.opt_txt,
                        command=self._on_formats_changed).pack(side="left", padx=(12, 0))
        ttk.Label(frame, text="Saving to:").grid(row=1, column=0, sticky="nw", padx=(0, 6), pady=(2, 0))
        self.output_root_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.output_root_var, wraplength=CONTROL_PANE_WIDTH - 120,
                  justify="left").grid(row=1, column=1, sticky="w", pady=(2, 0))
        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(actions, text="Open Output Folder", command=self.open_output_folder).pack(side="left")
        ttk.Button(actions, text="Change in Preferences…", command=self.open_preferences).pack(
            side="left", padx=(4, 0))
        self.opt_replacement_log = tk.BooleanVar(value=False)
        self.opt_debug_text = tk.BooleanVar(value=False)
        self.opt_dry_run = tk.BooleanVar(value=False)
        extra = ttk.Frame(frame)
        extra.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(extra, text="Edit audit (JSONL)", variable=self.opt_replacement_log).pack(side="left")
        ttk.Checkbutton(extra, text="Debug full text", variable=self.opt_debug_text).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(extra, text="Dry run (no files)", variable=self.opt_dry_run).pack(side="left", padx=(10, 0))
        self._update_output_label()

    def _build_run(self, parent, row: int) -> None:
        frame = self._group(parent, row, "4. Run")
        controls = ttk.Frame(frame)
        controls.grid(row=0, column=0, sticky="ew")
        self.run_button = ttk.Button(controls, text="Start", style="Primary.TButton", command=self._start_batch)
        self.run_button.pack(side="left")
        self.pause_button = ttk.Button(controls, text="Pause", command=self._toggle_pause, state=tk.DISABLED)
        self.pause_button.pack(side="left", padx=(4, 0))
        self.stop_button = ttk.Button(controls, text="Stop", command=self._request_stop, state=tk.DISABLED)
        self.stop_button.pack(side="left", padx=(4, 0))
        ttk.Separator(controls, orient="vertical").pack(side="left", fill="y", padx=8)
        self.resume_button = ttk.Button(controls, text="Resume Run…", command=self._resume_run)
        self.resume_button.pack(side="left")
        self.resume_recent_button = ttk.Button(controls, text="Resume Recent", command=self._resume_recent)
        self.resume_recent_button.pack(side="left", padx=(4, 0))
        self.retry_button = ttk.Button(controls, text="Retry Failed", command=self._retry_failed)
        self.retry_button.pack(side="left", padx=(4, 0))
        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 2))
        stats = ttk.Frame(frame)
        stats.grid(row=2, column=0, sticky="ew")
        stats.columnconfigure(0, weight=1)
        self.counts_var = tk.StringVar(value="Completed 0 · Failed 0 · Skipped 0")
        ttk.Label(stats, textvariable=self.counts_var).grid(row=0, column=0, sticky="w")
        self.elapsed_var = tk.StringVar(value="Elapsed 0:00")
        ttk.Label(stats, textvariable=self.elapsed_var, style="Secondary.TLabel").grid(row=0, column=1, sticky="e")
        self.rate_var = tk.StringVar(value="")
        ttk.Label(stats, textvariable=self.rate_var, style="Secondary.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w")

    def _build_activity(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", padx=(look.METRICS["gap_md"], 0))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="Activity", style="Value.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="Clear Log", command=self.clear_log).grid(row=0, column=1, sticky="e")
        self.activity_tabs = ttk.Notebook(parent)
        self.activity_tabs.grid(row=1, column=0, sticky="nsew", padx=(look.METRICS["gap_md"], 0),
                                pady=(4, look.METRICS["section_gap"]))
        self.summary_text = self._activity_text("Summary")
        self.detailed_text = self._activity_text("Detailed")

    def _activity_text(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.activity_tabs)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        text = tk.Text(frame, wrap="word", state=tk.DISABLED, width=60, height=20, relief="flat",
                       borderwidth=0, highlightthickness=0, padx=6, pady=4, font=self.bundle["fonts"]["mono"],
                       undo=False)
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        self.activity_tabs.add(frame, text=title)
        return text

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="Status.TFrame", padding=look.METRICS["status_pad"])
        bar.pack(fill="x", side="bottom")
        bar.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        self.dark_var = tk.BooleanVar(value=self.bundle["appearance"] == look.DARK)
        self.theme_toggle = ttk.Checkbutton(bar, text="Dark mode", variable=self.dark_var,
                                            command=self.toggle_appearance, style="Toolbutton")
        self.theme_toggle.grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bar, text="Preferences & Data…", style="Toolbutton",
                   command=self.open_preferences).grid(row=0, column=2, padx=(4, 0))
        ttk.Button(bar, text="Open Log Folder", style="Toolbutton",
                   command=self.open_log_folder).grid(row=0, column=3, padx=(4, 0))

    # ------------------------------------------------------------------ appearance
    def _repaint_raw_widgets(self) -> None:
        bundle = self.bundle
        c = bundle["colors"]
        self.configure(background=c["window"])
        look.style_tk_widget(self.file_listbox, bundle, "field")
        for text in (getattr(self, "summary_text", None), getattr(self, "detailed_text", None)):
            if text is None:
                continue
            look.style_tk_widget(text, bundle, "log")
            text.tag_configure("success", foreground=c["success"])
            text.tag_configure("accent", foreground=c["accent"])
            text.tag_configure("muted", foreground=c["secondary"])
            text.tag_configure(WARNING, foreground=c["warning"])
            text.tag_configure(ERROR, foreground=c["danger"])
        look.style_combobox_popdown(self.novel_combo, bundle)

    def toggle_appearance(self) -> None:
        self.set_appearance(look.DARK if self.dark_var.get() else look.LIGHT)

    def set_appearance(self, value: str) -> None:
        self.bundle = look.apply_appearance(self, value)
        self.dark_var.set(self.bundle["appearance"] == look.DARK)
        self._repaint_raw_widgets()
        if self._preferences_dialog is not None:
            self._preferences_dialog.apply_appearance(self.bundle)
        self._save_preference(appearance=self.bundle["appearance"])

    # ------------------------------------------------------------------ preferences
    def _save_preference(self, **values) -> bool:
        self.preferences.update(values)
        try:
            prefs_store.save_preferences(values)
            return True
        except (OSError, ValueError) as exc:
            if not self._preference_save_warned:
                self._preference_save_warned = True
                self._report(f"Preferences could not be saved ({type(exc).__name__}); your choice applies to "
                             "this session only.", WARNING)
            return False

    def default_output_root(self) -> Path:
        return downloads_dir() / DEFAULT_OUTPUT_FOLDER

    def output_root(self) -> Path:
        custom = self.preferences.get("output_root")
        return Path(custom) if custom else self.default_output_root()

    def set_output_root(self, value: str | None) -> None:
        if value is not None and not Path(value).is_absolute():
            raise ValueError("The output folder must be a full path")
        self.preferences["output_root"] = value
        prefs_store.save_preferences({"output_root": value})
        self._update_output_label()
        self._refresh_status()
        self._report(f"Output folder for new runs: {self.output_root()}", tone="muted", summary=True)

    def reset_preferences(self) -> None:
        prefs_store.reset_preferences()
        defaults, _notes = prefs_store.load_preferences()
        self.preferences = defaults
        self.recursive_var.set(defaults["include_subfolders"])
        self.opt_pdf.set("pdf" in defaults["output_formats"])
        self.opt_txt.set("txt" in defaults["output_formats"])
        self.novel_var.set(self._roster_label(list(self.novel_combo.cget("values")), defaults["novel"]))
        self._update_term_count()
        self.bundle = look.apply_appearance(self, defaults["appearance"])
        self.dark_var.set(self.bundle["appearance"] == look.DARK)
        self._repaint_raw_widgets()
        if self._preferences_dialog is not None:
            self._preferences_dialog.apply_appearance(self.bundle)
        self._update_output_label()
        self._refresh_status()
        self._report("Preferences were reset to their defaults.", summary=True)

    def open_preferences(self) -> None:
        from gui.preferences import PreferencesDialog
        if self._preferences_dialog is not None and self._preferences_dialog.winfo_exists():
            self._preferences_dialog.lift()
            self._preferences_dialog.focus_set()
            return
        self._preferences_dialog = PreferencesDialog(self)

    def preferences_closed(self, dialog) -> None:
        if self._preferences_dialog is dialog:
            self._preferences_dialog = None

    def _on_recursive_changed(self) -> None:
        self._save_preference(include_subfolders=bool(self.recursive_var.get()))

    def _selected_formats(self) -> tuple[str, ...]:
        return tuple(fmt for fmt, var in (("pdf", self.opt_pdf), ("txt", self.opt_txt)) if var.get())

    def _on_formats_changed(self) -> None:
        formats = self._selected_formats()
        if formats:
            self._save_preference(output_formats=list(formats))
        self._refresh_status()

    @staticmethod
    def _roster_label(roster: list[str], saved: str) -> str:
        for label in roster:
            if label == saved or clean_novel_name(label) == saved:
                return label
        return DEFAULT_NOVEL if DEFAULT_NOVEL in roster else (roster[0] if roster else "")

    def _on_novel_changed(self, _event=None) -> None:
        novel = clean_novel_name(self.novel_var.get())
        self._update_term_count()
        self._save_preference(novel=novel)
        self._report(f"Novel selected: {novel}", tone="muted")
        self._refresh_status()

    def _update_term_count(self) -> None:
        novel = clean_novel_name(self.novel_var.get())
        if novel not in self._term_counts:
            try:
                dispatch = resolve_dispatch(novel)
                index = str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
                self._term_counts[novel] = len(load_protected_lexicon(index, dispatch.canonical_names).terms)
            except Exception:  # noqa: BLE001 - informational only; the run reports real errors
                self._term_counts[novel] = -1
        count = self._term_counts[novel]
        self.terms_var.set("Protected-term list unavailable" if count < 0 else
                           f"{count:,} protected term(s) kept exactly as written" if count else
                           "No protected terms for this selection (universal rules only)")

    def _update_output_label(self) -> None:
        kind = "custom folder" if self.preferences.get("output_root") else "default"
        self.output_root_var.set(f"{self.output_root()}  ({kind})")

    # ------------------------------------------------------------------ shortcuts
    def _bind_shortcuts(self) -> None:
        mod = "Command" if self.tk.call("tk", "windowingsystem") == "aqua" else "Control"
        box = self.file_listbox
        box.bind(f"<{mod}-a>", self._select_all_sources)
        box.bind(f"<{mod}-A>", self._select_all_sources)
        for key in ("<Delete>", "<BackSpace>"):
            box.bind(key, lambda _e: (self._remove_selected(), "break")[1])
        box.bind("<Alt-Up>", lambda _e: (self._move_selected(-1), "break")[1])
        box.bind("<Alt-Down>", lambda _e: (self._move_selected(1), "break")[1])
        for text in (self.summary_text, self.detailed_text):
            text.bind(f"<{mod}-a>", lambda e: (e.widget.tag_add("sel", "1.0", "end-1c"), "break")[1])
            # A disabled Text still allows selection and copy; keep focus possible for Ctrl+C.
            text.bind("<Button-1>", lambda e: e.widget.focus_set())
        self.bind(f"<{mod}-o>", lambda _e: self._add_files())

    def _select_all_sources(self, _event=None):
        self.file_listbox.selection_set(0, tk.END)
        return "break"

    # ------------------------------------------------------------------ activity
    def _report(self, message: str, severity: str = INFO, *, tone: str | None = None,
                summary: bool | None = None) -> None:
        if summary is None:
            summary = severity != INFO or tone in ("success", "accent")
        self.activity.report(ActivityEvent("app", message, severity, summary=summary, tone=tone))

    def _render(self, update) -> None:
        if update.cleared:
            for text in (self.summary_text, self.detailed_text):
                text.configure(state=tk.NORMAL)
                text.delete("1.0", tk.END)
                text.configure(state=tk.DISABLED)
        for text, lines in ((self.summary_text, update.summary), (self.detailed_text, update.detailed)):
            if not lines:
                continue
            at_bottom = text.yview()[1] >= 0.999
            text.configure(state=tk.NORMAL)
            for line in lines:
                tag = line.tone or (line.severity if line.severity != INFO else "")
                text.insert(tk.END, line.text + "\n", (tag,) if tag else ())
            excess = int(text.index("end-1c").split(".")[0]) - 1 - self.activity.model.line_cap
            if excess > 0:
                text.delete("1.0", f"{excess + 1}.0")
            text.configure(state=tk.DISABLED)
            if at_bottom:
                text.see(tk.END)

    def clear_log(self) -> None:
        """Clear the displayed views only; session log files and run state are untouched."""
        self.activity.clear_display()

    def open_log_folder(self) -> None:
        path = self.activity.session_log.path.parent if self.activity.session_log.path else self.log_dir
        if not open_in_file_manager(path):
            self._report(f"Could not open the log folder automatically. It is here: {path}", WARNING)

    def open_output_folder(self) -> None:
        target = Path(self._last_run_dir) if self._last_run_dir and Path(self._last_run_dir).is_dir() \
            else self.output_root()
        if not target.is_dir():
            messagebox.showinfo("Output folder", f"The output folder will be created when the first run "
                                                 f"starts:\n{target}")
            return
        if not open_in_file_manager(target):
            self._report(f"Could not open the output folder automatically. It is here: {target}", WARNING)

    def _on_job(self, event: ActivityEvent) -> None:
        kind, value = event.payload
        if kind == "progress":
            self._set_progress(value)
        elif kind == "item":
            self._counts[value] = self._counts.get(value, 0) + 1
            self._update_counts()
        elif kind == "done":
            self._on_done(value)
        elif kind == "error":
            self._on_error(value)
        elif kind == "stale":
            self._confirm_stale_recovery()

    # ------------------------------------------------------------------ queue
    def _choose_input_folder(self) -> None:
        directory = filedialog.askdirectory(title="Add a folder of PDF/TXT files to the queue")
        if directory:
            self._apply_input_folder(directory)

    def _apply_input_folder(self, directory: str) -> None:
        exclude = self._request.output_dir if self._running and self._request else self.output_root()
        warnings: list[str] = []
        try:
            found = scan_folder(directory, recursive=self.recursive_var.get(), exclude=exclude,
                                warn=warnings.append)
        except (ValueError, NotADirectoryError, OSError) as exc:
            self._report(f"Could not scan folder: {exc}", ERROR)
            return
        for message in warnings:
            self._report(message, WARNING)
        existing = {os.path.normcase(str(Path(p).resolve())) for p in self.file_paths}
        added = 0
        for path in found:
            key = os.path.normcase(str(path.resolve()))
            if key not in existing:
                self.file_paths.append(str(path))
                self.import_roots[str(path)] = directory
                existing.add(key)
                added += 1
        self._refresh_file_list()
        self._report(f"Added folder {directory}: {added} PDF/TXT file(s) in natural order"
                     + ("" if self.recursive_var.get() else " (subfolders not included)") + ".", summary=True)
        if not found:
            self._report("No PDF/TXT files were found in that folder.", WARNING)
        self._refresh_status()

    def _add_files(self) -> None:
        chosen = filedialog.askopenfilenames(title="Select PDF/TXT files",
                                             filetypes=[("PDF / TXT files", "*.pdf *.txt")])
        try:
            paths = natural_order(scan_upload(chosen))
        except (OSError, ValueError) as exc:
            self._report(f"Could not add files: {exc}", ERROR)
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
            self._report(f"Added {added} file(s).", summary=True)
        self._refresh_status()

    def _refresh_file_list(self) -> None:
        """Rebuild the visible queue while retaining surviving selections, focus and scroll."""
        previous = self._display_paths
        selected = {previous[i] for i in self.file_listbox.curselection() if i < len(previous)}
        active = self.file_listbox.index(tk.ACTIVE)
        focused = previous[active] if active < len(previous) else None
        top = self.file_listbox.yview()[0]
        self.file_listbox.delete(0, tk.END)
        for index, path in enumerate(self.file_paths):
            imported = self.import_roots.get(path)
            label = Path(path).relative_to(Path(imported).parent).as_posix() if imported else Path(path).name
            self.file_listbox.insert(tk.END, label)
            if path in selected:
                self.file_listbox.selection_set(index)
            if path == focused:
                self.file_listbox.activate(index)
        self.file_listbox.yview_moveto(top)
        self._display_paths = tuple(self.file_paths)
        count = len(self.file_paths)
        self.count_var.set("No files queued" if not count else f"{count} file(s) queued")
        self._refresh_status()

    def _remove_selected(self) -> None:
        selection = list(self.file_listbox.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self.import_roots.pop(self.file_paths.pop(index), None)
        self._refresh_file_list()
        self._report(f"Removed {len(selection)} file(s).", tone="muted")
        self._refresh_status()

    def _clear_all(self) -> None:
        if not self.file_paths:
            return
        count = len(self.file_paths)
        self.file_paths.clear()
        self.import_roots.clear()
        self._refresh_file_list()
        self._report(f"Cleared {count} file(s) from the queue.", tone="muted")
        self._refresh_status()

    def _move_selected(self, direction: int) -> None:
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
        self.file_listbox.selection_clear(0, tk.END)
        for index in sorted(selected):
            self.file_listbox.selection_set(index)
        self.file_listbox.activate(active)
        if selected:
            self.file_listbox.see(active)

    # ------------------------------------------------------------------ run control
    def _resume_recent(self) -> None:
        if self._running:
            return
        offer = find_resumable_run(self.output_root())
        if offer.available:
            self._resume_run(directory=offer.output_dir)
        else:
            messagebox.showinfo("Resume Run", offer.reason)

    def _retry_failed(self) -> None:
        if self._running:
            return
        if self._last_run_dir and self._last_run_has_failures:
            self._resume_run(retry_failed=True, directory=self._last_run_dir)
        else:
            self._resume_run(retry_failed=True)

    def _resume_run(self, *, retry_failed: bool = False, directory: str | None = None,
                    recover: bool = False) -> None:
        if self._running:
            return
        directory = directory or filedialog.askdirectory(title="Select the original run folder")
        if not directory:
            return
        try:
            saved = read_manifest(manifest_path(directory))
        except Exception as exc:  # noqa: BLE001 - every refusal is shown, nothing is allocated
            self._report(f"Resume refused for {directory}: {exc}", ERROR)
            messagebox.showerror("Resume refused", str(exc))
            return
        options = saved["run"]["options"]
        completed = sum(e["status"] == "completed" for e in saved["entries"])
        request = RunRequest(files=tuple(saved["queue"]), output_dir=saved["output_dir"],
                             novel=saved["run"]["novel"], formats=tuple(options["formats"]),
                             write_replacement_log=options["write_replacement_log"],
                             write_debug_text=options["write_debug_text"], dry_run=False, resume=True,
                             retry_failed=retry_failed, recover=recover, previously_completed=completed)
        self._begin(request)

    def _start_batch(self) -> None:
        if self._running:
            return
        files = tuple(self.file_paths)
        if not files:
            messagebox.showwarning("No files", "Add PDF/TXT files or a folder before starting.")
            return
        formats = self._selected_formats()
        if not formats:
            messagebox.showwarning("No output format", "Select PDF, TXT, or both before starting.")
            return
        novel = clean_novel_name(self.novel_var.get())
        name = kebab_case(novel) or "output"
        root = self.output_root()
        dry = bool(self.opt_dry_run.get())
        try:
            proposed = next_numbered_output_dir(root, name)
            plan_outputs(files, proposed, formats=formats, import_roots=self.import_roots,
                         debug=self.opt_debug_text.get(), audit=self.opt_replacement_log.get())
            output_dir = str(proposed if dry else reserve_run_dir(root, name))
        except (OSError, ValueError) as exc:
            self._report(f"Output allocation failed: {exc}", ERROR)
            messagebox.showerror("Output allocation failed", str(exc))
            return
        request = RunRequest(files=files, output_dir=output_dir, novel=novel, formats=formats,
                             write_replacement_log=bool(self.opt_replacement_log.get()),
                             write_debug_text=bool(self.opt_debug_text.get()), dry_run=dry,
                             import_roots=tuple((k, v) for k, v in self.import_roots.items() if k in files))
        self._begin(request)

    def _begin(self, request: RunRequest) -> None:
        """Commit to one run: freeze the request, arm the controls and start the worker."""
        self._request = request
        self._running = True
        self._counts = {"completed": 0, "failed": 0, "skipped": 0}
        self._update_counts()
        self.pause_gate.set()
        self.stop_event.clear()
        self._set_run_controls(running=True)
        self.progress.configure(maximum=max(1, len(request.files)), value=0)
        self._begin_rate_tracking(len(request.files))
        label = ("Retry Failed" if request.retry_failed else "Resume" if request.resume
                 else "Dry run" if request.dry_run else "Run")
        self.activity.report(ActivityEvent("app", f"──── {label} started {time.strftime('%H:%M:%S')} ────",
                                           kind="separator"))
        self._report(f"{label}: {len(request.files)} file(s), novel {request.novel or 'Universal'}, "
                     f"formats {', '.join(f.upper() for f in request.formats)}.", tone="accent")
        self._report(f"Destination: {request.output_dir}" + (" (dry run: nothing is written)"
                                                             if request.dry_run else ""), summary=True)
        if request.previously_completed:
            self._report(f"{request.previously_completed} item(s) were already completed and will be "
                         "verified, not reprocessed.", summary=True)
        self.pump.start()
        self._tick_elapsed()
        threading.Thread(target=self._process_worker, args=(request,), daemon=True).start()

    def _process_worker(self, request: RunRequest) -> None:
        """Worker thread: emits events only. Never touches Tk."""
        emit = self.activity.emit
        try:
            summary = run_batch(
                request.files, request.output_dir,
                write_replacement_log=request.write_replacement_log,
                write_debug_text=request.write_debug_text,
                dry_run=request.dry_run, novel_name=request.novel,
                output_formats=request.formats, import_roots=dict(request.import_roots),
                resume=request.resume, retry_failed=request.retry_failed, recover_stale=request.recover,
                pause_gate=self.pause_gate, stop_event=self.stop_event,
                gui_log=lambda message, level="info": emit(bridge_event(message, level)),
                progress=lambda value: emit(_job("progress", value, coalesce="progress")),
                item_result=lambda _source, outcome: emit(_job("item", outcome)),
            )
        except StaleLock:
            emit(_job("stale"))
            return
        except Exception as exc:  # noqa: BLE001 - reported on the Tk thread; the UI stays responsive
            emit(_job("error", f"{type(exc).__name__}: {exc}"))
            return
        emit(_job("done", summary))

    def _set_run_controls(self, *, running: bool) -> None:
        idle = tk.DISABLED if running else tk.NORMAL
        busy = tk.NORMAL if running else tk.DISABLED
        for button in (self.run_button, self.resume_button, self.resume_recent_button, self.retry_button):
            button.configure(state=idle)
        self.pause_button.configure(state=busy, text="Pause")
        self.stop_button.configure(state=busy)

    def _finish_run_ui(self) -> None:
        self._running = False
        self.pause_gate.set()
        self.stop_event.clear()
        self._set_run_controls(running=False)
        self._end_rate_tracking()
        if self._elapsed_job is not None:
            try:
                self.after_cancel(self._elapsed_job)
            except tk.TclError:
                pass
            self._elapsed_job = None
        self._refresh_status()

    def _confirm_stale_recovery(self) -> None:
        request = self._request
        self._finish_run_ui()
        if self._exit_when_done:
            self._shutdown()
            return
        self._report("The run folder has a stale ownership record; recovery needs confirmation.", WARNING)
        if request and messagebox.askyesno(
                "Recover stale run?", "The former owner is proven exited or its process identity differs. "
                "Preserve its ownership record and recover this run?"):
            self._resume_run(directory=request.output_dir, retry_failed=request.retry_failed, recover=True)

    def _on_close(self) -> None:
        if not self._running:
            self._shutdown()
        elif messagebox.askyesno("Stop and exit?", "Finish the current file safely, save the checkpoint, "
                                                   "then exit?"):
            self._exit_when_done = True
            self._request_stop()

    def _shutdown(self) -> None:
        self.pump.stop()
        self.activity.close()
        self.destroy()

    def _toggle_pause(self) -> None:
        """Pause ⇄ Continue at a file boundary; the current file always finishes first."""
        if not self._running:
            return
        if self.pause_gate.is_set():
            self.pause_gate.clear()
            self.pause_button.configure(text="Continue")
            self._report("Pause requested — the current file will finish first.", WARNING)
        else:
            self.pause_gate.set()
            self.pause_button.configure(text="Pause")
            self._report("Continue requested.", tone="accent")

    def _request_stop(self) -> None:
        """Stop after the in-flight file; also releases a paused worker."""
        if not self._running:
            return
        self.stop_event.set()
        self.pause_gate.set()
        self.pause_button.configure(text="Pause", state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self._report("Stop requested — the current file will finish first.", WARNING)

    def _on_done(self, summary: dict) -> None:
        request = self._request
        self._finish_run_ui()
        self._last_run_dir = summary.get("output_dir")
        self._last_run_has_failures = bool(summary.get("finished_with_errors"))
        if "completed_total" in summary:
            self._report(f"Run totals: completed {summary['completed_total']}, failed/incomplete "
                         f"{summary.get('failed_total', 0)}, skipped {summary.get('skipped_total', 0)}, pending "
                         f"{summary.get('pending_total', 0)}. Elapsed "
                         f"{format_elapsed(time.monotonic() - request.started)}.", summary=True,
                         tone=None if summary.get("finished_with_errors") else "success")
        if self._exit_when_done:
            self._shutdown()
            return
        if summary.get("outputs"):
            if open_in_file_manager(summary["output_dir"]):
                self._report(f"Opened output folder: {summary['output_dir']}", tone="muted")
            else:
                self._report(f"Could not open the output folder automatically. It is here: "
                             f"{summary['output_dir']}", WARNING)
        title = ("Run stopped" if summary.get("stopped") else "Finished with errors"
                 if summary.get("finished_with_errors") else "Run incomplete"
                 if summary.get("run_complete") is False else "Run complete")
        messagebox.showinfo(title, f"Processed {summary['total']} file(s).\n"
                                   f"Completed: {summary.get('completed_total', summary.get('succeeded', 0))}   "
                                   f"Failed: {summary.get('failed_total', summary.get('failed', 0))}   "
                                   f"Skipped: {summary.get('skipped_total', summary.get('skipped', 0))}\n"
                                   f"Output folder: {summary['output_dir']}")

    def _on_error(self, message: str) -> None:
        self._finish_run_ui()
        self._report(f"Run stopped: {message}", ERROR)
        if self._exit_when_done:
            self._shutdown()
            return
        messagebox.showerror("Run error", message)

    # ------------------------------------------------------------------ progress
    def _update_counts(self) -> None:
        c = self._counts
        self.counts_var.set(f"Completed {c['completed']} · Failed {c['failed']} · Skipped {c['skipped']}")

    def _tick_elapsed(self) -> None:
        if not self._running or self._request is None:
            self._elapsed_job = None
            return
        self.elapsed_var.set("Elapsed " + format_elapsed(time.monotonic() - self._request.started))
        self._elapsed_job = self.after(1000, self._tick_elapsed)

    def _begin_rate_tracking(self, total: int) -> None:
        self._batch_total = max(0, int(total))
        self._batch_started = time.monotonic()
        self.rate_var.set("")

    def _end_rate_tracking(self) -> None:
        self._batch_started = None

    def _update_rate(self, completed: int) -> None:
        started = self._batch_started
        if started is None or not self._batch_total:
            return
        self.rate_var.set(format_rate(compute_rate(completed, self._batch_total, time.monotonic() - started)))

    def _set_progress(self, value: int) -> None:
        self.progress.configure(value=value)
        self._update_rate(value)

    def _refresh_status(self) -> None:
        if not hasattr(self, "status_var"):
            return
        novel = clean_novel_name(self.novel_var.get()) if hasattr(self, "novel_var") else "—"
        formats = "+".join(f.upper() for f in self._selected_formats()) if hasattr(self, "opt_pdf") else ""
        state = "Running" if self._running else "Ready"
        self.status_var.set(f"{state} · {len(self.file_paths)} file(s) queued · {novel} · "
                            f"{formats or 'no format selected'} → {self.output_root().name}/"
                            f"{kebab_case(novel) or 'output'}-N")


def launch() -> None:
    """Create and run the main application window."""
    app = WebnovelEditorApp()
    app.mainloop()
