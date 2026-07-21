"""Design tokens ported from dffrnt_assistant/ui/styles/theme.css, and the
ttk style setup that applies them.

ttk has no border-radius or box-shadow, so this is a faithful *palette* port,
not a pixel port — flat rectangles standing in for the web UI's rounded
cards. Keep the two token sets in sync by hand; there is no shared source
of truth between CSS custom properties and this dict.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---- Color tokens (mirrors :root in theme.css) ------------------------------
COLORS = {
    "background": "#f8f9fb",
    "foreground": "#091A29",
    "card": "#ffffff",
    "card_foreground": "#091A29",
    "primary": "#091A29",
    "primary_foreground": "#ffffff",
    "muted": "#eef0f3",
    "muted_foreground": "#5a6a78",
    "accent": "#5D27B8",
    "accent_foreground": "#ffffff",
    "highlight": "#E9FF5B",
    "destructive": "#E72300",
    # rgba(9,26,41,0.1) flattened onto --background for a Tk-safe solid.
    "border": "#e3e5e9",
    "sidebar": "#091A29",
    "sidebar_foreground": "#e8edf2",
    "sidebar_hover": "#16283a",
    "sidebar_active": "#1c3348",
}

# Status colors, ported from library.css (.up-status / .up-card-status).
STATUS_COLORS = {
    "ok": "#0a7c4a",
    "err": COLORS["destructive"],
    "warn": "#b8860b",
    "muted": COLORS["muted_foreground"],
}
STATUS_BG = {
    "ok": "#e8f5ee",
    "err": "#fbe9e6",
    "warn": "#fbf1da",
    "muted": COLORS["muted"],
}

RADIUS = 8  # --radius: 0.5rem, approximated (ttk can't round corners)
PAD = 12

FONT_SIZE = 10
FONT_SIZE_SM = 9
FONT_SIZE_LG = 13
FONT_SIZE_XL = 16


def _first_available(candidates: list[str]) -> str:
    families = set(tkfont.families())
    for name in candidates:
        if name in families:
            return name
    return "TkDefaultFont"


def resolve_fonts() -> dict[str, str]:
    """Best-effort match of the web UI's font stack against installed fonts.

    The web UI self-hosts Inter/JetBrains Mono (see ui/fonts/*.woff2); a
    desktop Tk app instead depends on what the OS already has. Mirror the
    same fallback order as --font-sans / --font-mono in theme.css.
    """
    sans = _first_available(
        ["Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Roboto", "DejaVu Sans"]
    )
    mono = _first_available(
        ["JetBrains Mono", "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono"]
    )
    return {"sans": sans, "mono": mono}


_resolved_fonts: dict[str, str] | None = None


def mono_font() -> str:
    """The monospace family resolved by the most recent configure_style()
    call — for widgets built after startup (e.g. widgets.console) that
    need the same font without threading it through every constructor.
    Falls back to a family Tk always has if called before configure_style.
    """
    if _resolved_fonts is not None:
        return _resolved_fonts["mono"]
    return "Courier"


def configure_style(root: tk.Tk) -> dict[str, str]:
    """Apply the DFFRNT palette to a ttk.Style and return the resolved fonts."""
    global _resolved_fonts
    fonts = resolve_fonts()
    _resolved_fonts = fonts
    root.configure(background=COLORS["background"])

    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(family=fonts["sans"], size=FONT_SIZE)
    text_font = tkfont.nametofont("TkTextFont")
    text_font.configure(family=fonts["sans"], size=FONT_SIZE)

    style = ttk.Style(root)
    # 'clam' is the only builtin theme that reliably honors background/
    # foreground overrides on every platform; the native themes (aqua,
    # vista) ignore most of them.
    style.theme_use("clam")

    style.configure(".", background=COLORS["background"], foreground=COLORS["foreground"],
                     font=(fonts["sans"], FONT_SIZE))

    style.configure("App.TFrame", background=COLORS["background"])
    # Frame has no interactive states (no disabled/active), so the border
    # color is a plain configure — a style.map keyed on a button-style
    # state here would be a silent no-op at best, a Tcl error at worst.
    style.configure(
        "Card.TFrame",
        background=COLORS["card"],
        relief="solid",
        borderwidth=1,
        bordercolor=COLORS["border"],
    )

    style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
    style.configure(
        "Brand.TLabel",
        background=COLORS["sidebar"],
        foreground=COLORS["sidebar_foreground"],
        font=(fonts["sans"], FONT_SIZE_LG, "bold"),
    )
    style.configure(
        "Sidebar.TLabel",
        background=COLORS["sidebar"],
        foreground=COLORS["sidebar_foreground"],
        font=(fonts["sans"], FONT_SIZE),
    )
    style.configure(
        "SidebarMuted.TLabel",
        background=COLORS["sidebar"],
        foreground="#9fb0bf",
        font=(fonts["sans"], FONT_SIZE_SM),
    )

    # Sidebar nav buttons (.nav-btn) — flat, left-aligned, hover/active via map().
    style.configure(
        "Nav.TButton",
        background=COLORS["sidebar"],
        foreground=COLORS["sidebar_foreground"],
        font=(fonts["sans"], FONT_SIZE),
        borderwidth=0,
        focuscolor=COLORS["sidebar"],
        padding=(12, 10),
        anchor="w",
    )
    style.map(
        "Nav.TButton",
        background=[("active", COLORS["sidebar_hover"])],
    )
    style.configure(
        "NavActive.TButton",
        background=COLORS["sidebar_active"],
        foreground="#ffffff",
        font=(fonts["sans"], FONT_SIZE, "bold"),
        borderwidth=0,
        focuscolor=COLORS["sidebar_active"],
        padding=(12, 10),
        anchor="w",
    )
    style.map(
        "NavActive.TButton",
        background=[("active", COLORS["sidebar_active"])],
    )

    # Primary / ghost / danger buttons (.btn-primary / .btn-ghost / destructive).
    style.configure(
        "Primary.TButton",
        background=COLORS["primary"],
        foreground=COLORS["primary_foreground"],
        font=(fonts["sans"], FONT_SIZE, "bold"),
        borderwidth=0,
        focuscolor=COLORS["primary"],
        padding=(14, 8),
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", COLORS["muted"]), ("active", "#16283a")],
        foreground=[("disabled", COLORS["muted_foreground"])],
    )
    style.configure(
        "Ghost.TButton",
        background=COLORS["card"],
        foreground=COLORS["foreground"],
        font=(fonts["sans"], FONT_SIZE, "bold"),
        borderwidth=1,
        focuscolor=COLORS["card"],
        padding=(14, 8),
    )
    style.map(
        "Ghost.TButton",
        background=[("active", COLORS["muted"]), ("disabled", COLORS["card"])],
        foreground=[("disabled", COLORS["muted_foreground"])],
        bordercolor=[("!disabled", COLORS["border"])],
    )
    style.configure(
        "Danger.TButton",
        background=COLORS["card"],
        foreground=COLORS["destructive"],
        font=(fonts["sans"], FONT_SIZE, "bold"),
        borderwidth=1,
        focuscolor=COLORS["card"],
        padding=(14, 8),
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#fbe9e6"), ("disabled", COLORS["card"])],
        foreground=[("disabled", COLORS["muted_foreground"])],
        bordercolor=[("!disabled", COLORS["border"])],
    )

    style.configure("Topbar.TFrame", background=COLORS["card"])
    style.configure(
        "TopbarTitle.TLabel",
        background=COLORS["card"],
        foreground=COLORS["muted_foreground"],
        font=(fonts["sans"], FONT_SIZE),
    )
    style.configure(
        "CardTitle.TLabel",
        background=COLORS["card"],
        foreground=COLORS["foreground"],
        font=(fonts["sans"], FONT_SIZE_LG, "bold"),
    )
    style.configure(
        "CardBody.TLabel",
        background=COLORS["card"],
        foreground=COLORS["foreground"],
        font=(fonts["sans"], FONT_SIZE),
    )
    style.configure(
        "Muted.TLabel",
        background=COLORS["card"],
        foreground=COLORS["muted_foreground"],
        font=(fonts["sans"], FONT_SIZE_SM),
    )
    style.configure(
        "MutedApp.TLabel",
        background=COLORS["background"],
        foreground=COLORS["muted_foreground"],
        font=(fonts["sans"], FONT_SIZE_SM),
    )

    # Status pills (.up-status / .up-card-status in library.css) — one
    # style per STATUS_COLORS key, looked up by name in widgets.status_pill.
    for kind, fg in STATUS_COLORS.items():
        style.configure(
            f"Pill{kind.capitalize()}.TLabel",
            background=STATUS_BG[kind],
            foreground=fg,
            font=(fonts["sans"], FONT_SIZE_SM, "bold"),
            padding=(8, 3),
        )

    style.configure("TSeparator", background=COLORS["border"])

    style.configure(
        "TCombobox",
        fieldbackground=COLORS["card"],
        background=COLORS["card"],
        foreground=COLORS["foreground"],
    )

    return fonts
