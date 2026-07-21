"""Logs view: follow container logs, the GUI equivalent of
`dffrnt_ctrl_panel.sh logs [service]`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import widgets
from ..backends import Backend

_SERVICES = ["all", "qdrant", "ollama", "api"]


class LogsView(ttk.Frame):
    def __init__(self, parent: tk.Misc, backend: Backend):
        super().__init__(parent, style="App.TFrame", padding=20)
        self.backend = backend
        self._follower = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        head = ttk.Frame(self, style="App.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(head, text="Service", style="MutedApp.TLabel").pack(side="left", padx=(0, 8))
        self._service = tk.StringVar(value="all")
        combo = ttk.Combobox(head, textvariable=self._service, values=_SERVICES, state="readonly", width=10)
        combo.pack(side="left", padx=(0, 12))
        combo.bind("<<ComboboxSelected>>", self._on_service_changed)

        self._follow_btn = widgets.primary_button(head, "Follow", self._on_follow)
        self._follow_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = widgets.ghost_button(head, "Stop", self._on_stop)
        self._stop_btn.pack(side="left")
        self._stop_btn.state(["disabled"])

        wrap = ttk.Frame(self, style="Card.TFrame", padding=1)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self._console = widgets.console(wrap, height=28)
        self._console.grid(row=0, column=0, sticky="nsew")

    def _on_service_changed(self, _event=None) -> None:
        # If a stream is live, re-follow the newly selected service so the
        # view reflects the menu without a manual Stop/Follow. If nothing is
        # being followed, the new selection just applies on the next Follow.
        if self._follower is not None:
            self._on_follow()

    def _on_follow(self) -> None:
        self._stop_follower()
        widgets.console_clear(self._console)
        service = self._service.get()
        service_arg = None if service == "all" else service
        try:
            self._follower = self.backend.stream_logs(service_arg, lambda _line: None)
        except Exception as exc:
            widgets.console_append(self._console, [f"!! {exc}"])
            return
        self._follow_btn.state(["disabled"])
        self._stop_btn.state(["!disabled"])
        self.after(100, self._poll)

    def _on_stop(self) -> None:
        self._stop_follower()
        self._follow_btn.state(["!disabled"])
        self._stop_btn.state(["disabled"])

    def _stop_follower(self) -> None:
        if self._follower is not None:
            self._follower.stop()
            self._follower = None

    def _poll(self) -> None:
        if self._follower is None:
            return
        lines, ended = self._follower.drain()
        widgets.console_append(self._console, lines)
        if ended:
            widgets.console_append(self._console, ["-- log stream ended --"])
            self._follower = None
            self._follow_btn.state(["!disabled"])
            self._stop_btn.state(["disabled"])
            return
        self.after(150, self._poll)

    def on_hide(self) -> None:
        """Called by the app shell when navigating away — logs are only
        followed while this view is visible."""
        self._stop_follower()
        self._follow_btn.state(["!disabled"])
        self._stop_btn.state(["disabled"])

    def set_backend(self, backend: Backend) -> None:
        """Re-point at a (re)installed stack (see DashboardView.set_backend)."""
        self._stop_follower()
        self.backend = backend
