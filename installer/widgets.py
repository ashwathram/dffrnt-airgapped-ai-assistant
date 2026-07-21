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


class ScrollableFrame(ttk.Frame):
    """A vertically scrolling container. Add content to `.body`, not to the
    ScrollableFrame itself.

    ttk has no scrollable container, so this is the canonical Canvas + inner
    frame + Scrollbar assembly: the body frame is drawn into a Canvas window,
    and the Canvas scrolls it. The scrollbar only appears when the content is
    actually taller than the viewport, and the body is kept exactly as wide
    as the Canvas so there is never a horizontal scrollbar (content reflows /
    each row scrolls its own overflow instead).

    Mouse-wheel scrolling is bound globally (bind_all) but only while
    enable_wheel() is in effect — the owning view toggles it in on_show /
    on_hide so the wheel drives whichever view is actually visible, and
    hovering a card (a child window over the Canvas) still scrolls the page
    rather than doing nothing.
    """

    def __init__(self, parent: tk.Misc, **kwargs):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            self, highlightthickness=0, borderwidth=0, background=COLORS["background"],
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._vbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._on_yscroll)

        self.body = ttk.Frame(self._canvas, style="App.TFrame")
        self._window = self._canvas.create_window((0, 0), window=self.body, anchor="nw")

        # Body changed size -> refresh the scrollable region to match.
        self.body.bind("<Configure>", self._on_body_configure)
        # Canvas changed size -> keep the body the same width (no h-scroll).
        self._canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_body_configure(self, _event: tk.Event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window, width=event.width)

    def _on_yscroll(self, first: str, last: str) -> None:
        # Show the scrollbar only when the content overflows the viewport.
        if float(first) <= 0.0 and float(last) >= 1.0:
            self._vbar.grid_remove()
        else:
            self._vbar.grid(row=0, column=1, sticky="ns")
        self._vbar.set(first, last)

    # ---- wheel, toggled by the owning view's on_show / on_hide ----------
    def enable_wheel(self) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)   # Windows / macOS
        self._canvas.bind_all("<Button-4>", self._on_wheel)     # Linux scroll up
        self._canvas.bind_all("<Button-5>", self._on_wheel)     # Linux scroll down

    def disable_wheel(self) -> None:
        self._canvas.unbind_all("<MouseWheel>")
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event: tk.Event) -> None:
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:  # Windows delta is ±120 multiples, macOS small — sign is enough.
            delta = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(delta, "units")


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
