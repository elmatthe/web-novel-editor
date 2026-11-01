"""Compact Light/Dark appearance: palettes, named ttk styles and live repaint.

Adapted (Phase 02B) from the author's Audiobook Creation Tool ``shared/appearance.py`` at
``62b0c09543fc5e2a8e6eca18262816e244ca1006``: its LIGHT/DARK palettes, compact metrics,
classic-widget coloring and combobox drop-down coloring. Not adopted: ACT's cloned-element
catalogue (it exists so converted panels can coexist with a ``vista`` base theme). This window
owns every widget and already used ``clam``, which honors custom colors, so the palette is
applied to ``clam`` styles directly. Calling :func:`apply_appearance` again repaints every ttk
widget in place; raw Tk widgets (Listbox/Text/Toplevel) are recolored by their owners through
:func:`style_tk_widget`, so selections, scroll positions, text and progress are preserved.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

LIGHT, DARK = "light", "dark"

LIGHT_COLORS: dict[str, str] = {
    "window": "#f0f0f0", "surface": "#f0f0f0", "elevated": "#fdfdfd", "border": "#c9c9c9",
    "divider": "#d9d9d9", "text": "#1a1a1a", "secondary": "#555555", "disabled": "#6b6b6b",
    "accent": "#1860c0", "accent_hover": "#2f74d0", "accent_pressed": "#134f9e",
    "accent_soft": "#dce8fb", "focus": "#1860c0",
    "success": "#166b2e", "warning": "#744300", "danger": "#b42424",
    "field": "#ffffff", "field_disabled": "#f4f4f4", "field_border": "#adadad",
    "selection": "#1860c0", "selection_text": "#ffffff", "selection_inactive": "#cfe0f7",
    "scroll_trough": "#eeeeee", "scroll_thumb": "#c4c4c4", "scroll_thumb_hover": "#adadad",
    "button": "#fdfdfd", "button_hover": "#e5f1fb", "button_pressed": "#cce4f7",
}

DARK_COLORS: dict[str, str] = {
    "window": "#1e1f22", "surface": "#26282c", "elevated": "#2d2f34", "border": "#3a3c41",
    "divider": "#33353a", "text": "#e7e8ea", "secondary": "#a6a9ae", "disabled": "#767a80",
    "accent": "#5b9bf7", "accent_hover": "#7bacf8", "accent_pressed": "#3f80dd",
    "accent_soft": "#233551", "focus": "#5b9bf7",
    "success": "#57b975", "warning": "#d3a94a", "danger": "#e57a72",
    "field": "#1c1d20", "field_disabled": "#26282c", "field_border": "#44474d",
    "selection": "#3f6fb0", "selection_text": "#ffffff", "selection_inactive": "#33475f",
    "scroll_trough": "#232427", "scroll_thumb": "#42454b", "scroll_thumb_hover": "#54585f",
    "button": "#2d2f34", "button_hover": "#383b41", "button_pressed": "#44474d",
}

PALETTES = {LIGHT: LIGHT_COLORS, DARK: DARK_COLORS}

#: Appearance-independent compact spacing (ACT METRICS subset).
METRICS: dict[str, object] = {
    "gap_sm": 4, "gap_md": 8, "gap_lg": 12, "card_pad": 6, "section_gap": 6,
    "button_pad": (8, 2), "field_pad": (2, 1), "tab_pad": (10, 3), "content_pad": 8,
    "status_pad": (8, 3), "progress_thickness": 8, "scroll_width": 12,
}


def normalize(appearance: str | None) -> str:
    return appearance if appearance in PALETTES else LIGHT


def fonts(root: tk.Misc) -> dict[str, tuple]:
    """Platform UI family at the Tk default size; monospace for the Activity text."""
    import tkinter.font as tkfont
    try:
        default = tkfont.nametofont("TkDefaultFont", root=root).actual()
        family, size = default["family"], abs(int(default["size"])) or 9
    except (tk.TclError, KeyError, ValueError):
        family, size = "TkDefaultFont", 9
    available = {f.lower() for f in tkfont.families(root)}
    mono = next((f for f in ("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")
                 if f.lower() in available), "TkFixedFont")
    return {"body": (family, size), "bold": (family, size, "bold"),
            "title": (family, size + 3, "bold"), "small": (family, max(size - 1, 7)),
            "mono": (mono, size)}


def apply_appearance(root: tk.Misc, appearance: str) -> dict:
    """(Re)configure every style for *appearance*; returns the bundle owners use to repaint."""
    appearance = normalize(appearance)
    c = PALETTES[appearance]
    f = fonts(root)
    style = ttk.Style(root)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    pad = METRICS
    style.configure(".", background=c["window"], foreground=c["text"], font=f["body"],
                    bordercolor=c["border"], darkcolor=c["window"], lightcolor=c["window"],
                    troughcolor=c["scroll_trough"], focuscolor=c["focus"],
                    selectbackground=c["selection"], selectforeground=c["selection_text"],
                    fieldbackground=c["field"], insertcolor=c["text"])
    style.map(".", foreground=[("disabled", c["disabled"])])
    style.configure("TFrame", background=c["window"])
    style.configure("Status.TFrame", background=c["surface"])
    style.configure("TLabel", background=c["window"], foreground=c["text"])
    style.configure("Title.TLabel", font=f["title"])
    style.configure("Secondary.TLabel", foreground=c["secondary"], font=f["small"])
    style.configure("Status.TLabel", background=c["surface"], foreground=c["secondary"], font=f["small"])
    style.configure("Value.TLabel", foreground=c["text"], font=f["bold"])
    style.configure("TLabelframe", background=c["window"], bordercolor=c["border"],
                    lightcolor=c["window"], darkcolor=c["window"], relief="groove", padding=pad["card_pad"])
    style.configure("TLabelframe.Label", background=c["window"], foreground=c["accent"], font=f["bold"])
    style.configure("TButton", background=c["button"], foreground=c["text"], bordercolor=c["field_border"],
                    lightcolor=c["button"], darkcolor=c["button"], padding=pad["button_pad"],
                    focuscolor=c["focus"], anchor="center")
    style.map("TButton", background=[("disabled", c["field_disabled"]), ("pressed", c["button_pressed"]),
                                     ("active", c["button_hover"])],
              lightcolor=[("pressed", c["button_pressed"]), ("active", c["button_hover"])],
              darkcolor=[("pressed", c["button_pressed"]), ("active", c["button_hover"])],
              bordercolor=[("focus", c["focus"])], foreground=[("disabled", c["disabled"])])
    style.configure("Primary.TButton", background=c["accent"], foreground="#ffffff",
                    bordercolor=c["accent_pressed"], lightcolor=c["accent"], darkcolor=c["accent"],
                    font=f["bold"])
    style.map("Primary.TButton",
              background=[("disabled", c["field_disabled"]), ("pressed", c["accent_pressed"]),
                          ("active", c["accent_hover"])],
              lightcolor=[("pressed", c["accent_pressed"]), ("active", c["accent_hover"])],
              darkcolor=[("pressed", c["accent_pressed"]), ("active", c["accent_hover"])],
              foreground=[("disabled", c["disabled"])])
    style.configure("Toolbutton", background=c["surface"], foreground=c["text"], padding=(6, 1),
                    bordercolor=c["surface"], lightcolor=c["surface"], darkcolor=c["surface"])
    style.map("Toolbutton", background=[("pressed", c["button_pressed"]), ("selected", c["accent_soft"]),
                                        ("active", c["button_hover"])],
              foreground=[("disabled", c["disabled"])])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=c["window"], foreground=c["text"],
                        indicatorbackground=c["field"], indicatorforeground=c["text"],
                        upperbordercolor=c["field_border"], lowerbordercolor=c["field_border"],
                        focuscolor=c["window"], padding=(0, 1))
        style.map(name, background=[("active", c["window"])],
                  indicatorbackground=[("disabled", c["field_disabled"]), ("pressed", c["accent_soft"]),
                                       ("selected", c["field"])],
                  foreground=[("disabled", c["disabled"])])
    style.configure("TCombobox", fieldbackground=c["field"], background=c["button"], foreground=c["text"],
                    arrowcolor=c["text"], bordercolor=c["field_border"], lightcolor=c["field"],
                    darkcolor=c["field"], selectbackground=c["field"], selectforeground=c["text"],
                    padding=pad["field_pad"])
    style.map("TCombobox", fieldbackground=[("readonly", c["field"]), ("disabled", c["field_disabled"])],
              foreground=[("readonly", c["text"]), ("disabled", c["disabled"])],
              selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["text"])],
              background=[("active", c["button_hover"])])
    style.configure("TEntry", fieldbackground=c["field"], foreground=c["text"], bordercolor=c["field_border"],
                    lightcolor=c["field"], darkcolor=c["field"], padding=pad["field_pad"])
    style.map("TEntry", fieldbackground=[("readonly", c["field_disabled"]), ("disabled", c["field_disabled"])])
    style.configure("TNotebook", background=c["window"], bordercolor=c["border"], tabmargins=(0, 2, 0, 0),
                    lightcolor=c["window"], darkcolor=c["window"])
    style.configure("TNotebook.Tab", background=c["surface"], foreground=c["secondary"],
                    bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"],
                    padding=pad["tab_pad"])
    style.map("TNotebook.Tab", background=[("selected", c["elevated"])],
              foreground=[("selected", c["text"])], lightcolor=[("selected", c["elevated"])])
    style.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["scroll_trough"],
                    bordercolor=c["border"], lightcolor=c["accent"], darkcolor=c["accent"],
                    thickness=pad["progress_thickness"])
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=c["scroll_thumb"], troughcolor=c["scroll_trough"],
                        bordercolor=c["scroll_trough"], arrowcolor=c["secondary"],
                        lightcolor=c["scroll_thumb"], darkcolor=c["scroll_thumb"], gripcount=0)
        style.map(f"{orient}.TScrollbar", background=[("active", c["scroll_thumb_hover"])])
    style.configure("TPanedwindow", background=c["divider"])
    style.configure("Sash", sashthickness=6, gripcount=0, background=c["divider"],
                    lightcolor=c["divider"], bordercolor=c["divider"])
    style.configure("TSeparator", background=c["divider"])
    # Drop-down lists created later pick these up; existing ones are repainted by owners.
    root.option_add("*TCombobox*Listbox.background", c["field"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["selection"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["selection_text"])
    native_title_bar(root, appearance)
    return {"appearance": appearance, "colors": dict(c), "fonts": f}


_TK_ROLES = {"field": ("field", "text"), "surface": ("window", "text"), "log": ("field", "text")}


def style_tk_widget(widget, bundle: dict, role: str = "field", **overrides) -> dict:
    """Color a classic Tk widget (Listbox/Text/Toplevel) from *bundle*; returns applied options."""
    c = bundle["colors"]
    bg, fg = _TK_ROLES[role]
    opts = {"background": c[bg], "foreground": c[fg], "highlightbackground": c["field_border"],
            "highlightcolor": c["focus"], "insertbackground": c["text"],
            "selectbackground": c["selection"], "selectforeground": c["selection_text"],
            "inactiveselectbackground": c["selection_inactive"], "disabledforeground": c["disabled"]}
    opts.update(overrides)
    try:
        supported = set(widget.keys())
    except tk.TclError:
        return {}
    applied = {k: v for k, v in opts.items() if k in supported}
    if applied:
        widget.configure(**applied)
    return applied


def style_combobox_popdown(combo: ttk.Combobox, bundle: dict) -> bool:
    """Recolor an existing combobox drop-down list in place (no ttk style reaches it)."""
    c = bundle["colors"]
    try:
        popdown = combo.tk.eval(f"ttk::combobox::PopdownWindow {combo}")
        combo.tk.call(f"{popdown}.f.l", "configure", "-background", c["field"], "-foreground", c["text"],
                      "-selectbackground", c["selection"], "-selectforeground", c["selection_text"])
    except tk.TclError:
        return False
    return True


def native_title_bar(root: tk.Misc, appearance: str) -> None:
    """Best effort: match the native title bar (Windows DWM) or window chrome (macOS)."""
    dark = appearance == DARK
    try:
        if sys.platform == "win32":
            import ctypes
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            value = ctypes.c_int(1 if dark else 0)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, older builds)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                              ctypes.sizeof(value)) == 0:
                    break
        elif sys.platform == "darwin":
            root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", root,
                         "darkaqua" if dark else "aqua")
    except Exception:  # noqa: BLE001 - cosmetic only; never block the UI
        pass
