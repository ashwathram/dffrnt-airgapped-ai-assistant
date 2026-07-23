"""Subprocess plumbing shared by backends. No tkinter import here — this
module knows nothing about the GUI; it just runs commands and hands lines
back through plain callables/queues that a Tk view can poll safely.

Tkinter widgets may only be touched from the main thread, so anything that
runs a subprocess to completion (which can take minutes, e.g. pulling a
model) must do so off the main thread. BackgroundJob is the bridge: it runs
a Backend verb in a worker thread and buffers its output in a queue.Queue
for the view to drain via `widget.after(...)`.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import urllib.request
from typing import Callable

OutputCallback = Callable[[str], None]


class CommandError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int, stderr: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr.strip()
        msg = f"command failed ({returncode}): {' '.join(cmd)}"
        # The exit code alone is useless to an operator ("docker info returned
        # 1" — why?). Docker et al. put the actual reason on stderr ("Cannot
        # connect to the Docker daemon ... Is the docker daemon running?"), so
        # fold it into the message every wrapper and log line already shows.
        if self.stderr:
            msg += f"\n{self.stderr}"
        super().__init__(msg)


def run_command(
    cmd: list[str],
    on_output: OutputCallback,
    *,
    cwd=None,
    env=None,
    input_text: str | None = None,
    check: bool = True,
) -> int:
    """Run `cmd` to completion, streaming merged stdout/stderr to on_output
    one line at a time. Blocks the calling thread — call from a worker
    thread (e.g. inside a BackgroundJob), never from the Tk main thread.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if input_text is not None:
        assert proc.stdin is not None
        proc.stdin.write(input_text)
        proc.stdin.close()
    assert proc.stdout is not None
    for line in proc.stdout:
        on_output(line.rstrip("\n"))
    returncode = proc.wait()
    if check and returncode != 0:
        raise CommandError(cmd, returncode)
    return returncode


def run_capture(cmd: list[str], *, cwd=None, env=None, timeout: float | None = 15) -> str:
    """Run `cmd`, wait for it, and return stripped stdout. For quick,
    non-streaming lookups (prereq checks, `docker inspect`, ...).

    On a non-zero exit, raises CommandError carrying the command's stderr —
    unlike subprocess's own check=True, whose CalledProcessError message
    drops stderr and leaves only an opaque exit code.
    """
    result = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise CommandError(cmd, result.returncode, result.stderr)
    return result.stdout.strip()


def probe_http(url: str, timeout: float = 2.0) -> bool:
    """True if `url` responds to a GET without raising — the stack's
    `curl -sf`-style health probe."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


class BackgroundJob:
    """Runs `fn(on_output)` in a daemon thread; on_output pushes lines into
    a thread-safe queue this job exposes via `drain()`. Meant to be polled
    from Tk with `widget.after(interval_ms, poll)`::

        job = BackgroundJob(backend.start).start()
        def poll():
            for line in job.drain():
                console.append(line)
            if job.done.is_set():
                if job.error is not None:
                    show_error(job.error)
                return
            widget.after(100, poll)
        widget.after(100, poll)
    """

    def __init__(self, fn: Callable[[OutputCallback], None]):
        self._fn = fn
        self._lines: queue.Queue[str] = queue.Queue()
        self.done = threading.Event()
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "BackgroundJob":
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self._fn(self._lines.put)
        except BaseException as exc:  # surfaced to the GUI via .error, never swallowed
            self.error = exc
        finally:
            self.done.set()

    def drain(self) -> list[str]:
        lines = []
        while True:
            try:
                lines.append(self._lines.get_nowait())
            except queue.Empty:
                break
        return lines


class LogFollower:
    """Wraps a long-lived, never-exiting command (`docker compose logs -f`)
    so a view can start following and later stop on demand — unlike
    BackgroundJob, which represents a command expected to finish."""

    def __init__(self, cmd: list[str], *, cwd=None, env=None):
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        assert self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._lines.put(line.rstrip("\n"))
        finally:
            self._lines.put(None)  # sentinel: process exited / stream ended

    def drain(self) -> tuple[list[str], bool]:
        """Returns (new_lines, ended)."""
        lines: list[str] = []
        ended = False
        while True:
            try:
                item = self._lines.get_nowait()
            except queue.Empty:
                break
            if item is None:
                ended = True
                break
            lines.append(item)
        return lines, ended

    def stop(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
