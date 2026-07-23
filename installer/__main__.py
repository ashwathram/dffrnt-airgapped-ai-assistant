"""Entry point, for both `python -m installer` and the frozen
dffrnt-manager binary PyInstaller builds from this file (deploy/package.sh).

Bare launch -> the Tk GUI. Any argument -> the headless CLI (cli.py), which
never imports tkinter — that's what lets one binary serve a desktop operator
and an SSH'd AWS box alike.

Absolute imports only: PyInstaller analyzes this file as a top-level script
(no package context), where relative imports would break.
"""

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv:
        from installer.cli import run_cli
        raise SystemExit(run_cli(argv))
    try:
        from installer.app import main as gui_main
    except ImportError as exc:  # most likely: no tkinter on a headless box
        print(f"!! Could not load the GUI ({exc}).\n"
              "   This looks like a headless machine — run a command instead, "
              "e.g.: status, start, install --help", file=sys.stderr)
        raise SystemExit(1)
    try:
        gui_main()
    except Exception as exc:
        # A Tk init failure on a displayless session lands here (TclError).
        print(f"!! Could not open a window ({exc}).\n"
              "   No display available? Every operation is also a CLI command — "
              "try: status, start, models, install --help", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
