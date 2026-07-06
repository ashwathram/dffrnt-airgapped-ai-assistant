"""Reset the live knowledge base to the synthetic evaluation corpus.

Deletes every document currently in the KB through the API (which removes both
the stored file and its chunks), then uploads each file from eval/corpus/ with
its tags and description — the same code path a real upload takes, so ingestion
itself is part of what gets evaluated.

Run from the repo root, with the app up:  python -m eval.ingest_corpus
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx as requests

API = "http://localhost:8000/api"
CORPUS_DIR = Path(__file__).parent / "corpus"

# filename -> (comma-separated tags, description)
UPLOADS = {
    "resume-amara-okafor.docx": ("Resume,Design", "Resume — Amara Okafor, Senior UX Designer"),
    "resume-ben-tremblay.docx": ("Resume,Engineering", "Resume — Ben Tremblay, Senior UI Developer"),
    "resume-chloe-nguyen.pdf": ("Resume,Research", "Resume — Chloe Nguyen, UX Researcher"),
    "resume-diego-ramirez.txt": ("Resume,Design", "Resume — Diego Ramirez, Product Designer"),
    "resume-elena-petrova.docx": ("Resume,Design", "Resume — Elena Petrova, Service Designer"),
    "proposal-aurora-patient-portal.docx": ("Proposal,Client Related", "Aurora Health patient portal redesign proposal"),
    "proposal-borealis-rebrand.md": ("Proposal,Client Related", "Borealis Museums brand & web refresh proposal"),
    "correspondence-aurora-timeline.txt": ("Correspondence,Client Related", "Aurora Health email thread on timeline compression"),
    "policy-contractor-onboarding.md": ("Policy,HR", "Contractor onboarding and rate-band policy"),
    "policy-benefits-summary.docx": ("Policy,HR", "Employee benefits summary"),
    "faq-security-airgap.txt": ("Policy,Internal", "Security & air-gap deployment FAQ"),
    "capabilities-overview.pptx": ("Internal,Marketing", "DFFRNT capabilities overview deck"),
    "contractor-roster.xlsx": ("Resume,HR", "Contractor roster with rates and availability"),
    "project-hours-q1-2026.csv": ("Internal,Data", "Project hours logged in Q1 2026"),
}


def wipe() -> None:
    docs = requests.get(f"{API}/documents", timeout=30).json()["documents"]
    for doc in docs:
        name = doc["filename"]
        r = requests.delete(f"{API}/documents/{name}", timeout=60)
        print(f"  deleted {name}: {r.status_code}")
    if not docs:
        print("  (already empty)")


def upload_all() -> bool:
    ok = True
    for name, (tags, description) in UPLOADS.items():
        path = CORPUS_DIR / name
        if not path.exists():
            print(f"  !! missing {name} — run `python -m eval.gen_corpus` first")
            ok = False
            continue
        with path.open("rb") as fh:
            r = requests.post(
                f"{API}/upload",
                files={"file": (name, fh)},
                data={"tags": tags, "description": description, "force": "true"},
                timeout=600,
            )
        body = r.json()
        if r.status_code == 200 and body.get("success"):
            print(f"  {name}: {body['chunks']} chunks  (tags: {tags})")
        else:
            print(f"  !! {name}: HTTP {r.status_code} {body}")
            ok = False
    return ok


def main() -> None:
    print("== wiping current KB ==")
    wipe()
    print("== uploading corpus ==")
    ok = upload_all()
    docs = requests.get(f"{API}/documents", timeout=30).json()
    print(f"== done: {docs['document_count']} documents, {docs['total_chunks']} chunks ==")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
