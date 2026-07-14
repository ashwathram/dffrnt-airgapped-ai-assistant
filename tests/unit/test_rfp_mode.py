from unittest.mock import patch

from dffrnt_assistant.config import Settings
from dffrnt_assistant.rag import pipeline as pipeline_module
from dffrnt_assistant.rag.pipeline import RagPipeline


class FakeRetriever:
    def __init__(self, hits):
        self._hits = hits

    def retrieve(self, question, tag_filter=None, mode="chat"):
        return list(self._hits)

    def sources(self, hits):
        return [{"filename": h["payload"]["filename"]} for h in hits]


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


def _hit(filename, text, *, document_type="", tags=None, summary_kind="chunk", score=1.0):
    return {
        "payload": {
            "filename": filename,
            "text": text,
            "document_type": document_type,
            "tags": tags or [],
            "summary_kind": summary_kind,
        },
        "score": score,
    }


def test_rfp_mode_answer_uses_compare_flow_and_required_sections():
    settings = Settings()
    llm = FakeLLM(
        [
            "Required roles:\n- UX Researcher [1]\nRequired skills and experience:\n- User interviews [1]\nRequired deliverables:\n- Research report [1]\nPreferred tools or domain preferences:\n- Figma [1]",
            (
                "Resume: Alex_Morgan_UX_Researcher_Fictional_Resume.docx\n"
                "- Supported roles/titles: UX Researcher [2]\n"
                "- Supported skills: User interviews [2]\n"
                "- Supported experience: 5+ years [2]\n"
                "- Supported deliverables or outputs: Research reports [2]\n"
                "- Preferred tools/domain evidence: Figma [2]\n"
                "Resume: Cella_Shang_UX_Researcher_Resume.docx\n"
                "- Supported roles/titles: UX Researcher [3]\n"
                "- Supported skills: Usability testing [3]\n"
                "- Supported experience: Product research [3]\n"
                "- Supported deliverables or outputs: Recommendations [3]\n"
                "- Preferred tools/domain evidence: FigJam [3]\n"
                "Resume: Jane_Doe_UX_Designer_Fictional_Resume.docx\n"
                "- Supported roles/titles: UX Designer [4]\n"
                "- Supported skills: Prototyping [4]\n"
                "- Supported experience: Enterprise product design [4]\n"
                "- Supported deliverables or outputs: Mockups [4]\n"
                "- Preferred tools/domain evidence: Figma [4]\n"
                "Resume: FIRST LAST-1-Software-Engineer.pdf\n"
                "- Supported roles/titles: Software Engineer [5]\n"
                "- Supported skills: Front-end development [5]\n"
                "- Supported experience: Web applications [5]\n"
                "- Supported deliverables or outputs: Production features [5]\n"
                "- Preferred tools/domain evidence: React [5]"
            ),
            (
                "Final conclusion:\n"
                "- Partially: the selected resumes cover UX research, design, and front-end support, but still miss some required roles. [1][2][3][4][5]\n"
                "RFP requirements:\n"
                "- Required roles include UX research, design, and project delivery support. [1]\n"
                "- Required qualifications include user research methods and delivery artifacts such as research reports. [1]\n"
                "Resume set coverage:\n"
                "- Alex_Morgan_UX_Researcher_Fictional_Resume.docx, Cella_Shang_UX_Researcher_Resume.docx, Jane_Doe_UX_Designer_Fictional_Resume.docx, and FIRST LAST-1-Software-Engineer.pdf together cover research, design, and front-end evidence, but not the full team shape. [1][2][3][4][5]"
            ),
        ]
    )
    hits = [
        _hit(
            "RFP_Enterprise_Customer_Portal_Redesign.docx",
            "Required team includes UX Researcher and deliverables include research report.",
            document_type="rfp",
            tags=["UX RFP"],
            summary_kind="document_summary",
        ),
        _hit(
            "Alex_Morgan_UX_Researcher_Fictional_Resume.docx",
            "UX Researcher with interviews and reports.",
            tags=["Alex", "Resume"],
            summary_kind="document_summary",
        ),
        _hit(
            "Cella_Shang_UX_Researcher_Resume.docx",
            "UX Researcher with usability testing and synthesis.",
            tags=["Cella", "Resume"],
            summary_kind="document_summary",
        ),
        _hit(
            "Jane_Doe_UX_Designer_Fictional_Resume.docx",
            "UX Designer with prototyping and enterprise design.",
            tags=["Jane", "Resume"],
            summary_kind="document_summary",
        ),
        _hit(
            "FIRST LAST-1-Software-Engineer.pdf",
            "Software Engineer with front-end delivery experience.",
            tags=["First_Last", "Resume"],
            summary_kind="document_summary",
        ),
    ]
    pipeline = RagPipeline(FakeRetriever(hits), llm, settings)

    result = pipeline.answer(
        "Check selected resumes against selected RFP",
        [],
        ["UX RFP", "Alex", "Cella", "Jane", "First_Last"],
        mode="rfp",
    )

    answer = result["answer"]
    assert "Final conclusion:" in answer
    assert "RFP requirements:" in answer
    assert "Resume set coverage:" in answer
    assert len(llm.prompts) == 3
    assert "Extracted RFP requirements:" in llm.prompts[2]
    assert "Extracted resume capabilities:" in llm.prompts[2]


def test_rfp_mode_routes_into_rfp_answer_and_captures_rfp_and_resume_contexts():
    settings = Settings()
    llm = FakeLLM(
        [
            "Required roles:\n- UX Researcher [1]",
            (
                "Resume: Alex_Morgan_UX_Researcher_Fictional_Resume.docx\n"
                "- Supported roles/titles: UX Researcher [2]\n"
                "Resume: Cella_Shang_UX_Researcher_Resume.docx\n"
                "- Supported roles/titles: UX Researcher [3]\n"
                "Resume: Jane_Doe_UX_Designer_Fictional_Resume.docx\n"
                "- Supported roles/titles: UX Designer [4]\n"
                "Resume: FIRST LAST-1-Software-Engineer.pdf\n"
                "- Supported roles/titles: Software Engineer [5]"
            ),
            (
                "Final conclusion:\n"
                "- Partially: some required roles are still missing. [1][2][3][4][5]\n"
                "RFP requirements:\n"
                "- UX research and design support are required. [1]\n"
                "Resume set coverage:\n"
                "- Alex_Morgan_UX_Researcher_Fictional_Resume.docx, Cella_Shang_UX_Researcher_Resume.docx, Jane_Doe_UX_Designer_Fictional_Resume.docx, and FIRST LAST-1-Software-Engineer.pdf are present. [1][2][3][4][5]"
            ),
        ]
    )
    hits = [
        _hit(
            "RFP_Enterprise_Customer_Portal_Redesign.docx",
            "Required Project Team includes UX Researcher and UI Designer.",
            document_type="rfp",
            tags=["UX RFP"],
            summary_kind="document_summary",
        ),
        _hit(
            "RFP_Enterprise_Customer_Portal_Redesign.docx",
            "Required Qualifications include user interviews and research reports.",
            document_type="rfp",
            tags=["UX RFP"],
        ),
        _hit(
            "Alex_Morgan_UX_Researcher_Fictional_Resume.docx",
            "Alex resume evidence.",
            tags=["Alex", "Resume"],
            summary_kind="document_summary",
        ),
        _hit(
            "Cella_Shang_UX_Researcher_Resume.docx",
            "Cella resume evidence.",
            tags=["Cella", "Resume"],
            summary_kind="document_summary",
        ),
        _hit(
            "Jane_Doe_UX_Designer_Fictional_Resume.docx",
            "Jane resume evidence.",
            tags=["Jane", "Resume"],
            summary_kind="document_summary",
        ),
        _hit(
            "FIRST LAST-1-Software-Engineer.pdf",
            "First Last resume evidence.",
            tags=["First_Last", "Resume"],
            summary_kind="document_summary",
        ),
    ]
    pipeline = RagPipeline(FakeRetriever(hits), llm, settings)
    captured = {}

    original_requirements = pipeline_module.build_rfp_requirements_prompt
    original_capabilities = pipeline_module.build_resume_capabilities_prompt
    original_compare = pipeline_module.build_rfp_compare_prompt

    def capture_requirements(context, question):
        captured["rfp_context"] = context
        return original_requirements(context, question)

    def capture_capabilities(context, question):
        captured["resume_context"] = context
        return original_capabilities(context, question)

    def capture_compare(requirements, capabilities, question):
        captured["requirements"] = requirements
        captured["capabilities"] = capabilities
        return original_compare(requirements, capabilities, question)

    with patch.object(pipeline, "_rfp_answer", wraps=pipeline._rfp_answer) as wrapped_answer:
        with patch.object(pipeline_module, "build_rfp_requirements_prompt", side_effect=capture_requirements):
            with patch.object(pipeline_module, "build_resume_capabilities_prompt", side_effect=capture_capabilities):
                with patch.object(pipeline_module, "build_rfp_compare_prompt", side_effect=capture_compare) as wrapped_compare:
                    result = pipeline.answer(
                        "Check selected resumes against selected RFP",
                        [],
                        ["UX RFP", "Alex", "Cella", "Jane", "First_Last"],
                        mode="rfp",
                    )

    assert wrapped_answer.called
    assert wrapped_compare.called
    assert '<<file name="RFP_Enterprise_Customer_Portal_Redesign.docx">>' in captured["rfp_context"]
    assert captured["rfp_context"].count('<<file name="RFP_Enterprise_Customer_Portal_Redesign.docx">>') == 1
    for filename in [
        "Alex_Morgan_UX_Researcher_Fictional_Resume.docx",
        "Cella_Shang_UX_Researcher_Resume.docx",
        "Jane_Doe_UX_Designer_Fictional_Resume.docx",
        "FIRST LAST-1-Software-Engineer.pdf",
    ]:
        assert f'<<file name="{filename}">>' in captured["resume_context"]
    assert captured["requirements"]
    assert captured["capabilities"]
    assert "Final conclusion:" in result["answer"]
    assert "RFP requirements:" in result["answer"]
    assert "Resume set coverage:" in result["answer"]


def test_rfp_mode_stream_routes_into_rfp_answer_stream():
    settings = Settings()
    llm = FakeLLM(
        [
            "Required roles:\n- UX Researcher [1]",
            "Resume: Alex_Morgan_UX_Researcher_Fictional_Resume.docx\n- Supported roles/titles: UX Researcher [2]",
            (
                "Final conclusion:\n"
                "- Partially: evidence is incomplete. [1][2]\n"
                "RFP requirements:\n"
                "- UX research support is required. [1]\n"
                "Resume set coverage:\n"
                "- Alex_Morgan_UX_Researcher_Fictional_Resume.docx is present but the full set is incomplete. [1][2]"
            ),
        ]
    )
    hits = [
        _hit(
            "RFP_Enterprise_Customer_Portal_Redesign.docx",
            "Required Project Team includes UX Researcher.",
            document_type="rfp",
            tags=["UX RFP"],
            summary_kind="document_summary",
        ),
        _hit(
            "Alex_Morgan_UX_Researcher_Fictional_Resume.docx",
            "Alex resume evidence.",
            tags=["Alex", "Resume"],
            summary_kind="document_summary",
        ),
    ]
    pipeline = RagPipeline(FakeRetriever(hits), llm, settings)

    with patch.object(pipeline, "_rfp_answer_stream", wraps=pipeline._rfp_answer_stream) as wrapped_stream:
        events = list(
            pipeline.answer_stream(
                "Check selected resumes against selected RFP",
                [],
                ["UX RFP", "Alex"],
                mode="rfp",
            )
        )

    assert wrapped_stream.called
    text = "".join(payload for kind, payload in events if kind == "token")
    assert "Final conclusion:" in text
    assert "RFP requirements:" in text
    assert "Resume set coverage:" in text
