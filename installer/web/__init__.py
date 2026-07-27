"""Browser-rendered control panel: a stdlib HTTP server (server.py) that
drives the same Backend/Installer/model_store layer the CLI does, plus the
static HTML/CSS/JS it serves (static/). The browser is the view layer —
no Tk, no Qt, nothing to freeze per-platform for the UI itself."""
