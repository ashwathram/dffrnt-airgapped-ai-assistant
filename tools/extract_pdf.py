from pathlib import Path
import sys
try:
    from PyPDF2 import PdfReader
except Exception:
    raise

# Allow passing a PDF path as the first argument; otherwise use the default
default_pdf = Path(__file__).resolve().parents[1] / 'Docs_to Help_Guide_Implementation' / 'DFFRNT Pitch Presentation.pdf'
pdf_arg = sys.argv[1] if len(sys.argv) > 1 else None
pdf_path = Path(pdf_arg) if pdf_arg else default_pdf

if not pdf_path.exists():
    print(f"PDF not found: {pdf_path}")
    raise SystemExit(2)

reader = PdfReader(str(pdf_path))
text = []
for p in reader.pages:
    t = p.extract_text()
    if t:
        text.append(t)
full = "\n\n".join(text)
# Print first 3000 chars to avoid huge output
print(full[:3000])
