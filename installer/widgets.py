"""Small, stateless widget factories shared across views. Styling itself
lives in theme.py — these just apply the right style name consistently so
call sites read like the thing they're building (`primary_button`, not
`ttk.Button(..., style="Primary.TButton")` repeated everywhere).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme
from .theme import COLORS


def card(parent: tk.Misc, **kwargs) -> ttk.Frame:
    frame = ttk.Frame(parent, style="Card.TFrame", padding=16, **kwargs)
    return frame


def primary_button(parent: tk.Misc, text: str, command=None) -> ttk.Button:
    return ttk.Button(parent, text=text, style="Primary.TButton", command=command)


def ghost_button(parent: tk.Misc, text: str, command=None) -> ttk.Button:
    return ttk.Button(parent, text=text, style="Ghost.TButton", command=command)


def danger_button(parent: tk.Misc, text: str, command=None) -> ttk.Button:
    return ttk.Button(parent, text=text, style="Danger.TButton", command=command)


def status_pill(parent: tk.Misc, kind: str, text: str) -> ttk.Label:
    """kind is one of theme.STATUS_COLORS' keys: ok / err / warn / muted."""
    return ttk.Label(parent, text=text, style=f"Pill{kind.capitalize()}.TLabel")


def health_kind(running: bool, healthy: bool | None) -> str:
    """Maps a ServiceStatus's (running, healthy) pair to a pill kind."""
    if not running:
        return "err"
    if healthy is False:
        return "warn"
    if healthy is True:
        return "ok"
    return "muted"  # running, health unknown


def console(parent: tk.Misc, height: int = 14, font: str | None = None) -> tk.Text:
    """The dark, monospace output pane used for streamed command output —
    stands in for the web UI's terminal-ish log/audit views."""
    text = tk.Text(
        parent,
        height=height,
        background=COLORS["sidebar"],
        foreground="#d7e2ea",
        insertbackground="#d7e2ea",
        borderwidth=0,
        highlightthickness=0,
        wrap="word",
        font=(font or theme.mono_font(), 10),
        state="disabled",
    )
    return text


def console_append(widget: tk.Text, lines: list[str]) -> None:
    if not lines:
        return
    widget.configure(state="normal")
    for line in lines:
        widget.insert("end", line + "\n")
    widget.see("end")
    widget.configure(state="disabled")


def console_clear(widget: tk.Text) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.configure(state="disabled")
