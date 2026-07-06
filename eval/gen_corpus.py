"""Generate the synthetic evaluation corpus into eval/corpus/.

Every document is written from scratch with *controlled ground truth*: each fact
checked by eval/sample_queries.py appears verbatim here and nowhere else, so
correctness scoring is unambiguous. The corpus mirrors the three tasks the
assistant must serve (resume/HR extraction, proposal & correspondence Q&A,
internal knowledge-base interrogation) and covers all seven supported formats
(pdf, docx, pptx, xlsx, csv, txt, md).

Run from the repo root:  python -m eval.gen_corpus
Then upload with:        python -m eval.ingest_corpus
"""

from __future__ import annotations

from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"

# ---------------------------------------------------------------------------
# Resumes (task 1: HR extraction + multi-candidate aggregation).
# Deliberately similar in structure — retrieval must discriminate between them.
# Ground-truth design: Figma appears ONLY in Okafor + Ramírez; the highest rate
# is Petrova ($105) and the lowest Ramírez ($70); the only PhD is Nguyen.
# ---------------------------------------------------------------------------

RESUMES = {
    "resume-amara-okafor.docx": {
        "title": "Amara Okafor",
        "sections": [
            ("Profile",
             "Senior UX Designer with nine years of experience leading design for "
             "financial-services and e-commerce products. Ottawa, Ontario. "
             "Contract hourly rate: $95/hour. amara.okafor@example.com"),
            ("Experience",
             "Lumen Digital — Senior UX Designer, 2019–2024. Led the end-to-end "
             "redesign of a retail-banking mobile app used by 1.2 million customers; "
             "the redesign raised the app's NPS from 31 to 58 within a year. Managed "
             "a team of 6 designers and ran quarterly usability benchmarks.\n\n"
             "Craft&Pixel Studio — UX Designer, 2016–2019. Built and maintained "
             "design systems for three e-commerce clients; introduced design tokens "
             "and cut design-to-dev handoff time by a third."),
            ("Skills",
             "Figma, design tokens, design systems, WCAG 2.2 accessibility, "
             "usability testing, journey mapping, stakeholder workshops."),
            ("Education",
             "Master of Design (MDes), Carleton University, 2016."),
        ],
    },
    "resume-ben-tremblay.docx": {
        "title": "Ben Tremblay",
        "sections": [
            ("Profile",
             "Senior UI Developer specialising in design-system engineering. "
             "Montréal, Québec. Contract hourly rate: $80/hour. "
             "ben.tremblay@example.com"),
            ("Experience",
             "Nova Interfaces — Senior UI Developer, 2021–2025. Built the React and "
             "TypeScript component library that 14 product teams adopted as their "
             "design system; the shared components cut UI defect reports by 40%. "
             "Owned the Storybook documentation and the visual-regression pipeline.\n\n"
             "Hydro-Québec — Front-End Developer, 2018–2021. Developed internal "
             "operations dashboards for grid monitoring in React and D3."),
            ("Skills",
             "React, TypeScript, Storybook, Tailwind CSS, accessibility testing, "
             "visual regression testing, CI/CD."),
            ("Education",
             "B.Eng. Software Engineering, Polytechnique Montréal, 2018."),
        ],
    },
    "resume-elena-petrova.docx": {
        "title": "Elena Petrova",
        "sections": [
            ("Profile",
             "Service Designer focused on public-sector service transformation. "
             "Toronto, Ontario. Contract hourly rate: $105/hour. "
             "elena.petrova@example.com"),
            ("Experience",
             "GovConnect Agency — Lead Service Designer, 2019–2025. Redesigned a "
             "municipal permit application service end to end; average processing "
             "time fell from 21 days to 6 days and call-centre volume dropped by "
             "half. Facilitated co-design sessions with residents and case officers.\n\n"
             "Sberbank Digital — Service Designer, 2015–2019. Mapped and redesigned "
             "onboarding journeys for retail banking products."),
            ("Skills",
             "Service blueprinting, journey mapping, co-design facilitation, "
             "prototyping, qualitative research, stakeholder alignment."),
            ("Education",
             "MA Service Design, Royal College of Art, 2015."),
        ],
    },
}

RESUME_PDF = {
    "resume-chloe-nguyen.pdf": (
        "Chloe Nguyen\n"
        "UX Researcher — Ottawa, Ontario\n"
        "chloe.nguyen@example.com | Contract hourly rate: $90/hour\n\n"
        "PROFILE\n"
        "Mixed-methods UX researcher with a track record of turning research into "
        "measurable product improvements in enterprise software.\n\n"
        "EXPERIENCE\n"
        "MapleSoft Insights — UX Researcher, 2020–2025\n"
        "- Ran more than 120 moderated usability sessions across four product lines.\n"
        "- Research-driven redesigns raised first-attempt task success from 62% to 88%.\n"
        "- Built the company's research repository and tagging taxonomy.\n\n"
        "Statistics Canada — Research Co-op, 2019\n"
        "- Supported survey design and cognitive interviewing for household surveys.\n\n"
        "SKILLS\n"
        "Usability testing, eye tracking, survey design, diary studies, R, "
        "thematic analysis.\n\n"
        "EDUCATION\n"
        "PhD Human-Computer Interaction, University of Ottawa, 2020."
    ),
}

RESUME_TXT = {
    "resume-diego-ramirez.txt": (
        "DIEGO RAMIREZ\n"
        "Product Designer (contract) — Mexico City, remote-friendly\n"
        "diego.ramirez@example.com | Contract hourly rate: $70/hour\n"
        "Bilingual: Spanish and English\n"
        "\n"
        "PROFILE\n"
        "Product designer specialising in fintech onboarding and conversion flows.\n"
        "\n"
        "EXPERIENCE\n"
        "Kapital Fintech - Product Designer, 2022-2024\n"
        "Redesigned the account-opening onboarding flow; sign-up drop-off fell by 27%.\n"
        "Ran weekly design sprints with product and compliance stakeholders.\n"
        "\n"
        "Banorte - Design Lead, Mobile Banking, 2017-2022\n"
        "Led a five-person team shipping the retail mobile banking app.\n"
        "\n"
        "SKILLS\n"
        "Figma, rapid prototyping, design sprints, usability testing, "
        "conversion optimisation.\n"
        "\n"
        "EDUCATION\n"
        "BA Industrial Design, UNAM, 2016.\n"
    ),
}

# ---------------------------------------------------------------------------
# Proposals + correspondence (task 2).
# ---------------------------------------------------------------------------

PROPOSAL_DOCX = {
    "proposal-aurora-patient-portal.docx": {
        "title": "Aurora Health Patient Portal UX Redesign — Proposal",
        "sections": [
            ("Overview",
             "DFFRNT proposes a full UX redesign of the Aurora Health patient "
             "portal, covering appointment booking, test results, and secure "
             "messaging. Fixed price: $240,000. Duration: 16 weeks."),
            ("Team",
             "One engagement lead (Sofia Marchetti), two product designers, and "
             "one UX researcher, supported part-time by an accessibility "
             "specialist."),
            ("Phases",
             "Discovery — 4 weeks: stakeholder interviews, analytics review, and "
             "20 patient interviews.\n\n"
             "Design — 8 weeks: information architecture, design system build, and "
             "high-fidelity prototypes across web and mobile.\n\n"
             "Validation — 4 weeks: three rounds of moderated usability testing "
             "and an accessibility audit."),
            ("Deliverables",
             "Research findings report, a reusable design system, a WCAG 2.2 AA "
             "accessibility audit, and a clickable prototype covering the top "
             "eight patient tasks."),
            ("Success metrics",
             "Raise first-attempt task completion by 25% and reduce "
             "portal-related support calls by 30% within two quarters of launch."),
        ],
    },
}

PROPOSAL_MD = {
    "proposal-borealis-rebrand.md": (
        "# Borealis Museums Consortium — Brand & Web Refresh Proposal\n"
        "\n"
        "DFFRNT proposes a brand and web refresh for the Borealis Museums "
        "Consortium's four member museums.\n"
        "\n"
        "**Budget:** $85,000 fixed price. **Duration:** 8 weeks.\n"
        "\n"
        "## Deliverables\n"
        "\n"
        "- A flexible logo system that adapts to each member museum\n"
        "- A brand style guide covering typography, colour, and voice\n"
        "- A web component library implemented in the consortium's CMS\n"
        "- Three responsive page templates: exhibition, visit planning, donation\n"
        "\n"
        "## Optional add-on\n"
        "\n"
        "A WCAG accessibility audit of the existing web estate can be added for "
        "$12,000.\n"
        "\n"
        "## Assumptions\n"
        "\n"
        "Content migration is handled by the consortium's web team. DFFRNT "
        "delivers source files in Figma.\n"
    ),
}

CORRESPONDENCE_TXT = {
    "correspondence-aurora-timeline.txt": (
        "Subject: RE: Patient portal engagement — timeline question\n"
        "\n"
        "From: Dr. Priya Sharma (Aurora Health) | 2026-03-10\n"
        "To: Sofia Marchetti (DFFRNT)\n"
        "\n"
        "Sofia — our board wants the redesigned portal live before the summer "
        "clinic surge. Is there any way to compress the engagement from 16 weeks "
        "down to 12 weeks?\n"
        "\n"
        "---\n"
        "\n"
        "From: Sofia Marchetti (DFFRNT) | 2026-03-12\n"
        "To: Dr. Priya Sharma (Aurora Health)\n"
        "\n"
        "Priya — yes, with two changes. We can overlap the validation phase with "
        "design sprints 6 through 8, and we would add a second UX researcher so "
        "usability rounds run in parallel. The additional researcher adds $18,000, "
        "bringing the revised total to $258,000. Scope and deliverables are "
        "unchanged.\n"
        "\n"
        "---\n"
        "\n"
        "From: Dr. Priya Sharma (Aurora Health) | 2026-03-14\n"
        "To: Sofia Marchetti (DFFRNT)\n"
        "\n"
        "Approved — please proceed with the 12-week plan at $258,000. Our team "
        "will be ready for kickoff on 2026-04-01.\n"
    ),
}

# ---------------------------------------------------------------------------
# Internal knowledge base (task 3: policies, FAQ, company facts).
# ---------------------------------------------------------------------------

POLICY_MD = {
    "policy-contractor-onboarding.md": (
        "# Contractor Onboarding & Engagement Policy\n"
        "\n"
        "This policy governs how DFFRNT engages independent contractors for "
        "client work.\n"
        "\n"
        "## Screening\n"
        "\n"
        "Every contractor must sign the standard NDA and complete reliability "
        "screening within 10 business days of contract signature. Contractors "
        "must not access client materials before screening completes.\n"
        "\n"
        "## Rate bands\n"
        "\n"
        "Approved hourly rate bands:\n"
        "\n"
        "- Junior: up to $60/hour\n"
        "- Intermediate: $60–$90/hour\n"
        "- Senior: $90–$120/hour\n"
        "\n"
        "Rates above $120/hour require written approval from the managing "
        "partner.\n"
        "\n"
        "## Invoicing and duration\n"
        "\n"
        "Invoices are payable net-30. Timesheets are due every Friday in Harvest. "
        "A continuous engagement may not exceed 12 months without a conversion "
        "review by HR.\n"
    ),
}

POLICY_DOCX = {
    "policy-benefits-summary.docx": {
        "title": "Employee Benefits Summary",
        "sections": [
            ("Health",
             "All permanent employees receive a health spending account of "
             "$2,500 per year, plus standard extended health and dental "
             "coverage."),
            ("Time off",
             "The base vacation allowance is 4 weeks per year, rising to 5 weeks "
             "after five years of service. Offices close between December 25 and "
             "January 1."),
            ("Growth",
             "Each employee has a professional development budget of $1,800 per "
             "year for courses, conferences, or certifications."),
            ("Family",
             "Parental leave is topped up to 93% of salary for 18 weeks."),
            ("Ways of working",
             "Hybrid policy: a minimum of 2 days per week in the office, "
             "coordinated within each team."),
        ],
    },
}

FAQ_TXT = {
    "faq-security-airgap.txt": (
        "DFFRNT AI ASSISTANT — SECURITY & DEPLOYMENT FAQ\n"
        "\n"
        "Q: Where does client data live?\n"
        "A: All client documents stay on DFFRNT's on-premises server. Nothing is "
        "sent to any cloud service.\n"
        "\n"
        "Q: Does the assistant call external AI APIs?\n"
        "A: No. The language model and the embedding model both run locally on "
        "the same air-gapped machine. The deployment has no internet access.\n"
        "\n"
        "Q: How long are documents retained?\n"
        "A: Uploaded documents and their derived index are retained for 7 years, "
        "in line with the client-records retention schedule.\n"
        "\n"
        "Q: Who do I contact about a suspected security incident?\n"
        "A: Email security@dffrnt.example within 24 hours of discovery. The "
        "on-call security lead triages all reports.\n"
    ),
}

CAPABILITIES_PPTX = {
    "capabilities-overview.pptx": [
        ("DFFRNT — Capabilities Overview",
         "A design consultancy for regulated industries."),
        ("Who we are",
         "Founded in 2015 in Ottawa. 38 employees across two offices: Ottawa "
         "and Toronto. Independent and founder-owned."),
        ("Sectors",
         "Healthcare, government, and financial services. Long-term engagements "
         "with provincial health agencies and two of Canada's five largest "
         "banks."),
        ("Selected results",
         "Retail banking app NPS up 27 points after redesign. Municipal permit "
         "processing time cut from 21 days to 6. Patient portal task completion "
         "up 25%."),
        ("Services",
         "Product design, service design, UX research, design systems, "
         "accessibility audits, and private AI knowledge tools."),
    ],
}

ROSTER_XLSX = {
    "contractor-roster.xlsx": {
        "sheet": "Roster",
        "rows": [
            ("Name", "Role", "Hourly rate", "Availability", "Screening status"),
            ("Amara Okafor", "Senior UX Designer", "$95", "From 2026-08-01", "Cleared"),
            ("Ben Tremblay", "Senior UI Developer", "$80", "Immediately", "Cleared"),
            ("Chloe Nguyen", "UX Researcher", "$90", "From 2026-07-15", "In progress"),
            ("Diego Ramirez", "Product Designer", "$70", "Immediately", "Cleared"),
            ("Elena Petrova", "Service Designer", "$105", "From 2026-09-01", "Cleared"),
        ],
    },
}

HOURS_CSV = {
    "project-hours-q1-2026.csv": [
        ("project", "week", "hours", "billable"),
        ("Aurora Discovery", "2026-W02", "112", "yes"),
        ("Aurora Discovery", "2026-W03", "118", "yes"),
        ("Aurora Discovery", "2026-W04", "121", "yes"),
        ("Aurora Discovery", "2026-W05", "96", "yes"),
        ("Borealis Refresh", "2026-W02", "64", "yes"),
        ("Borealis Refresh", "2026-W03", "71", "yes"),
        ("Borealis Refresh", "2026-W04", "58", "yes"),
        ("Internal Tooling", "2026-W02", "24", "no"),
        ("Internal Tooling", "2026-W03", "19", "no"),
        ("Internal Tooling", "2026-W04", "22", "no"),
    ],
}


def write_docx(path: Path, title: str, sections):
    import docx

    d = docx.Document()
    d.add_heading(title, level=0)
    for heading, body in sections:
        d.add_heading(heading, level=1)
        for para in body.split("\n\n"):
            d.add_paragraph(para)
    d.save(str(path))


def write_pdf(path: Path, text: str):
    import fitz

    doc = fitz.open()
    page = doc.new_page()  # A4 default
    rect = fitz.Rect(54, 54, page.rect.width - 54, page.rect.height - 54)
    leftover = page.insert_textbox(rect, text, fontsize=10, fontname="helv")
    if leftover < 0:
        raise RuntimeError(f"{path.name}: text overflows one page; shorten it")
    doc.save(str(path))
    doc.close()


def write_pptx(path: Path, slides):
    from pptx import Presentation

    prs = Presentation()
    layout = prs.slide_layouts[1]  # title + content
    for title, body in slides:
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    prs.save(str(path))


def write_xlsx(path: Path, sheet: str, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(list(row))
    wb.save(str(path))


def write_csv(path: Path, rows):
    import csv as _csv

    with path.open("w", newline="", encoding="utf-8") as fh:
        _csv.writer(fh).writerows(rows)


def main() -> None:
    CORPUS_DIR.mkdir(exist_ok=True)
    for name, spec in {**RESUMES, **PROPOSAL_DOCX, **POLICY_DOCX}.items():
        write_docx(CORPUS_DIR / name, spec["title"], spec["sections"])
    for name, text in RESUME_PDF.items():
        write_pdf(CORPUS_DIR / name, text)
    for name, text in {**RESUME_TXT, **CORRESPONDENCE_TXT, **FAQ_TXT}.items():
        (CORPUS_DIR / name).write_text(text, encoding="utf-8")
    for name, text in {**PROPOSAL_MD, **POLICY_MD}.items():
        (CORPUS_DIR / name).write_text(text, encoding="utf-8")
    for name, spec in CAPABILITIES_PPTX.items():
        write_pptx(CORPUS_DIR / name, spec)
    for name, spec in ROSTER_XLSX.items():
        write_xlsx(CORPUS_DIR / name, spec["sheet"], spec["rows"])
    for name, rows in HOURS_CSV.items():
        write_csv(CORPUS_DIR / name, rows)

    files = sorted(CORPUS_DIR.iterdir())
    print(f"Wrote {len(files)} files to {CORPUS_DIR}:")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size} B)")


if __name__ == "__main__":
    main()
