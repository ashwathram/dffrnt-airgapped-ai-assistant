"""Central logging for the installer GUI.

Every lifecycle operation a Backend performs — start, stop, restart,
check_prerequisites, reingest_preview/apply, and (once phase 2 lands) the
install/provisioning flow — writes its full streamed output plus a clear
begin/end/error marker to a log file, so a failure survives after the GUI
console scrolls away or the window closes.

Deliberately NOT logged per-line: status() polling and stream_logs()
follow output. Both are read-only, high-frequency (status is re-polled
after every action; log-follow can run indefinitely), and already fully
visible live in the GUI — status in the Services card, logs in the Logs
view. stream_logs in particular would just duplicate `docker compose
logs`, which Docker already persists on its own. Logging them here would
mean an unbounded file for zero new information. See docker_backend.py's
`with_logging` usage for exactly which methods opt in.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

LOGGER_NAME = "dffrnt.installer"


def configure_logging(app_root: Path, *, verbose: bool = True) -> logging.Logger:
    """Idempotent — safe to call more than once (e.g. in tests); only the
    first call attaches handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    log_dir = app_root / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "installer.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        # app_root/logs isn't writable (e.g. a read-only checkout) — fall
        # back to the OS temp dir rather than crash the GUI over logging.
        log_path = Path(tempfile.gettempdir()) / "dffrnt-installer.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    logger.addHandler(stream_handler)

    logger.info("logging to %s", log_path)
    return logger


def get_logger() -> logging.Logger:
    """The configured logger, or a no-op default if configure_logging()
    hasn't run yet (e.g. a module imported and used outside the GUI)."""
    return logging.getLogger(LOGGER_NAME)


def with_logging(stage: str, on_output):
    """Wraps an OutputCallback so every line it receives is also written
    to the log file at DEBUG, tagged with `stage` (e.g. "start",
    "reingest.apply"). Use for any Backend method whose output should
    survive the GUI console."""
    logger = get_logger()

    def wrapped(line: str) -> None:
        logger.debug("[%s] %s", stage, line)
        on_output(line)

    return wrapped
