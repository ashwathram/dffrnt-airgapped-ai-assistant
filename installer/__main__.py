"""Entry point, for both `python -m installer` and the frozen
dffrnt-manager binary PyInstaller builds from this file (deploy/package.sh).

Bare launch -> serve the browser control panel (installer/web) and open it.
Any argument -> the headless CLI (cli.py). One artifact covers a desktop
operator (browser UI) and an SSH'd box (CLI, or `panel --no-browser` +
port forward) — the view layer is the browser, so nothing about the UI is
platform-specific.

Absolute imports only: PyInstaller analyzes this file as a top-level script
(no package context), where relative imports would break.
"""

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv:
        from installer.cli import run_cli
        raise SystemExit(run_cli(argv))
    from installer.web.server import serve
    serve(open_browser=True)


if __name__ == "__main__":
    main()
