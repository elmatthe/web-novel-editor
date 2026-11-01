"""Preferences & Data: output destination, session-log location/retention and reset.

Adapted (Phase 02B) from the author's Audiobook Creation Tool ``shared/preferences_ui.py`` at
``62b0c09543fc5e2a8e6eca18262816e244ca1006``: one themed modal, an Output card with a
default/custom choice plus Browse/Save feedback, a Reset Preferences card, a status line and
Close, with injectable dialog functions so tests never drive native dialogs. Not adopted:
downloaded-model/asset cleanup and its helper processes (this editor has no such data).

The dialog never edits ``config.toml``. Changes affect new runs only; Resume always uses a
run's original folder. Reset removes only the per-user ``settings.json``.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui import appearance as look

DIALOG_TITLE = "Preferences & Data"


class PreferencesDialog(tk.Toplevel):
    def __init__(self, app, *, ask_directory=None, confirm=None) -> None:
        super().__init__(app)
        self.app = app
        self._ask_directory = ask_directory or (lambda **kw: filedialog.askdirectory(parent=self, **kw))
        self._confirm = confirm or (lambda title, message: messagebox.askyesno(title, message, parent=self))
        self.title(DIALOG_TITLE)
        self.transient(app)
        self.resizable(True, False)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        custom = app.preferences.get("output_root")
        self.var_mode = tk.StringVar(value="custom" if custom else "default")
        self.var_custom = tk.StringVar(value=custom or "")
        self.var_status = tk.StringVar(value="")
        self.status_kind = ""
        self._build()
        self.apply_appearance(app.bundle)
        self._on_mode_change()

    # -- layout ---------------------------------------------------------------------------
    def _build(self) -> None:
        pad = look.METRICS["content_pad"]
        outer = ttk.Frame(self, padding=pad + 4)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        ttk.Label(outer, text=DIALOG_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="Saved to your per-user settings. config.toml is never modified.",
                  style="Secondary.TLabel").grid(row=1, column=0, sticky="w", pady=(0, pad))

        output = ttk.Labelframe(outer, text="Output folder")
        output.grid(row=2, column=0, sticky="ew")
        output.columnconfigure(1, weight=1)
        default = self.app.default_output_root()
        ttk.Radiobutton(output, text=f"Default: {default}", variable=self.var_mode, value="default",
                        command=self._on_mode_change).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(output, text="Custom folder:", variable=self.var_mode, value="custom",
                        command=self._on_mode_change).grid(row=1, column=0, sticky="w")
        self.entry_custom = ttk.Entry(output, textvariable=self.var_custom, width=48)
        self.entry_custom.grid(row=1, column=1, sticky="ew", padx=(4, 4))
        self.button_browse = ttk.Button(output, text="Browse…", command=self.browse)
        self.button_browse.grid(row=1, column=2, sticky="e")
        ttk.Label(output, text="Numbered run folders (for example universal-1) are created directly inside "
                               "the chosen folder. Changes apply to new runs; Resume always uses a run's "
                               "original folder.", style="Secondary.TLabel", wraplength=520,
                  justify="left").grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.button_save = ttk.Button(output, text="Save", style="Primary.TButton",
                                      command=self.save_output_root)
        self.button_save.grid(row=3, column=2, sticky="e", pady=(4, 0))

        logs = ttk.Labelframe(outer, text="Activity logs")
        logs.grid(row=3, column=0, sticky="ew", pady=(look.METRICS["section_gap"], 0))
        logs.columnconfigure(0, weight=1)
        ttk.Label(logs, text=str(self.app.log_dir), wraplength=520, justify="left").grid(
            row=0, column=0, sticky="w")
        ttk.Button(logs, text="Open Log Folder", command=self.app.open_log_folder).grid(
            row=0, column=1, sticky="e")
        ttk.Label(logs, text=f"Each session writes one diagnostic log (file names, counts, timings and "
                             f"errors; never chapter text). The latest {self.app.log_retention} closed "
                             "session logs are kept and older ones are removed automatically. Clear Log "
                             "only clears the window.", style="Secondary.TLabel", wraplength=520,
                  justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        reset = ttk.Labelframe(outer, text="Reset")
        reset.grid(row=4, column=0, sticky="ew", pady=(look.METRICS["section_gap"], 0))
        reset.columnconfigure(0, weight=1)
        ttk.Label(reset, text="Restores default appearance, novel, formats, subfolder and output "
                              "choices by removing only the saved settings file. Outputs, run "
                              "folders, logs, profiles and the program environment are untouched.",
                  style="Secondary.TLabel", wraplength=420, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Button(reset, text="Reset Preferences…", command=self.reset_preferences).grid(
            row=0, column=1, sticky="e", padx=(8, 0))

        footer = ttk.Frame(outer)
        footer.grid(row=5, column=0, sticky="ew", pady=(pad, 0))
        footer.columnconfigure(0, weight=1)
        self.label_status = ttk.Label(footer, textvariable=self.var_status, wraplength=420, justify="left")
        self.label_status.grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Close", command=self.close).grid(row=0, column=1, sticky="e")

    # -- behavior -------------------------------------------------------------------------
    def _on_mode_change(self) -> None:
        state = tk.NORMAL if self.var_mode.get() == "custom" else tk.DISABLED
        self.entry_custom.configure(state=state)
        self.button_browse.configure(state=state)

    def _set_status(self, message: str, kind: str = "info") -> None:
        self.var_status.set(message)
        colors = self.app.bundle["colors"]
        self.label_status.configure(foreground=colors["danger"] if kind == "error" else colors["success"]
                                    if kind == "ok" else colors["text"])
        self.status_kind = kind

    def browse(self) -> None:
        chosen = self._ask_directory(title="Choose the output folder (numbered runs go directly inside)")
        if chosen:
            self.var_mode.set("custom")
            self._on_mode_change()
            self.var_custom.set(str(Path(chosen)))
            self.save_output_root()

    def save_output_root(self) -> bool:
        if self.var_mode.get() == "default":
            value = None
        else:
            raw = self.var_custom.get().strip()
            path = Path(raw).expanduser() if raw else None
            if path is None or not path.is_absolute():
                self._set_status("Enter a full folder path, or choose one with Browse…", "error")
                return False
            if path.exists() and not path.is_dir():
                self._set_status("That path is a file, not a folder. Choose a folder.", "error")
                return False
            value = str(path)
        try:
            self.app.set_output_root(value)
        except (OSError, ValueError) as exc:
            self._set_status(f"Could not save the output folder: {exc}", "error")
            return False
        self._set_status(f"Saved. New runs go to: {self.app.output_root()}", "ok")
        return True

    def reset_preferences(self) -> bool:
        if not self._confirm("Reset Preferences?",
                             "Remove saved preferences and restore the defaults?\n\nOutputs, run folders, "
                             "logs and the program environment are not affected."):
            return False
        try:
            self.app.reset_preferences()
        except OSError as exc:
            self._set_status(f"Preferences could not be reset: {exc}", "error")
            return False
        self.var_mode.set("default")
        self.var_custom.set("")
        self._on_mode_change()
        self._set_status("Preferences reset to defaults.", "ok")
        return True

    def apply_appearance(self, bundle: dict) -> None:
        if not self.winfo_exists():
            return
        self.configure(background=bundle["colors"]["window"])
        look.native_title_bar(self, bundle["appearance"])

    def close(self) -> None:
        self.app.preferences_closed(self)
        self.destroy()
