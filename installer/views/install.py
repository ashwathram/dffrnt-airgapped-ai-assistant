"""Install view: first-run deployment from a bundle tarball — the GUI
face of the CLI's `install` command. Pick a bundle (auto-detected when one
sits nearby, or Browse), pick a destination, check prerequisites, Install.

On success it calls the app shell's on_installed(app_root) so the Manage,
Models, and Logs tabs re-point at the newly installed stack without a
restart.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import widgets
from ..installers import InstallError, Installer, find_bundles
from ..installers.docker_installer import default_install_dest, is_installed
from ..platform_detect import PlatformInfo
from ..process import BackgroundJob


class InstallView(ttk.Frame):
    def __init__(self, parent: tk.Misc, platform_info: PlatformInfo,
                 installer: Installer, app_root: Path, on_installed):
        super().__init__(parent, style="App.TFrame")
        self.platform_info = platform_info
        self.installer = installer
        self.app_root = app_root
        self.on_installed = on_installed  # callback(Path) -> None, set by app shell
        self._job = None
        self._busy = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._scroll = widgets.ScrollableFrame(self, style="App.TFrame")
        self._scroll.grid(row=0, column=0, sticky="nsew")
        self._body = self._scroll.body
        self._body.configure(padding=20)
        self._body.columnconfigure(0, weight=1)

        self._build_status_card()
        self._build_bundle_card()
        self._build_prereq_card()
        self._build_console()

        self.refresh_prereqs()
        self._autodetect_bundle()

    # ---- shell hooks ------------------------------------------------------
    def on_show(self) -> None:
        self._scroll.enable_wheel()

    def on_hide(self) -> None:
        self._scroll.disable_wheel()

    # ---- layout -----------------------------------------------------------
    def _build_status_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(0, weight=1)
        ttk.Label(c, text="Installation", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self._status_label = ttk.Label(c, text="", style="Muted.TLabel", wraplength=640, justify="left")
        self._status_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._refresh_installed_state()

    def _refresh_installed_state(self) -> None:
        if is_installed(self.app_root):
            self._status_label.configure(
                text=f"An installed stack was found at {self.app_root}. Installing again "
                     "updates it in place (the running stack is stopped first, and you "
                     "choose whether your edited config.toml is kept)."
            )
        else:
            self._status_label.configure(
                text="No installed stack found. Select the dffrnt-*.tar.gz bundle "
                     "(produced by deploy/package.sh and shipped in dist/) and a "
                     "destination, then Install."
            )

    def _build_bundle_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(1, weight=1)

        ttk.Label(c, text="Bundle", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=3)

        ttk.Label(c, text="Tarball", style="CardBody.TLabel").grid(
            row=1, column=0, sticky="w", pady=(10, 2))
        self._bundle_var = tk.StringVar()
        ttk.Entry(c, textvariable=self._bundle_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(10, 2))
        widgets.ghost_button(c, "Browse…", self._on_browse_bundle).grid(
            row=1, column=2, sticky="e", pady=(10, 2))

        ttk.Label(c, text="Install to", style="CardBody.TLabel").grid(
            row=2, column=0, sticky="w", pady=2)
        self._dest_var = tk.StringVar(value=str(
            self.app_root if is_installed(self.app_root) else default_install_dest()))
        ttk.Entry(c, textvariable=self._dest_var).grid(row=2, column=1, sticky="ew", padx=8, pady=2)
        widgets.ghost_button(c, "Browse…", self._on_browse_dest).grid(row=2, column=2, sticky="e", pady=2)

        self._bundle_info = ttk.Label(c, text="", style="Muted.TLabel")
        self._bundle_info.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self._install_btn = widgets.primary_button(c, "Install", self._on_install)
        self._install_btn.grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
        if not self.platform_info.pathway_implemented:
            self._install_btn.state(["disabled"])

    def _build_prereq_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(0, weight=1)

        head = ttk.Frame(c, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Prerequisites", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        widgets.ghost_button(head, "Re-check", self.refresh_prereqs).grid(row=0, column=1, sticky="e")

        self._prereq_rows = ttk.Frame(c, style="Card.TFrame")
        self._prereq_rows.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._prereq_rows.columnconfigure(1, weight=1)

    def _build_console(self) -> None:
        ttk.Label(self._body, text="Output", style="MutedApp.TLabel").grid(row=3, column=0, sticky="w")
        wrap = ttk.Frame(self._body, style="Card.TFrame", padding=1)
        wrap.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self._console = widgets.console(wrap, height=16)
        self._console.grid(row=0, column=0, sticky="nsew")

    # ---- bundle selection --------------------------------------------------
    def _autodetect_bundle(self) -> None:
        # "A dffrnt-*.tar.gz sitting near me": look next to the app root,
        # in dist/, and in the cwd; take the newest. The operator can
        # always Browse to override.
        candidates = find_bundles([
            self.app_root, self.app_root.parent,
            self.app_root.parent / "dist", Path.cwd(), Path.cwd() / "dist",
        ])
        if candidates:
            self._bundle_var.set(str(candidates[0]))
            self._describe_bundle(candidates[0])

    def _describe_bundle(self, bundle: Path) -> None:
        try:
            info = self.installer.inspect_bundle(bundle)
        except (InstallError, NotImplementedError) as exc:
            self._bundle_info.configure(text=f"⚠ {exc}")
            return
        size_mb = info.size_bytes / (1024 * 1024)
        self._bundle_info.configure(
            text=f"{info.path.name} — {info.target_system} bundle, {size_mb:,.0f} MB")

    def _on_browse_bundle(self) -> None:
        picked = filedialog.askopenfilename(
            parent=self, title="Select the deployment bundle",
            filetypes=[("DFFRNT bundle", "dffrnt-*.tar.gz"), ("tar.gz archives", "*.tar.gz")],
        )
        if picked:
            self._bundle_var.set(picked)
            self._describe_bundle(Path(picked))

    def _on_browse_dest(self) -> None:
        picked = filedialog.askdirectory(parent=self, title="Select the install destination")
        if picked:
            self._dest_var.set(picked)

    # ---- prereqs -----------------------------------------------------------
    def refresh_prereqs(self) -> None:
        for child in self._prereq_rows.winfo_children():
            child.destroy()
        try:
            checks = self.installer.check_prerequisites()
        except Exception as exc:
            from ..backends import PrereqCheck
            checks = [PrereqCheck("Prerequisite check failed", False, str(exc))]
        for i, check in enumerate(checks):
            kind = "ok" if check.ok else "err"
            widgets.status_pill(self._prereq_rows, kind, "OK" if check.ok else "MISSING").grid(
                row=i, column=0, sticky="w", pady=2)
            text = check.name + (f" — {check.detail}" if check.detail else "")
            ttk.Label(self._prereq_rows, text=text, style="CardBody.TLabel").grid(
                row=i, column=1, sticky="w", padx=(8, 0), pady=2)

    # ---- install -----------------------------------------------------------
    def _on_install(self) -> None:
        if self._busy:
            return
        bundle = Path(self._bundle_var.get().strip()) if self._bundle_var.get().strip() else None
        if bundle is None:
            messagebox.showerror("No bundle selected",
                                 "Select a dffrnt-*.tar.gz bundle first.", parent=self)
            return
        dest = Path(self._dest_var.get().strip()) if self._dest_var.get().strip() else None
        if dest is None:
            messagebox.showerror("No destination", "Choose an install destination.", parent=self)
            return

        try:
            self.installer.inspect_bundle(bundle)
        except (InstallError, NotImplementedError) as exc:
            messagebox.showerror("Invalid bundle", str(exc), parent=self)
            return

        # Resolve the config question up front — a GUI shouldn't block a
        # background job on a mid-run dialog.
        keep_config = True
        if (dest / "config.toml").is_file():
            keep_config = not messagebox.askyesno(
                "Existing config.toml found",
                f"{dest} already contains a config.toml.\n\n"
                "Overwrite it with the bundle's default?\n"
                "(No = keep your existing config — the safe default. If you "
                "overwrite, the current file is archived as config.toml.old.)",
                parent=self, default=messagebox.NO,
            )

        if not messagebox.askyesno(
            "Confirm install",
            f"Install {bundle.name} into {dest}?\n\n"
            "Any running stack there will be stopped and its images replaced, "
            "then the new stack is started.",
            parent=self,
        ):
            return

        widgets.console_append(self._console, [f"$ install {bundle.name} -> {dest}"])
        self._busy = True
        self._install_btn.state(["disabled"])
        self._job = BackgroundJob(
            lambda out: self.installer.install(bundle, dest, out, keep_config=keep_config)
        ).start()
        self.after(100, lambda: self._poll_job(dest))

    def _poll_job(self, dest: Path) -> None:
        job = self._job
        if job is None:
            return
        widgets.console_append(self._console, job.drain())
        if job.done.is_set():
            self._busy = False
            self._install_btn.state(["!disabled"])
            self._job = None
            if job.error is not None:
                widgets.console_append(self._console, [f"!! {job.error}"])
            else:
                self.app_root = dest
                self._refresh_installed_state()
                self.on_installed(dest)
            return
        self.after(150, lambda: self._poll_job(dest))
