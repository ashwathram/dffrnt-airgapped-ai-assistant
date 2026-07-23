"""Models view: switch the active LLM, and move models on/off the machine
as tarballs — the air-gapped answer to `ollama pull`.

The flow this tab exists for:

  networked machine:  Export card — pull (if needed) + pack manifest/blobs
                      into one uncompressed tar on a USB drive
  air-gapped machine: Import card — checksum-verified merge into the store,
                      then the model appears in the picker; Apply & restart
                      rewrites config.toml's llm_model and restarts the
                      stack (start's ensure/prune does the rest)

Switching is LLM-only by design: swapping embed_model changes the vector
dimension and demands a full re-ingest, so it stays a deliberate
config.toml edit (see config.toml's own comments).
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import model_store, widgets
from ..backends import Backend
from ..config import AppConfig, find_config, write_config_value
from ..platform_detect import PlatformInfo
from ..process import BackgroundJob


class ModelsView(ttk.Frame):
    def __init__(self, parent: tk.Misc, platform_info: PlatformInfo,
                 config: AppConfig, backend: Backend, app_root: Path,
                 on_config_changed):
        super().__init__(parent, style="App.TFrame", padding=20)
        self.platform_info = platform_info
        self.config = config
        self.backend = backend
        self.app_root = app_root
        self.on_config_changed = on_config_changed  # callback() -> None, set by app shell
        self._job = None
        self._on_success = None
        self._busy = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._scroll = widgets.ScrollableFrame(self, style="App.TFrame")
        self._scroll.grid(row=0, column=0, sticky="nsew")
        self._body = self._scroll.body
        self._body.configure(padding=20)
        self._body.columnconfigure(0, weight=1)

        self._build_swap_card()
        self._build_installed_card()
        self._build_import_card()
        self._build_export_card()
        self._build_console()

        self._refresh_all()

    # ---- shell hooks ------------------------------------------------------
    def on_show(self) -> None:
        self._scroll.enable_wheel()
        if not self._busy:
            self._refresh_all()

    def on_hide(self) -> None:
        self._scroll.disable_wheel()

    def set_backend(self, backend: Backend, config: AppConfig, app_root: Path) -> None:
        """Re-point at a (re)installed stack or a reloaded config (see
        DashboardView.set_backend / app shell)."""
        self.backend = backend
        self.config = config
        self.app_root = app_root
        self._refresh_all()

    # ---- layout -----------------------------------------------------------
    def _build_swap_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(1, weight=1)

        ttk.Label(c, text="Active model", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=3)
        self._swap_hint = ttk.Label(c, text="", style="Muted.TLabel",
                                    wraplength=640, justify="left")
        self._swap_hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 10))

        ttk.Label(c, text="LLM", style="CardBody.TLabel").grid(row=2, column=0, sticky="w")
        self._swap_var = tk.StringVar()
        self._swap_combo = ttk.Combobox(c, textvariable=self._swap_var)
        self._swap_combo.grid(row=2, column=1, sticky="ew", padx=8)
        self._apply_btn = widgets.primary_button(c, "Apply & restart", self._on_apply)
        self._apply_btn.grid(row=2, column=2, sticky="e")

        self._embed_label = ttk.Label(c, text="", style="Muted.TLabel",
                                      wraplength=640, justify="left")
        self._embed_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        if not self.platform_info.pathway_implemented:
            self._apply_btn.state(["disabled"])

    def _build_installed_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(0, weight=1)

        head = ttk.Frame(c, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Installed models", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w")
        widgets.ghost_button(head, "Refresh", self._refresh_all).grid(row=0, column=1, sticky="e")

        self._model_rows = ttk.Frame(c, style="Card.TFrame")
        self._model_rows.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._model_rows.columnconfigure(1, weight=1)

    def _build_import_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(1, weight=1)

        ttk.Label(c, text="Import a model from a tarball", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=3)
        ttk.Label(
            c, text="Merge a model archive exported on a networked machine (see Export "
                    "below) into this machine's store. Contents are checksum-verified "
                    "before anything is placed; imported models are kept until you "
                    "delete them or switch to them.",
            style="Muted.TLabel", wraplength=640, justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 10))

        ttk.Label(c, text="Tarball", style="CardBody.TLabel").grid(row=2, column=0, sticky="w")
        self._import_var = tk.StringVar()
        ttk.Entry(c, textvariable=self._import_var).grid(row=2, column=1, sticky="ew", padx=8)
        widgets.ghost_button(c, "Browse…", self._on_browse_import).grid(row=2, column=2, sticky="e")

        self._import_btn = widgets.primary_button(c, "Import", self._on_import)
        self._import_btn.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
        if not self.platform_info.pathway_implemented:
            self._import_btn.state(["disabled"])

    def _build_export_card(self) -> None:
        c = widgets.card(self._body)
        c.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        c.columnconfigure(1, weight=1)

        ttk.Label(c, text="Export a model to a tarball", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=3)
        self._export_hint = ttk.Label(c, text="", style="Muted.TLabel",
                                      wraplength=640, justify="left")
        self._export_hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 10))

        ttk.Label(c, text="Model", style="CardBody.TLabel").grid(row=2, column=0, sticky="w")
        self._export_var = tk.StringVar()
        self._export_combo = ttk.Combobox(c, textvariable=self._export_var)
        self._export_combo.grid(row=2, column=1, sticky="ew", padx=8)
        self._export_btn = widgets.primary_button(c, "Export…", self._on_export)
        self._export_btn.grid(row=2, column=2, sticky="e")
        if not self.platform_info.pathway_implemented:
            self._export_btn.state(["disabled"])

    def _build_console(self) -> None:
        ttk.Label(self._body, text="Output", style="MutedApp.TLabel").grid(
            row=4, column=0, sticky="w")
        wrap = ttk.Frame(self._body, style="Card.TFrame", padding=1)
        wrap.grid(row=5, column=0, sticky="nsew", pady=(4, 0))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self._console = widgets.console(wrap, height=14)
        self._console.grid(row=0, column=0, sticky="nsew")

    # ---- refresh ----------------------------------------------------------
    def _offline(self) -> bool:
        return getattr(self.backend, "target_system", "online") == "offline"

    def _refresh_all(self) -> None:
        try:
            infos = self.backend.list_models()
        except Exception:
            infos = []
        self._refresh_swap(infos)
        self._refresh_installed(infos)
        self._refresh_export(infos)

    def _refresh_swap(self, infos: list[model_store.ModelInfo]) -> None:
        embed = model_store.with_tag(self.config.embed_model) if self.config.embed_model else ""
        candidates = [
            i.name for i in infos
            if i.name != embed and not model_store.looks_like_embedder(i.name)
        ]
        current = self.config.llm_model
        if current and current not in candidates \
                and model_store.with_tag(current) not in candidates:
            candidates.insert(0, current)
        self._swap_combo.configure(values=candidates)
        if not self._swap_var.get():
            self._swap_var.set(current)

        if self._offline():
            # Air-gapped: only what is physically in the store is selectable.
            self._swap_combo.configure(state="readonly")
            self._swap_hint.configure(
                text="Pick from the models in this machine's store and Apply & restart. "
                     "This is an offline deployment: new models arrive via Import below, "
                     "never by pulling. The previous model is removed at restart to "
                     "reclaim disk (getting it back needs a re-import or re-install).")
        else:
            self._swap_combo.configure(state="normal")
            self._swap_hint.configure(
                text="Pick an installed model — or type any Ollama model name (e.g. "
                     "qwen3:8b) to pull it during the restart. The previous model is "
                     "removed at restart to reclaim disk.")
        self._embed_label.configure(
            text=f"Embedder: {self.config.embed_model or '(unset)'} — switching it "
                 "requires a full re-ingest, so it is deliberately config.toml-only.")

    def _refresh_installed(self, infos: list[model_store.ModelInfo]) -> None:
        for child in self._model_rows.winfo_children():
            child.destroy()
        if not infos:
            ttk.Label(self._model_rows,
                      text="No models in the store yet"
                           + (" — import one below." if self._offline()
                              else " — they arrive on first start (pull) or via Import."),
                      style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            return
        llm = model_store.with_tag(self.config.llm_model) if self.config.llm_model else ""
        embed = model_store.with_tag(self.config.embed_model) if self.config.embed_model else ""
        kept = {model_store.with_tag(n) for n in model_store.read_keep_file(self.app_root)}
        for row, info in enumerate(infos):
            if info.name == llm:
                pill, text = ("ok", "LLM")
            elif info.name == embed:
                pill, text = ("ok", "embedder")
            elif info.name in kept:
                pill, text = ("muted", "imported")
            else:
                pill, text = ("warn", "prunes on restart")
            widgets.status_pill(self._model_rows, pill, text).grid(
                row=row, column=0, sticky="w", pady=2)
            ttk.Label(self._model_rows,
                      text=f"{info.name}  ·  {model_store.human_size(info.size_bytes)}",
                      style="CardBody.TLabel").grid(row=row, column=1, sticky="w",
                                                    padx=(8, 0), pady=2)
            if info.name not in (llm, embed) and self.platform_info.pathway_implemented:
                widgets.ghost_button(
                    self._model_rows, "Delete",
                    lambda name=info.name: self._on_delete(name),
                ).grid(row=row, column=2, sticky="e", pady=2)

    def _refresh_export(self, infos: list[model_store.ModelInfo]) -> None:
        self._export_combo.configure(values=[i.name for i in infos])
        if self._offline():
            self._export_combo.configure(state="readonly")
            self._export_hint.configure(
                text="Pack a model from this store into a single .tar for another "
                     "machine. (Offline deployment: only already-present models can "
                     "be exported.)")
        else:
            self._export_combo.configure(state="normal")
            self._export_hint.configure(
                text="Run this on the NETWORKED staging machine: pick an installed "
                     "model or type any Ollama name — it is pulled first if absent "
                     "(the stack must be started) — then packed into a single .tar "
                     "to carry to the air-gapped machine on a USB drive. Plain tar, "
                     "uncompressed: model weights don't compress. The drive must not "
                     "be FAT32 (4 GiB file limit); use exFAT.")

    # ---- job plumbing (same pattern as DashboardView) ----------------------
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy or self.platform_info.pathway_implemented:
            state = "disabled" if busy else "!disabled"
            for btn in (self._apply_btn, self._import_btn, self._export_btn):
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
            if job.error is not None:
                widgets.console_append(self._console, [f"!! {job.error}"])
            self._refresh_all()
            if job.error is None and on_success is not None:
                on_success()
            return
        self.after(150, self._poll_job)

    # ---- actions ----------------------------------------------------------
    def _on_apply(self) -> None:
        if self._busy:
            return
        name = self._swap_var.get().strip()
        if not name:
            messagebox.showerror("No model selected", "Pick or enter a model first.",
                                 parent=self)
            return
        try:
            model_store.name_to_manifest_rel(name)  # syntax check only
        except model_store.ModelStoreError as exc:
            messagebox.showerror("Invalid model name", str(exc), parent=self)
            return
        current = self.config.llm_model
        if model_store.with_tag(name) == model_store.with_tag(current or "-"):
            messagebox.showinfo("No change", f"{name} is already the active LLM.",
                                parent=self)
            return
        config_path = find_config(self.app_root)
        if config_path is None:
            messagebox.showerror(
                "No config.toml found",
                f"No config.toml under {self.app_root} — is the stack installed?",
                parent=self)
            return
        present = any(model_store.with_tag(name) == model_store.with_tag(i.name)
                      for i in self.backend.list_models())
        if self._offline() and not present:
            messagebox.showerror(
                "Model not in the store",
                f"'{name}' is not in this machine's store, and an offline deployment "
                "cannot pull. Import it from a tarball first.", parent=self)
            return

        kept = {model_store.with_tag(n)
                for n in model_store.read_keep_file(self.app_root)}
        old_pruned = current and model_store.with_tag(current) not in kept
        lines = [f"Switch the active LLM from {current or '(unset)'} to {name}?", ""]
        if not present:
            lines.append(f"• {name} is not cached yet — it will be pulled during the "
                         "restart (needs network).")
        if old_pruned:
            lines.append(f"• {current} will be REMOVED from the store at restart to "
                         "reclaim disk"
                         + (" — on this offline machine, getting it back later "
                            "means importing it again from a tarball." if self._offline()
                            else "."))
        lines.append("• The stack restarts now; the assistant is briefly unavailable.")
        if not messagebox.askyesno("Confirm model switch", "\n".join(lines), parent=self):
            return

        write_config_value(config_path, "llm_model", name)
        widgets.console_append(self._console, [f">> config.toml: llm_model = \"{name}\""])
        if os.environ.get("LLM_MODEL"):
            widgets.console_append(self._console, [
                "!! LLM_MODEL is set in this environment and overrides config.toml — "
                "the running stack may not pick up this change."])
        # If the switched-to model was an import, it is now config-referenced;
        # drop it from the keep file so a later switch away reclaims its disk.
        model_store.remove_from_keep_file(self.app_root, name)
        self.on_config_changed()  # app shell reloads config + rebuilds backends
        self._run_action("restart (apply model)", self.backend.restart)

    def _on_delete(self, name: str) -> None:
        if self._busy:
            return
        if not messagebox.askyesno(
                "Delete model",
                f"Remove {name} from this machine's store?"
                + ("\n\nThis is an offline deployment — getting it back requires "
                   "another tarball import." if self._offline() else ""),
                parent=self):
            return
        self._run_action(f"delete {name}",
                         lambda out: self.backend.delete_model(out, name))

    def _on_browse_import(self) -> None:
        picked = filedialog.askopenfilename(
            parent=self, title="Select a model archive",
            filetypes=[("Model archive", "*.tar"), ("All files", "*")],
        )
        if picked:
            self._import_var.set(picked)

    def _on_import(self) -> None:
        if self._busy:
            return
        raw = self._import_var.get().strip()
        if not raw:
            messagebox.showerror("No tarball selected",
                                 "Browse to a model archive first.", parent=self)
            return
        tar_path = Path(raw)
        self._run_action(
            f"import {tar_path.name}",
            lambda out: self.backend.import_model_tar(out, tar_path),
            on_success=lambda: widgets.console_append(self._console, [
                ">> Select it under Active model and Apply & restart to use it."]),
        )

    def _on_export(self) -> None:
        if self._busy:
            return
        name = self._export_var.get().strip()
        if not name:
            messagebox.showerror("No model selected", "Pick or enter a model first.",
                                 parent=self)
            return
        try:
            model_store.name_to_manifest_rel(name)
        except model_store.ModelStoreError as exc:
            messagebox.showerror("Invalid model name", str(exc), parent=self)
            return
        suggested = name.replace("/", "-").replace(":", "-") + ".ollama.tar"
        picked = filedialog.asksaveasfilename(
            parent=self, title="Save model archive as", initialfile=suggested,
            defaultextension=".tar",
            filetypes=[("Model archive", "*.tar"), ("All files", "*")],
        )
        if not picked:
            return
        dest = Path(picked)
        self._run_action(
            f"export {name} -> {dest.name}",
            lambda out: self.backend.export_model(out, name, dest),
        )
