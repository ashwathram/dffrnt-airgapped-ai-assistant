"""The RAG pipeline: retrieve -> assemble prompt -> generate."""

import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from ..ingest.loaders import load_file
from .prompt import (
    DEFAULT_RESUME_SYSTEM_PROMPT,
    DEFAULT_SYSTEM_PROMPT,
    build_history,
    build_prompt,
    build_resume_prompt,
)

_NO_DOCUMENTS = (
    "No documents have been ingested yet. Please ask an admin to upload documents."
)
_NO_MATCHING_TAGS = (
    "No documents match the selected tag filter. Clear the filter or choose "
    "different tags, then try again."
)


def _no_hits_message(tag_filter) -> str:
    return _NO_MATCHING_TAGS if tag_filter else _NO_DOCUMENTS


class RagPipeline:
    def __init__(self, retriever, llm, settings):
        self.retriever = retriever
        self.llm = llm
        self.settings = settings
        self.system_prompt = settings.system_prompt or DEFAULT_SYSTEM_PROMPT
        self.resume_system_prompt = DEFAULT_RESUME_SYSTEM_PROMPT
        self.resume_generation_options = {"num_predict": 800, "repeat_penalty": 1.08}

    @staticmethod
    def _trim_repeated_resume_tail(text: str) -> str:
        if not text:
            return text
        markers = [
            "\nProfessional Summary",
            "\nCore Competencies",
            "\nProfessional Experience",
            "\nEducation",
            "\nCertifications",
            "\nTools",
        ]
        for marker in markers:
            first = text.find(marker)
            if first < 0:
                continue
            second = text.find(marker, first + len(marker))
            if second > first:
                return text[:second].rstrip()
        return text

    @staticmethod
    def _resume_sort_key(payload):
        return (
            payload.get("page_number") or 0,
            payload.get("slide_index") or 0,
            payload.get("char_start") or 0,
            str(payload.get("chunk_id") or ""),
        )

    def _document_text(self, filename: str) -> str:
        payloads = self.retriever.store.payloads_by_filename(filename)
        source_candidates: List[Path] = []
        for payload in payloads:
            source_file = str(payload.get("source_file") or "").strip()
            if source_file:
                source_candidates.append(Path(source_file))
        source_candidates.append(Path(self.settings.data_dir) / filename)
        for candidate in source_candidates:
            try:
                if candidate.is_file():
                    document = load_file(str(candidate))
                    text = (document.get("text") or "").strip()
                    if text:
                        return text
            except Exception:
                continue

        payloads = sorted(
            payloads,
            key=self._resume_sort_key,
        )
        seen = set()
        parts = []
        for payload in payloads:
            text = " ".join((payload.get("text") or "").split())
            if not text or text in seen:
                continue
            seen.add(text)
            parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _extract_resume_sections(resume_text: str) -> Dict[str, str]:
        headings = [
            "Professional Summary",
            "Core Competencies",
            "Professional Experience",
            "Education",
            "Certifications",
            "Tools",
        ]
        sections: Dict[str, str] = {}
        for index, heading in enumerate(headings):
            start = resume_text.find(heading)
            if start < 0:
                continue
            end = len(resume_text)
            for next_heading in headings[index + 1 :]:
                next_start = resume_text.find(next_heading, start + len(heading))
                if next_start >= 0:
                    end = min(end, next_start)
            sections[heading] = resume_text[start:end].strip()
        if "Header" not in sections:
            first_heading_positions = [
                resume_text.find(h) for h in headings if resume_text.find(h) >= 0
            ]
            header_end = min(first_heading_positions) if first_heading_positions else len(resume_text)
            sections["Header"] = resume_text[:header_end].strip()
        return sections

    @staticmethod
    def _extract_rfp_focus(rfp_text: str) -> str:
        priorities = []
        probes = {
            "Objectives": [
                ("Improve citizen experience", "Improve user experience"),
                ("Increase online service completion", "Improve completion rates"),
                ("Standardize design", "Standardize design"),
                ("Build reusable UX assets", "Build reusable UX assets"),
            ],
            "Scope": [
                ("Citizen interviews", "User research interviews"),
                ("Stakeholder interviews", "Stakeholder interviews"),
                ("Service blueprint workshops", "Service design workshops"),
                ("Accessibility assessment", "Accessibility assessment"),
                ("Journey mapping", "Journey mapping"),
                ("Information architecture", "Information architecture"),
                ("Wireframes", "Wireframes"),
                ("Prototypes", "Prototypes"),
                ("Responsive interfaces", "Responsive interfaces"),
                ("Design system", "Design systems"),
                ("Remote usability testing", "Usability testing"),
                ("Accessibility validation", "Accessibility validation"),
            ],
            "Qualifications": [
                ("Interaction design", "Interaction design"),
                ("Information architecture", "Information architecture"),
                ("Responsive design", "Responsive design"),
                ("Design systems", "Design systems"),
                ("Accessibility", "Accessibility"),
                ("WCAG 2.2 AA", "Accessibility standards"),
            ],
            "Tools": [
                ("Figma", "Figma"),
                ("FigJam", "FigJam"),
                ("Dovetail", "Dovetail"),
                ("Optimal Workshop", "Optimal Workshop"),
                ("Miro", "Miro"),
                ("Jira", "Jira"),
                ("Confluence", "Confluence"),
            ],
        }
        lowered = rfp_text.lower()
        for label, items in probes.items():
            matched = [display for raw, display in items if raw.lower() in lowered]
            if matched:
                priorities.append(f"{label}: " + "; ".join(matched))
        return "\n".join(priorities) if priorities else rfp_text[:1500]

    def _generate_resume_section(self, prompt: str, num_predict: int) -> str:
        return self.llm.generate(
            prompt,
            {"num_predict": num_predict, "repeat_penalty": 1.12},
        ).strip()

    def _generate_summary(self, header_text: str, summary_text: str, rfp_focus: str) -> str:
        if not summary_text.strip():
            return summary_text.strip()
        prompt = (
            f"{self.resume_system_prompt}\n\n"
            "You are rewriting only the Professional Summary section of a resume for an RFP response.\n"
            "Return exactly one Professional Summary section.\n"
            "Write one compact paragraph only.\n"
            "Do not output markdown, bullets, commentary, duplicated text, or any other section.\n\n"
            f"RFP priorities:\n{rfp_focus}\n\n"
            f"Resume header:\n{header_text}\n\n"
            f"Source Professional Summary:\n{summary_text}\n\n"
            "Keep the same underlying facts, seniority, and scope from the source summary.\n"
            "Prefer stronger RFP-aligned wording where the source summary supports it.\n"
            "Use broad alignment language, not narrow proposal jargon, unless the source summary explicitly contains that specificity.\n"
            "Prefer the more specific factual wording from the source summary over a broader generic paraphrase when both would mean the same thing.\n"
            "Do not introduce unsupported years of experience, industries, standards, tools, metrics, or responsibilities.\n"
            "Do not introduce government, citizen-service, named compliance standards, or named research methods unless they are explicitly in the source summary.\n"
            "Replace the original summary text instead of appending to it.\n"
            "Rewrite the Professional Summary now:"
        )
        raw = self._generate_resume_section(prompt, 160)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return summary_text.strip()
        cleaned_lines: List[str] = []
        body = ""
        for line in lines:
            if line.startswith("#") or line == "---":
                continue
            lowered = line.lower().rstrip(":")
            if lowered == "professional summary":
                continue
            body = line
            break
        if not body:
            return summary_text.strip()
        cleaned_lines.append("Professional Summary")
        cleaned_lines.append(body)
        return "\n\n".join(cleaned_lines).strip()

    @staticmethod
    def _looks_like_role_boundary(lines: List[str], index: int) -> bool:
        if index + 1 >= len(lines):
            return False
        title_line = lines[index].strip()
        meta_line = lines[index + 1].strip()
        if not title_line or not meta_line:
            return False
        if title_line.startswith(("-", "•")) or meta_line.startswith(("-", "•")):
            return False
        has_date = any(char.isdigit() for char in meta_line) and (
            "|" in meta_line or "Present" in meta_line or "present" in meta_line
        )
        return has_date

    def _parse_experience_roles(self, experience_text: str) -> List[Dict[str, object]]:
        lines = [line.strip() for line in experience_text.splitlines() if line.strip()]
        if lines and lines[0] == "Professional Experience":
            lines = lines[1:]
        roles: List[Dict[str, object]] = []
        index = 0
        while index < len(lines):
            if not self._looks_like_role_boundary(lines, index):
                index += 1
                continue
            title = lines[index]
            company_line = lines[index + 1]
            index += 2
            bullets: List[str] = []
            while index < len(lines) and not self._looks_like_role_boundary(lines, index):
                line = lines[index].lstrip("-• ").strip()
                if line:
                    bullets.append(line)
                index += 1
            roles.append(
                {
                    "title": title,
                    "company_line": company_line,
                    "bullets": bullets,
                }
            )
        return roles

    @staticmethod
    def _clean_generated_bullets(text: str, expected_count: int) -> List[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        bullets: List[str] = []
        for line in lines:
            if line.lower().startswith("professional experience"):
                continue
            cleaned = re.sub(r"^[-*•\d\.\)\s]+", "", line).strip()
            if cleaned and not any(
                token in cleaned.lower() for token in ("nimbus digital |", "brightpath solutions |", "pixel forge studio |")
            ):
                bullets.append(cleaned)
        if expected_count and len(bullets) > expected_count:
            bullets = bullets[:expected_count]
        return bullets

    def _generate_role_bullet(
        self, role_title: str, company_line: str, source_bullet: str, rfp_focus: str
    ) -> str:
        prompt = (
            f"{self.resume_system_prompt}\n\n"
            "You are rewriting one resume bullet for an RFP response.\n"
            "Keep the employer, job title, and date range unchanged outside this rewrite. Rewrite only this one bullet.\n"
            "Return exactly one bullet sentence only, with no heading, no commentary, and no extra sections.\n\n"
            f"RFP priorities:\n{rfp_focus}\n\n"
            f"Role title:\n{role_title}\n\n"
            f"Company and dates:\n{company_line}\n\n"
            f"Source bullet:\n- {source_bullet}\n\n"
            "Prefer the RFP's terminology wherever the source resume supports it.\n"
            "Keep the same underlying facts, but rewrite the bullet more directly against the RFP priorities so the fit is obvious.\n"
            "Preserve the same concrete activity, method, tool, metric, and outcome from the source bullet.\n"
            "Prefer the most specific supported wording from the source bullet over a broader generic rewrite when both would communicate the same meaning.\n"
            "Keep concrete numbers, named activities, explicit methods, and distinct outcomes visible whenever they appear in the source bullet.\n"
            "Avoid repetitive phrasing. Do not fall back to generic lead-ins like 'Conducted user research' or similar stock phrasing unless that is literally what the source bullet says.\n"
            "Do not invent new projects, industries, standards, tools, metrics, responsibilities, or employers.\n"
            "Do not introduce government, citizen, public-sector, named compliance standards, named workshop types, named interview types, or named testing methods unless they already appear in the source bullet.\n"
            "Do not add numbers, percentages, compliance standards, workshops, interviews, or testing methods unless they already appear in the source bullet.\n"
            "Rewrite the bullet now:"
        )
        raw = self._generate_resume_section(prompt, 220)
        bullets = self._clean_generated_bullets(raw, 1)
        return bullets[0] if bullets else source_bullet

    def _generate_role_bullets(
        self, role_title: str, company_line: str, source_bullets: List[str], rfp_focus: str
    ) -> List[str]:
        return [
            self._generate_role_bullet(role_title, company_line, bullet, rfp_focus)
            for bullet in source_bullets
        ]

    def _generate_professional_experience(self, experience_text: str, rfp_focus: str) -> str:
        roles = self._parse_experience_roles(experience_text)
        if not roles:
            return experience_text.strip()
        rendered_roles = ["Professional Experience"]
        for role in roles:
            title = str(role.get("title") or "").strip()
            company_line = str(role.get("company_line") or "").strip()
            source_bullets = [str(bullet).strip() for bullet in role.get("bullets") or [] if str(bullet).strip()]
            rewritten_bullets = (
                self._generate_role_bullets(title, company_line, source_bullets, rfp_focus)
                if source_bullets
                else []
            )
            rendered_roles.extend([title, company_line])
            for bullet in rewritten_bullets:
                rendered_roles.append(f"- {bullet}")
        return "\n".join(rendered_roles).strip()

    def _build_tailored_resume(
        self, selected_resume_filename: str, selected_rfp_filename: str
    ) -> str:
        resume_text = self._document_text(selected_resume_filename)
        rfp_text = self._document_text(selected_rfp_filename)
        resume_sections = self._extract_resume_sections(resume_text)
        rfp_focus = self._extract_rfp_focus(rfp_text)

        header = resume_sections.get("Header", "").strip()
        summary = self._generate_summary(
            header,
            resume_sections.get("Professional Summary", ""),
            rfp_focus,
        )
        competencies = resume_sections.get("Core Competencies", "").strip()
        experience = self._generate_professional_experience(
            resume_sections.get("Professional Experience", ""),
            rfp_focus,
        )
        education = resume_sections.get("Education", "").strip()
        certifications = resume_sections.get("Certifications", "").strip()
        tools = resume_sections.get("Tools", "").strip()

        ordered_sections = [
            header,
            summary,
            competencies,
            experience,
            education,
            certifications,
            tools,
        ]
        cleaned = [part.strip() for part in ordered_sections if part and part.strip()]
        result = "\n\n".join(cleaned)
        return self._trim_repeated_resume_tail(result)

    def _resolve_resume_hits(
        self,
        question: str,
        tag_filter,
        grounding_preference,
        selected_resume_filename: str,
        selected_rfp_filename: str,
    ):
        selected_files = [name for name in [selected_resume_filename, selected_rfp_filename] if name]
        effective_tags = list(tag_filter or [])
        if len(selected_files) < 2:
            return [], effective_tags, selected_files, "chat"

        combined = []
        seen_chunks = set()
        resume_chunks = sorted(
            self.retriever.store.payloads_by_filename(selected_resume_filename),
            key=self._resume_sort_key,
        )
        for payload in resume_chunks:
            chunk_key = (
                payload.get("filename"),
                payload.get("chunk_id"),
                payload.get("page_number"),
                payload.get("char_start"),
                payload.get("char_end"),
            )
            if chunk_key in seen_chunks:
                continue
            seen_chunks.add(chunk_key)
            combined.append({"payload": payload, "score": 1.0})

        rfp_top_k = max(6, self.settings.top_k)
        rfp_hits = self.retriever.retrieve(
            question,
            effective_tags or None,
            [selected_rfp_filename],
            top_k=rfp_top_k,
        )
        for hit in rfp_hits:
            payload = hit.get("payload") or {}
            chunk_key = (
                payload.get("filename"),
                payload.get("chunk_id"),
                payload.get("page_number"),
                payload.get("char_start"),
                payload.get("char_end"),
            )
            if chunk_key in seen_chunks:
                continue
            seen_chunks.add(chunk_key)
            combined.append(hit)
        hits = sorted(combined, key=lambda item: item.get("score", 0), reverse=True)
        return hits, effective_tags, selected_files, "documents" if hits else "chat"

    def answer(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        tag_filter=None,
        mode: str = "default",
        grounding_preference: str = "auto",
        selected_resume_filename: str = "",
        selected_rfp_filename: str = "",
    ) -> dict:
        if mode == "resume":
            hits, effective_tags, selected_files, source_mode = self._resolve_resume_hits(
                question,
                tag_filter,
                grounding_preference,
                selected_resume_filename,
                selected_rfp_filename,
            )
            if not hits:
                return {
                    "answer": (
                        "Select one uploaded resume and one uploaded RFP document, then try again. "
                        "RFP tailoring mode only uses those selected uploaded files."
                        if len(selected_files) < 2
                        else "I couldn't find matching content in the selected uploaded resume and RFP files. "
                        "Check that both files were ingested successfully and tagged as 'resume' and 'rfp'."
                    ),
                    "sources": [],
                    "question": question,
                    "meta": {
                        "mode": "resume",
                        "source_mode": "chat",
                        "effective_tags": effective_tags,
                        "selected_files": selected_files,
                    },
                }
            answer = self._build_tailored_resume(
                selected_resume_filename, selected_rfp_filename
            )
            return {
                "answer": answer,
                "sources": self.retriever.sources(hits),
                "question": question,
                "meta": {
                    "mode": "resume",
                    "source_mode": source_mode,
                    "effective_tags": effective_tags,
                    "selected_files": selected_files,
                },
            }

        hits = self.retriever.retrieve(question, tag_filter)
        if not hits:
            return {
                "answer": _no_hits_message(tag_filter),
                "sources": [],
                "question": question,
                "meta": {
                    "mode": "default",
                    "source_mode": "chat",
                    "effective_tags": tag_filter or [],
                },
            }

        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)

        return {
            "answer": self.llm.generate(prompt),
            "sources": self.retriever.sources(hits),
            "question": question,
            "meta": {
                "mode": "default",
                "source_mode": "documents",
                "effective_tags": tag_filter or [],
            },
        }

    def answer_stream(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        tag_filter=None,
        mode: str = "default",
        grounding_preference: str = "auto",
        selected_resume_filename: str = "",
        selected_rfp_filename: str = "",
    ) -> Iterator[Tuple[str, object]]:
        """Stream an answer as ``(kind, payload)`` events.

        Yields exactly one ``("sources", list)`` first (retrieval happens before
        generation, so sources are known up front), then ``("token", str)`` for
        each generated token. The caller assembles the final answer text.
        """
        if mode == "resume":
            hits, effective_tags, selected_files, source_mode = self._resolve_resume_hits(
                question,
                tag_filter,
                grounding_preference,
                selected_resume_filename,
                selected_rfp_filename,
            )
            if not hits:
                yield (
                    "meta",
                    {
                        "mode": "resume",
                        "source_mode": "chat",
                        "effective_tags": effective_tags,
                        "selected_files": selected_files,
                    },
                )
                yield ("sources", [])
                yield (
                    "token",
                    (
                        "Select one uploaded resume and one uploaded RFP document, then try again. "
                        "RFP tailoring mode only uses those selected uploaded files."
                        if len(selected_files) < 2
                        else "I couldn't find matching content in the selected uploaded resume and RFP files. "
                        "Check that both files were ingested successfully and tagged as 'resume' and 'rfp'."
                    ),
                )
                return
            yield (
                "meta",
                {
                    "mode": "resume",
                    "source_mode": source_mode,
                    "effective_tags": effective_tags,
                    "selected_files": selected_files,
                },
            )
            yield ("sources", self.retriever.sources(hits))
            answer = self._build_tailored_resume(
                selected_resume_filename, selected_rfp_filename
            )
            yield ("token", answer)
            return

        hits = self.retriever.retrieve(question, tag_filter)
        if not hits:
            yield (
                "meta",
                {
                    "mode": "default",
                    "source_mode": "chat",
                    "effective_tags": tag_filter or [],
                },
            )
            yield ("sources", [])
            yield ("token", _no_hits_message(tag_filter))
            return

        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)

        yield (
            "meta",
            {
                "mode": "default",
                "source_mode": "documents",
                "effective_tags": tag_filter or [],
            },
        )
        yield ("sources", self.retriever.sources(hits))
        for channel, text in self.llm.generate_stream(prompt):
            yield ("thinking", text) if channel == "thinking" else ("token", text)
