"""Dashboard view: platform summary, prerequisite checks, service status,
and the start/stop/restart/reingest actions — the GUI equivalent of
`dffrnt_ctrl_panel.sh {start|stop|restart|status|reingest}`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import widgets
from ..backends import Backend, PrereqCheck, ServiceStatus
from ..config import AppConfig
from ..platform_detect import PlatformInfo
from ..process import BackgroundJob

_SERVICE_PORTS = {"Qdrant": "qdrant_port", "Ollama": "ollama_port", "API": "api_port"}


class DashboardView(ttk.Frame):
    def __init__(self, parent: tk.Misc, platform_info: PlatformInfo, config: AppConfig, backend: Backend):
        super().__init__(parent, style="App.TFrame", padding=20)
        self.platform_info = platform_info
        self.config = config
        self.backend = backend
        self._job = None  # active BackgroundJob, if any
        self._on_success = None  # callback for the current job, if any
        self._busy = False

        self.columnconfigure(0, weight=1)

        self._build_platform_card()
        self._build_prereq_card()
        self._build_services_card()
        self._build_maintenance_card()
        self._build_console()

        self.refresh_prereqs()
        self.refresh_status()

    # ---- layout -----------------------------------------------------------
    def _build_platform_card(self) -> None:
        c = widgets.card(self)
        c.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(1, weight=1)

        pi = self.platform_info
        ttk.Label(c, text="Platform", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", columnspan=2)
        detail = (
            f"{pi.os.value}  ·  {pi.arch}  ·  pathway: {pi.pathway.value}"
            f"{'  ·  GPU detected' if pi.has_nvidia_gpu else ''}"
            f"{'' if pi.docker_present else '  ·  docker not on PATH'}"
        )
        ttk.Label(c, text=detail, style="Muted.TLabel").grid(row=1, column=0, sticky="w", columnspan=2, pady=(4, 0))

        if not pi.pathway_implemented:
            ttk.Label(
                c,
                text=f"The {pi.pathway.value} pathway isn't implemented yet for this OS.",
                style="Muted.TLabel",
                foreground="#b8860b",
            ).grid(row=2, column=0, sticky="w", columnspan=2, pady=(8, 0))

    def _build_prereq_card(self) -> None:
        c = widgets.card(self)
        c.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(0, weight=1)

        head = ttk.Frame(c, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Prerequisites", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        widgets.ghost_button(head, "Re-check", self.refresh_prereqs).grid(row=0, column=1, sticky="e")

        self._prereq_rows = ttk.Frame(c, style="Card.TFrame")
        self._prereq_rows.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._prereq_rows.columnconfigure(1, weight=1)

    def _build_services_card(self) -> None:
        c = widgets.card(self)
        c.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(0, weight=1)

        head = ttk.Frame(c, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Services", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")

        self._service_rows = ttk.Frame(c, style="Card.TFrame")
        self._service_rows.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._service_rows.columnconfigure(1, weight=1)

        actions = ttk.Frame(c, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._start_btn = widgets.primary_button(actions, "Start", self._on_start)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._restart_btn = widgets.ghost_button(actions, "Restart", self._on_restart)
        self._restart_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = widgets.danger_button(actions, "Stop", self._on_stop)
        self._stop_btn.pack(side="left", padx=(0, 8))
        widgets.ghost_button(actions, "Refresh status", self.refresh_status).pack(side="left")

        if not self.platform_info.pathway_implemented:
            for btn in (self._start_btn, self._restart_btn, self._stop_btn):
                btn.state(["disabled"])

    def _build_maintenance_card(self) -> None:
        c = widgets.card(self)
        c.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(0, weight=1)

        ttk.Label(c, text="Maintenance", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            c, text="Re-ingest every stored document — the GUI equivalent of "
                     "dffrnt_ctrl_panel.sh reingest. Previews the affected files first; "
                     "nothing changes until you confirm.",
            style="Muted.TLabel", wraplength=640, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        self._reingest_btn = widgets.ghost_button(c, "Reingest documents", self._on_reingest)
        self._reingest_btn.grid(row=2, column=0, sticky="w")
        if not self.platform_info.pathway_implemented:
            self._reingest_btn.state(["disabled"])

    def _build_console(self) -> None:
        ttk.Label(self, text="Output", style="MutedApp.TLabel").grid(row=4, column=0, sticky="w")
        wrap = ttk.Frame(self, style="Card.TFrame", padding=1)
        wrap.grid(row=5, column=0, sticky="nsew", pady=(4, 0))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)
        self._console = widgets.console(wrap)
        self._console.grid(row=0, column=0, sticky="nsew")

    # ---- prerequisite / status refresh ------------------------------------
    def refresh_prereqs(self) -> None:
        for child in self._prereq_rows.winfo_children():
            child.destroy()
        try:
            checks: list[PrereqCheck] = self.backend.check_prerequisites()
        except Exception as exc:
            checks = [PrereqCheck("Prerequisite check failed", False, str(exc))]
        for i, check in enumerate(checks):
            kind = "ok" if check.ok else "err"
            widgets.status_pill(self._prereq_rows, kind, "OK" if check.ok else "MISSING").grid(
                row=i, column=0, sticky="w", pady=2)
            text = check.name + (f" — {check.detail}" if check.detail else "")
            ttk.Label(self._prereq_rows, text=text, style="CardBody.TLabel").grid(
                row=i, column=1, sticky="w", padx=(8, 0), pady=2)

    def refresh_status(self) -> None:
        for child in self._service_rows.winfo_children():
            child.destroy()
        try:
            statuses: list[ServiceStatus] = list(self.backend.status())
        except Exception as exc:
            ttk.Label(self._service_rows, text=f"Could not read status: {exc}", style="Muted.TLabel").grid(
                row=0, column=0, sticky="w")
            return
        for i, svc in enumerate(statuses):
            kind = widgets.health_kind(svc.running, svc.healthy)
            widgets.status_pill(self._service_rows, kind, svc.detail or ("up" if svc.running else "down")).grid(
                row=i, column=0, sticky="w", pady=2)
            port_attr = _SERVICE_PORTS.get(svc.name)
            port = getattr(self.config, port_attr, None) if port_attr else None
            label = f"{svc.name}" + (f"  ·  localhost:{port}" if port else "")
            ttk.Label(self._service_rows, text=label, style="CardBody.TLabel").grid(
                row=i, column=1, sticky="w", padx=(8, 0), pady=2)

    # ---- actions ------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy or self.platform_info.pathway_implemented:
            state = "disabled" if busy else "!disabled"
            for btn in (self._start_btn, self._restart_btn, self._stop_btn, self._reingest_btn):
                btn.state([state])

    def _run_action(self, label: str, fn, on_success=None) -> None:
        if self._busy:
            return
        widgets.console_append(self._console, [f"$ {label}"])
        self._set_busy(True)
        self._on_success = on_success
        self._job = BackgroundJob(fn).start()
        self.after(100, self._poll_job)

    def _poll_job(self) -> None:
        job = self._job
        if job is None:
            return
        widgets.console_append(self._console, job.drain())
        if job.done.is_set():
            self._set_busy(False)
            self._job = None
            on_success, self._on_success = self._on_success, None
            error = job.error
            if error is not None:
                widgets.console_append(self._console, [f"!! {error}"])
            self.refresh_status()
            if error is None and on_success is not None:
                on_success()
            return
        self.after(150, self._poll_job)

    def _on_start(self) -> None:
        self._run_action("start", self.backend.start)

    def _on_stop(self) -> None:
        self._run_action("stop", self.backend.stop)

    def _on_restart(self) -> None:
        self._run_action("restart", self.backend.restart)

    def _on_reingest(self) -> None:
        self._run_action(
            "reingest --dry-run (preview)", self.backend.reingest_preview,
            on_success=self._confirm_reingest_apply,
        )

    def _confirm_reingest_apply(self) -> None:
        proceed = messagebox.askyesno(
            "Confirm re-ingestion",
            "Proceed with re-ingestion of the files listed in the console output above?\n\n"
            "This can take a while and, once started, will not stop partway through.",
            parent=self,
        )
        if proceed:
            self._run_action("reingest --force --verbose", self.backend.reingest_apply)
        else:
            widgets.console_append(self._console, [">> Aborted — nothing changed."])
