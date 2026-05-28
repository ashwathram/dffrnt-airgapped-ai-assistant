# Running the DFFRNT Air-Gapped Assistant (Local Developer Guide)

This file explains how to set up a developer environment and run the repository locally.

Prerequisites
- Windows (PowerShell recommended)
- `python` (we use the project venv, created with Python 3.14)
- `ffmpeg` on PATH (if you plan to work with audio)

Create and activate the venv (already configured for Python 3.14 in this workspace):

```powershell
# create venv (if needed)
py -3.14 -m venv .venv
# activate in PowerShell
& ".\ .venv\Scripts\Activate.ps1"
# upgrade pip
python -m pip install --upgrade pip setuptools wheel
```

Install dependencies

```powershell
# if a requirements.txt is present
pip install -r requirements.txt
```

Quick checks
- Extract the pitch PDF (example extractor):

```powershell
python tools\extract_pdf.py "Docs_to Help_Guide_Implementation\DFFRNT Pitch Presentation.pdf"
```

- Run tests:

```powershell
python -m pytest -q
```

- Run a minimal demo or ingestion flow (TBD): follow `ARCHITECTURE.md` for component wiring.

Notes for air-gapped deploys
- Pre-download all Python wheels and model artifacts before moving to the isolated network.
- Store model binaries under `models/` and data under `data/` as described in `ARCHITECTURE.md`.

If you encounter activation policy errors in PowerShell, run the commands with the venv Python directly (no activation):

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```