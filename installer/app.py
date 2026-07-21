"""Main window: a sidebar + content shell echoing the web UI's layout
(dffrnt_assistant/ui/index.html's .sidebar/.brand/.nav-btn/.main/.topbar),
switching between the Dashboard and Logs views.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import theme
from .backends import Backend
from .backends.docker_backend import DockerComposeBackend
from .backends.portable_backend import PortableBackend
from .config import AppConfig, find_app_root, load_config
from .logging_setup import configure_logging
from .platform_detect import PlatformInfo, Pathway, detect
from .views.dashboard import DashboardView
from .views.logs import LogsView

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _make_backend(app_root: Path, config: AppConfig, platform_info: PlatformInfo) -> Backend:
    if platform_info.pathway is Pathway.PORTABLE:
        return PortableBackend(app_root, config)
    return DockerComposeBackend(app_root, config)


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DFFRNT AI Assistant — Control Panel")
        self.geometry("980x720")
        self.minsize(820, 600)

        fonts = theme.configure_style(self)
        self._set_icon()

        self.platform_info = detect()
        self.app_root = find_app_root()
        self.logger = configure_logging(self.app_root)
        self.logger.info(
            "platform: os=%s arch=%s pathway=%s gpu_detected=%s docker_present=%s",
            self.platform_info.os.value, self.platform_info.arch, self.platform_info.pathway.value,
            self.platform_info.has_nvidia_gpu, self.platform_info.docker_present,
        )
        self.config = load_config(self.app_root)
        self.logger.info(
            "config: app_root=%s api_port=%s gpu=%s llm_model=%s embed_model=%s",
            self.app_root, self.config.api_port, self.config.gpu,
            self.config.llm_model, self.config.embed_model,
        )
        self.backend = _make_backend(self.app_root, self.config, self.platform_info)
        self.logger.info("backend: %s", type(self.backend).__name__)

        self._views: dict[str, tk.Widget] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._active = None

        self._build_shell(fonts)
        self._show("dashboard")

    def _set_icon(self) -> None:
        icon_path = ASSETS_DIR / "icon.png"
        if icon_path.is_file():
            try:
                self._icon_image = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self._icon_image)
            except tk.TclError:
                pass  # icon is cosmetic only — never block startup on it

    # ---- shell layout -----------------------------------------------------
    def _build_shell(self, fonts: dict[str, str]) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=0, width=220)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        brand = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(16, 16))
        brand.pack(fill="x")
        ttk.Label(brand, text="DFFRNT", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text="AI Assistant — Control Panel", style="SidebarMuted.TLabel").pack(anchor="w")

        nav = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(8, 16))
        nav.pack(fill="x")
        self._add_nav(nav, "dashboard", "Dashboard")
        self._add_nav(nav, "logs", "Logs")

        ttk.Frame(sidebar, style="Sidebar.TFrame").pack(fill="both", expand=True)  # spacer

        footer = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(16, 12))
        footer.pack(fill="x", side="bottom")
        ttk.Label(footer, text=f"{self.platform_info.os.value} · {self.platform_info.pathway.value}",
                  style="SidebarMuted.TLabel").pack(anchor="w")

        main = ttk.Frame(self, style="App.TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        topbar = ttk.Frame(main, style="Topbar.TFrame", padding=(20, 14))
        topbar.grid(row=0, column=0, sticky="ew")
        self._topbar_title = ttk.Label(topbar, text="Dashboard", style="TopbarTitle.TLabel")
        self._topbar_title.pack(side="left")

        self._content = ttk.Frame(main, style="App.TFrame")
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=1)

        self._views["dashboard"] = DashboardView(self._content, self.platform_info, self.config, self.backend)
        self._views["logs"] = LogsView(self._content, self.backend)
        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

    def _add_nav(self, parent: tk.Misc, key: str, label: str) -> None:
        btn = ttk.Button(parent, text=label, style="Nav.TButton", command=lambda: self._show(key))
        btn.pack(fill="x", pady=2)
        self._nav_buttons[key] = btn

    def _show(self, key: str) -> None:
        if self._active == key:
            return
        if self._active == "logs":
            self._views["logs"].on_hide()
        for k, btn in self._nav_buttons.items():
            btn.configure(style="NavActive.TButton" if k == key else "Nav.TButton")
        self._views[key].tkraise()
        self._topbar_title.configure(text=key.capitalize())
        self._active = key


def main() -> None:
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
