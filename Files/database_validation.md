# Database Validation Report

Generated: 2026-05-27T09:48:56
Corpus root: `C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related`
Collection: `db_validation_20260527_094525`
Weak evidence threshold: `0.45`
Documents ingested: 10
Chunks ingested: 5761

## A. Database Infrastructure Scorecard

**Result:** PASS

### 1. File ingestion
- files_discovered: 10
- files_loaded: 10
- ingestion_completeness: 1.0
- failed_files: 0 failed (see sample below)
- file_type_breakdown: {'PDF': 3460, 'DOCX': 4, 'PPTX': 63, 'CSV': 2234}

### 2. Chunk quality
- total_chunks: 5761
- avg_chunks_per_file: 576.1
- min_chunk_length: 1
- max_chunk_length: 1200
- avg_chunk_length: 746.37
- median_chunk_length: 1032
- empty_chunk_count: 0
- short_chunk_count: 896
- duplicate_chunk_count: 0
- cross_file_contamination_count: 0

#### Sample chunks:
- source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section1
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section1::chunk_1
  - char_start: 0 char_end: 116
  - preview: 1 IBM Institute for Business ValueRewiring the C-suite The fast track to 2030 Global C-suite Series 2026 CEO Study
- source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section2
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section2::chunk_1
  - char_start: 118 char_end: 119
  - preview: 2
- source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section3
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section3::chunk_1
  - char_start: 121 char_end: 874
  - preview: 1 1This study is the 15th IBM Institute for Business Value (IBM IBV) CEO Study. For the 2026 CEO Study, the IBM IBV, in cooperation with Oxford Economics, surveyed 2,000 CEOs from 33 geog...
- source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section4
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section4::chunk_1
  - char_start: 876 char_end: 1174
  - preview: Foreword 3 Introduction 4 Play #1 Rethink the C-suite for speed and clarity 14 Play #2 Create an AI-agent flywheel 20 Play #3 Customize your AI mix, not just your AI models 26 Play #4 Orc...
- source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section5
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section5::chunk_1
  - char_start: 1176 char_end: 2259
  - preview: 3Foreword Leading at the speed of AI Artificial intelligence is not another cycle of change. It is a structural shift in how organizations think, decide, and compete. Every era has undere...

### 3. Metadata quality
- source_file: 100.0%
- filename: 100.0%
- file_type: 100.0%
- chunk_id: 100.0%
- section_heading: 100.0%
- char_start: 100.0%
- char_end: 100.0%

#### Sample payloads:
- {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'filename': '2026-ceo-study-rewiring-the-c-suite-report.pdf', 'file_type': 'pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section1::chunk_1', 'page_number': 1, 'slide_index': None, 'section_heading': 'section1', 'char_start': 0, 'char_end': 116}
- {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'filename': '2026-ceo-study-rewiring-the-c-suite-report.pdf', 'file_type': 'pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section2::chunk_1', 'page_number': 2, 'slide_index': None, 'section_heading': 'section2', 'char_start': 118, 'char_end': 119}
- {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'filename': '2026-ceo-study-rewiring-the-c-suite-report.pdf', 'file_type': 'pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section3::chunk_1', 'page_number': 3, 'slide_index': None, 'section_heading': 'section3', 'char_start': 121, 'char_end': 874}
- {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'filename': '2026-ceo-study-rewiring-the-c-suite-report.pdf', 'file_type': 'pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section4::chunk_1', 'page_number': 4, 'slide_index': None, 'section_heading': 'section4', 'char_start': 876, 'char_end': 1174}
- {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'filename': '2026-ceo-study-rewiring-the-c-suite-report.pdf', 'file_type': 'pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section5::chunk_1', 'page_number': 5, 'slide_index': None, 'section_heading': 'section5', 'char_start': 1176, 'char_end': 2259}

### 4. Embedding quality
- chunks_created: 5761
- embeddings_created: 5761
- embedding_completion_rate: 1.0
- embedding_dimension: 384
- dimension_consistency: True

### 5. Qdrant storage quality
- expected_vector_count: 5761
- qdrant_collection_count: 5761
- storage_completion_rate: 1.0

#### Sample stored records:
- id: a1be620f-1cc4-5683-bfe6-65f49df49e5e
  - payload_preview: {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section1::chunk_1', 'preview': '1 IBM Institute for Business ValueRewiring the C-suite The fast track to 2030 Global C-suite Series 2026 CEO Study'}
- id: 87a9c955-320a-54ab-8b7b-e9477915791b
  - payload_preview: {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section2::chunk_1', 'preview': '2'}
- id: 4fb9fc01-36d9-5f29-b6d5-041684fa198b
  - payload_preview: {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section3::chunk_1', 'preview': '1 1This study is the 15th IBM Institute for Business Value (IBM IBV) CEO Study. For the 2026 CEO Study, the IBM IBV, in cooperation with Oxford Economics, surveyed 2,000 CEOs from 33 geog...'}
- id: 2ec234a7-4a62-53ea-88e9-cc0c595ff629
  - payload_preview: {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section4::chunk_1', 'preview': 'Foreword 3 Introduction 4 Play #1 Rethink the C-suite for speed and clarity 14 Play #2 Create an AI-agent flywheel 20 Play #3 Customize your AI mix, not just your AI models 26 Play #4 Orc...'}
- id: d829f3b2-fe89-5d53-a957-38a6d16b6579
  - payload_preview: {'source_file': 'C:\\DTI 5902\\dffrnt-airgapped-ai-assistant\\database\\raw\\Client_Related\\2026-ceo-study-rewiring-the-c-suite-report.pdf', 'chunk_id': '2026-ceo-study-rewiring-the-c-suite-report.pdf::section5::chunk_1', 'preview': '3Foreword Leading at the speed of AI Artificial intelligence is not another cycle of change. It is a structural shift in how organizations think, decide, and compete. Every era has undere...'}

## B. Baseline Retrieval / Searchability Scorecard

**Result:** REVIEW

### Metrics
- queries_with_sensible_results: 17/24
- source_coverage_rate: 9/10
- broad_queries_returning_multiple_files: 5/5
- retrieval_diversity_avg: 2.3333333333333335
- negative_suppression_rate: 1/3
- weak_evidence_leakage: 24/120
- metadata_retrieval_completeness: 120/480
- paraphrase_stability: [{'pair': ('What projects did this person work on?', 'Find prior project experience'), 'overlap': 0.0}, {'pair': ('What technical skills are listed?', 'What technical skills are listed?'), 'overlap': 1.0}]

### Per-query results (top 5)

### Query: What technologies were used in PicoShell?

- score: 0.3792
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section95
  - chunk_id: dmava_mckinseyco.pdf::section95::chunk_14
  - preview: Section B. Inventions Developed under the Award .
- score: 0.3249
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section8
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section8::chunk_19
  - preview: Description of Project:
- score: 0.3249
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section16
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section16::chunk_3
  - preview: Description of Project:
- score: 0.3249
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_12
  - preview: Description of Project:
- score: 0.3192
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section16
  - chunk_id: dmava_mckinseyco.pdf::section16::chunk_3
  - preview: and datasets, including OrgLab,

### Query: What projects did this person work on?

- score: 0.5648
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_12
  - preview: Description of Project:
- score: 0.5648
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section8
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section8::chunk_19
  - preview: Description of Project:
- score: 0.5648
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section16
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section16::chunk_3
  - preview: Description of Project:
- score: 0.5106
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_10
  - preview: Tim Sutton: Project co -lead, architect, developer
- score: 0.4981
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_11
  - preview: Gavin Fleming: Project co -lead, GISc Practitioner

### Query: What technical skills are listed?

- score: 0.4821
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section46
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section46::chunk_4
  - preview: • Akkodis: The Akkodis Academy focuses on advanced digital, engineering and technology skills, supporting both early-career talent and experienced professionals in acquiring in-demand cap...
- score: 0.4736
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section46
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section46::chunk_1
  - preview: 3. Training and skilling The rapid acceleration of AI, automation, digitalization and the green transition is fundamentally reshaping how work is performed and which skills are required....
- score: 0.4619
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section50
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section50::chunk_10
  - preview: 7. Other Training : Microsoft Windows, Microsoft C#, Microsoft C++, Microsoft Visual Basic, MacOS, iOS, NVIDIA CUDA. Extensive experience with Open Sources technologies and development en...
- score: 0.4592
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section50
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section50::chunk_4
  - preview: 2. Proposed Position : Software Engineer
- score: 0.4582
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\Resume-Sample-1-Software-Engineer.pdf
  - section_heading: section1
  - chunk_id: Resume-Sample-1-Software-Engineer.pdf::section1::chunk_5
  - preview: UNIVERSITY OF ARIZONA, Tucson, Arizona M.S., Computer Science, 2012 B.S.B.A., Management Information Systems, 2011 TECHNICAL SKILLS

### Query: Where did this person study?

- score: 0.4703
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section33
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section33::chunk_1
  - preview: 31Case study
- score: 0.4294
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section27
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section27::chunk_1
  - preview: 25 25Case study
- score: 0.3924
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section69
  - chunk_id: dmava_mckinseyco.pdf::section69::chunk_17
  - preview: 43. Institution Of Higher Education. See 2 CFR 1108.235.
- score: 0.3651
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\Resume-Sample-1-Software-Engineer.pdf
  - section_heading: section1
  - chunk_id: Resume-Sample-1-Software-Engineer.pdf::section1::chunk_4
  - preview: EDUCATION
- score: 0.3580
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section14
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section14::chunk_1
  - preview: Healthcare Payer, provider, and life sciences

### Query: What sections should a case study include?

- score: 0.6993
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section2
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section2::chunk_11
  - preview: A well written case study will be informative, maintain interest and prompt action or further inquiry so remember the 4 core principles.
- score: 0.6725
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section2
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section2::chunk_1
  - preview: Case studies – a short guide to writing case studies
- score: 0.6549
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section2
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section2::chunk_9
  - preview: Case studies provide an opportunity to show case good or promising practice. They are frequently used to describe a problem or issue, which logically and step by step has been addressed t...
- score: 0.6439
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section3
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section3::chunk_1
  - preview: Case study template
- score: 0.6427
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section6
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section6::chunk_6
  - preview: Remember case studies & practice examples can:

### Query: How should project outcomes be presented?

- score: 0.5817
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section10
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section10::chunk_6
  - preview: The main goals of the project as outlined in the contract were:
- score: 0.5771
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section8
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section8::chunk_19
  - preview: Description of Project:
- score: 0.5771
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section16
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section16::chunk_3
  - preview: Description of Project:
- score: 0.5771
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_12
  - preview: Description of Project:
- score: 0.5482
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section104
  - chunk_id: dmava_mckinseyco.pdf::section104::chunk_9
  - preview: b. Favorable developments which will enable you to meet schedules and objectives sooner or at less cost than anticipated or produce more or different beneficial results than originally pl...

### Query: What belongs in an implementation plan?

- score: 0.5822
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section20
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section20::chunk_2
  - preview: 20 4 Description of Approach, Methodology and Work Plan
- score: 0.5494
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section11
  - chunk_id: dmava_mckinseyco.pdf::section11::chunk_6
  - preview: Key activities 1. Build transition plan from the current operating structure to the operating structures of the new agencies. The goal of the transition plan is to support operational con...
- score: 0.5376
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section46
  - chunk_id: dmava_mckinseyco.pdf::section46::chunk_5
  - preview: f. A comprehensive transition plan. g. A timeline for the transition plan.
- score: 0.5332
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section10
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section10::chunk_6
  - preview: The main goals of the project as outlined in the contract were:
- score: 0.5306
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section157
  - chunk_id: dmava_mckinseyco.pdf::section157::chunk_8
  - preview: Section F. Centralized Personnel Plan .

### Query: What is the structure of a one-page case study?

- score: 0.7657
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\IC-One-Page-Case-Study-Template-for-Microsoft-Word-Example_WORD.docx
  - section_heading: section1
  - chunk_id: IC-One-Page-Case-Study-Template-for-Microsoft-Word-Example_WORD.docx::section1::chunk_1
  - preview: ONE-PAGE CASE STUDY TEMPLATE for Microsoft Word EXAMPLE
- score: 0.6821
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section3
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section3::chunk_1
  - preview: Case study template
- score: 0.6410
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section2
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section2::chunk_1
  - preview: Case studies – a short guide to writing case studies
- score: 0.6029
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\IC-Data-Driven-Case-Study-Template-Example_WORD.docx
  - section_heading: section1
  - chunk_id: IC-Data-Driven-Case-Study-Template-Example_WORD.docx::section1::chunk_1
  - preview: DATA-DRIVEN CASE STUDY TEMPLATE EXAMPLE
- score: 0.5996
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section2
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section2::chunk_11
  - preview: A well written case study will be informative, maintain interest and prompt action or further inquiry so remember the 4 core principles.

### Query: How is AI being used by the company?

- score: 0.6487
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section35
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section35::chunk_3
  - preview: “It’s not laying AI on top of your existing tools and services. It’s reimagining the entire process.” Pablo T. Rivero CEO, Resy; SVP, Global Dining, American Express, USForeword Introduct...
- score: 0.6286
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section19
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section19::chunk_1
  - preview: “AI needs to be embedded into how we operate. That means integrating it into workflows across design, merchandising, marketing, stores, and operations—not as a separate initiative, but as...
- score: 0.6118
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section32
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section32::chunk_1
  - preview: Key business risks Description Mitigation Artificial intelligence (AI) The rapid pace of generative AI deployment brings with it the threat that advanced AI could eventually change the ex...
- score: 0.6087
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section38
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section38::chunk_2
  - preview: 12 Still, CEOs say only 25% of the workforce is using AI regularly as part of their job—despite the fact that 86% of CEOs say employees have the skills to collaborate with AI. The gap bet...
- score: 0.5934
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section25
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section25::chunk_2
  - preview: Before the next budget cycle closes, agree on a fixed reinvestment rate for AI-driven productivity gains (typically 60% to 80%) and commit to funding faster cycles of experimentation and...

### Query: What are the RUN and CHANGE pillars?

- score: 0.4136
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section11
  - chunk_id: dmava_mckinseyco.pdf::section11::chunk_6
  - preview: Key activities 1. Build transition plan from the current operating structure to the operating structures of the new agencies. The goal of the transition plan is to support operational con...
- score: 0.3767
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section10
  - chunk_id: dmava_mckinseyco.pdf::section10::chunk_4
  - preview: Phase 2: Design future state operating structures for the new agencies (i.e., structure, functions, and roles) This phase of work focuses on providing options for the future state operati...
- score: 0.3612
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section12
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section12::chunk_2
  - preview: • Market turnarounds: A critical component of RUN is the successful turnaround of key markets, specifically Adecco US and Akkodis Germany. • Productivity: By standardizing and automating...
- score: 0.3562
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section11
  - chunk_id: dmava_mckinseyco.pdf::section11::chunk_3
  - preview: 2. Conduct “design sessions” and/or discussions to identify and create the new operating structures for the new agencies in a way that aligns with the organizational design principles. Th...
- score: 0.3403
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section46
  - chunk_id: dmava_mckinseyco.pdf::section46::chunk_5
  - preview: f. A comprehensive transition plan. g. A timeline for the transition plan.

### Query: What business strategy is discussed?

- score: 0.5753
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section36
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section36::chunk_1
  - preview: 34Our analysis shows that leaders who have made the most progress breaking down functional boundaries are executing on strategy faster than the competition. Organizations that have redesi...
- score: 0.5440
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section20
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section20::chunk_2
  - preview: 20 4 Description of Approach, Methodology and Work Plan
- score: 0.5033
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section18
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section18::chunk_1
  - preview: 16“Dynamic strategy planning, continual communication, and being honest about why this is happening are extremely important.” Carsten Egeriis CEO, Danske Bank, DenmarkThis challenge is mo...
- score: 0.4971
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section103
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section103::chunk_1
  - preview: Illustration 3: Design of the 2025 STIP Role CEO Other EC members Target opportunity: Amount paid if performance targets are met for all metrics• 110% of annual base salary • 85%-100% of...
- score: 0.4746
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section48
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section48::chunk_1
  - preview: 46Comprehensive functional redesign and business-case realization (see play #4) To assess how organizational redesign translates into business value, the relationship between the breadth...

### Query: What leadership themes are mentioned?

- score: 0.4712
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section20
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section20::chunk_3
  - preview: Every leader completed a self-assessment and sought feedback from managers, peers, and direct reports. Leaders received an individual report to inform one or two focused development actio...
- score: 0.4668
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section42
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section42::chunk_3
  - preview: Key strengths included appreciation for senior leadership’s openness to diverse perspectives, clarity on role expectations and a strong sense of empowerment to make decisions in the best...
- score: 0.4269
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section29
  - chunk_id: dmava_mckinseyco.pdf::section29::chunk_4
  - preview:  NASA – ARMD Sustainable Leadership Effort. Led year-long workshop- based efforts for the ARMD senior leadership team focused on aligning on a common vision, building trust, making decis...
- score: 0.4209
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_15
  - preview: Project management, technical leadership, system architecture. Overseeing technical aspects of the various
- score: 0.4207
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section47
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section47::chunk_2
  - preview: The top quartile, referred to as AI-first organizations, is associated with stronger reported historical performance, including a 17% revenue growth premium over the past three years rela...

### Query: Find documents discussing AI

- score: 0.5035
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section37
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section37::chunk_1
  - preview: 35“The introduction of AI is more transformative than the introduction of the internet was at the time—not because of the technology itself, but because of its impact on how people work,...
- score: 0.4799
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section9
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section9::chunk_2
  - preview: 7 A playbook for AI-first success
- score: 0.4706
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section39
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section39::chunk_2
  - preview: Prioritize skills such as systems thinking, interpreting AI outputs, challenging recommendations, and managing exceptions. Redefine performance evaluations and manager training to reward...
- score: 0.4704
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section35
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section35::chunk_3
  - preview: “It’s not laying AI on top of your existing tools and services. It’s reimagining the entire process.” Pablo T. Rivero CEO, Resy; SVP, Global Dining, American Express, USForeword Introduct...
- score: 0.4622
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section58
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section58::chunk_6
  - preview: • Shaping responsible AI policy for the world of work We continued our engagement on the responsible use of artificial intelligence in the workplace, advocating for regulatory frameworks...

### Query: Find implementation examples

- score: 0.5254
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section6
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section6::chunk_9
  - preview: SHARING EXAMPLES
- score: 0.4720
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section4
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section4::chunk_1
  - preview: Local practice examples
- score: 0.4591
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section5
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section5::chunk_1
  - preview: Local practice example template
- score: 0.3888
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section20
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section20::chunk_3
  - preview: 4.1 Technical Approach and Methodology
- score: 0.3827
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section16
  - chunk_id: dmava_mckinseyco.pdf::section16::chunk_3
  - preview: and datasets, including OrgLab,

### Query: Find documents discussing performance metrics

- score: 0.5119
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section163
  - chunk_id: dmava_mckinseyco.pdf::section163::chunk_2
  - preview: POP Article I. Period of Performance
- score: 0.4672
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section103
  - chunk_id: dmava_mckinseyco.pdf::section103::chunk_7
  - preview: REP Article I. Performance Management, Monitoring, And Reporting. Section A. Required Reporting Form, Format, or Data Elements for Interim and Final Performance Repo rts. RESERVED - Langu...
- score: 0.4527
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section142
  - chunk_id: dmava_mckinseyco.pdf::section142::chunk_8
  - preview: (1) Outcomes are distinct from inputs needed to achieve the outcomes, such as amounts or percentages of time that subrecipient employees or other participants will spend on the project or...
- score: 0.4475
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section101
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section101::chunk_2
  - preview: n benchmarking and performance comparison 99 Annual Report 2025Company ReportNon-Financial ReportCorporate GovernanceRemuneration ReportFinancial StatementsAdditional Information
- score: 0.4425
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section100
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section100::chunk_7
  - preview: In an industry where reliable, comparable data is limited, Relative Revenue Growth (RRG) stands out as the most transparent measure of competitive performance. It enables us to assess pro...

### Query: Find examples related to leadership

- score: 0.4346
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section6
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section6::chunk_9
  - preview: SHARING EXAMPLES
- score: 0.4333
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section60
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section60::chunk_3
  - preview: [Among the assignments in which the staff has been involved, indicate the following information for those assignments that best illustrate staff capability to handle th e tasks listed und...
- score: 0.4326
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section54
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section54::chunk_4
  - preview: [Among the assignments in which the staff has been involved, indicate the following information for those assignments that best illustrate staff capability to handle the tasks listed unde...
- score: 0.4326
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section64
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section64::chunk_5
  - preview: [Among the assignments in which the staff has been involved, indicate the following information for those assignments that best illustrate staff capability to handle the tasks listed unde...
- score: 0.4326
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section43
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section43::chunk_2
  - preview: [Among the assignments in which the staff has been involved, indicate the following information for those assignments that best illustrate staff capability to handle the tasks listed unde...

### Query: Show documents discussing strategy

- score: 0.4301
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\PHE-case-study-ppt.Final_.pptx
  - section_heading: section4
  - chunk_id: PHE-case-study-ppt.Final_.pptx::section4::chunk_2
  - preview: Understand the purpose or intention: Why are you writing it? What do you want to showcase? What are they key messages?
- score: 0.4218
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\IC-One-Page-Case-Study-Template-for-Microsoft-Word-Example_WORD.docx
  - section_heading: section1
  - chunk_id: IC-One-Page-Case-Study-Template-for-Microsoft-Word-Example_WORD.docx::section1::chunk_1
  - preview: ONE-PAGE CASE STUDY TEMPLATE for Microsoft Word EXAMPLE
- score: 0.4150
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section207
  - chunk_id: dmava_mckinseyco.pdf::section207::chunk_1
  - preview: documentation.
- score: 0.4139
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section99
  - chunk_id: dmava_mckinseyco.pdf::section99::chunk_4
  - preview: Section H. Review of Procurement Documents .
- score: 0.3942
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\IC-Problem-Solution-Impact-Case-Study-Template-for-Powerpoint-Example_Powerpoint.pptx
  - section_heading: section2
  - chunk_id: IC-Problem-Solution-Impact-Case-Study-Template-for-Powerpoint-Example_Powerpoint.pptx::section2::chunk_2
  - preview: Using this approach, you can effectively communicate the challenges, their repercussions, and their successful resolutions, thereby articulating a comprehensive and engaging case study pr...

### Query: Which tools or platforms were used in that shell project?

- score: 0.4266
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section16
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section16::chunk_3
  - preview: Description of Project:
- score: 0.4266
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section8
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section8::chunk_19
  - preview: Description of Project:
- score: 0.4266
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_12
  - preview: Description of Project:
- score: 0.3820
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section48
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section48::chunk_1
  - preview: Selection No. 1259359 Technical Proposal Annex 2 11. Detailed Tasks Assigned General role as GIS and DRR consul tant, particularly around GeoSAFE, QG IS and other open source tools. 12. W...
- score: 0.3569
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section11
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section11::chunk_5
  - preview: The work was carried out over the period 1 February 2017 – 31 May 2018 with the major work elements consisting of:

### Query: What examples exist of artificial intelligence initiatives?

- score: 0.5300
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section24
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section24::chunk_3
  - preview: CEOs expect AI to make nearly half of operational decisions by 2030. Percentage of decisions made by AI without human intervention, by typeFigure 3 of operational decisions arebeing made...
- score: 0.5232
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section25
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section25::chunk_2
  - preview: Before the next budget cycle closes, agree on a fixed reinvestment rate for AI-driven productivity gains (typically 60% to 80%) and commit to funding faster cycles of experimentation and...
- score: 0.5223
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section38
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section38::chunk_2
  - preview: 12 Still, CEOs say only 25% of the workforce is using AI regularly as part of their job—despite the fact that 86% of CEOs say employees have the skills to collaborate with AI. The gap bet...
- score: 0.5146
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section35
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section35::chunk_3
  - preview: “It’s not laying AI on top of your existing tools and services. It’s reimagining the entire process.” Pablo T. Rivero CEO, Resy; SVP, Global Dining, American Express, USForeword Introduct...
- score: 0.5144
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section9
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section9::chunk_3
  - preview: In The enterprise in 2030 , IBM IBV analysis unveiled five predictions that will define the business landscape of the future.2 Our 2026 CEO Study identifies the plays CEOs must make now t...

### Query: Find prior implementation experience

- score: 0.3929
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section20
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section20::chunk_2
  - preview: 20 4 Description of Approach, Methodology and Work Plan
- score: 0.3606
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section20
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section20::chunk_3
  - preview: 4.1 Technical Approach and Methodology
- score: 0.3565
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section140
  - chunk_id: dmava_mckinseyco.pdf::section140::chunk_5
  - preview: a. Determine that the subrecipient has completed its programmatic performance under the subaward and all applicable administrative actions; or
- score: 0.3565
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section48
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section48::chunk_8
  - preview: These measures are embedded in local operating procedures and are supported by our Internal Control Standards, which define minimum requirements for onboarding, training, documentation an...
- score: 0.3438
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section46
  - chunk_id: dmava_mckinseyco.pdf::section46::chunk_4
  - preview: d. Identify one -time costs associated with implementation of the DMAVA transition plan, i.e., capital improvements needed to support the transition plan, additional equipment to include...

### Query: Show examples of organizational transformation

- score: 0.4702
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section36
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section36::chunk_1
  - preview: 34Our analysis shows that leaders who have made the most progress breaking down functional boundaries are executing on strategy faster than the competition. Organizations that have redesi...
- score: 0.4614
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section46
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section46::chunk_1
  - preview: 44Study design and sample The IBM Institute for Business Value conducted a global CEO survey from February to April 2026 to examine how organizations are redesigning leadership models, op...
- score: 0.4273
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section34
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section34::chunk_2
  - preview: The payoff: CEOs who actively redesign how teams work together are more than twice as likely to have delivered on their business objectives. 32Foreword Introduction Rethink the C-suiteCre...
- score: 0.4222
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section10
  - chunk_id: dmava_mckinseyco.pdf::section10::chunk_3
  - preview: Exhibit 1. McKinsey’s Organizational D esign Framework
- score: 0.4161
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section6
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section6::chunk_2
  - preview: 1 Consultant’s Organization

### Query: What blockchain project was implemented?

- score: 0.5046
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_12
  - preview: Description of Project:
- score: 0.5046
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section16
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section16::chunk_3
  - preview: Description of Project:
- score: 0.5046
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section8
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section8::chunk_19
  - preview: Description of Project:
- score: 0.4583
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section10
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section10::chunk_6
  - preview: The main goals of the project as outlined in the contract were:
- score: 0.4284
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section95
  - chunk_id: dmava_mckinseyco.pdf::section95::chunk_14
  - preview: Section B. Inventions Developed under the Award .

### Query: Find autonomous vehicle work

- score: 0.4091
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section14
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section14::chunk_3
  - preview: The business adapted quickly to changing market conditions, strengthening proximity to clients and candidates to offer responsiveness and personalized coaching at every stage, and leverag...
- score: 0.3686
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section38
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section38::chunk_2
  - preview: 12 Still, CEOs say only 25% of the workforce is using AI regularly as part of their job—despite the fact that 86% of CEOs say employees have the skills to collaborate with AI. The gap bet...
- score: 0.3643
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section12
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section12::chunk_4
  - preview: We are building on more than a decade of deep AI know-how with a range of attractive offerings under the Akkodis Intelligence approach. • r.Potential: We launched r.Potential in 2025, a j...
- score: 0.3637
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\2026-ceo-study-rewiring-the-c-suite-report.pdf
  - section_heading: section27
  - chunk_id: 2026-ceo-study-rewiring-the-c-suite-report.pdf::section27::chunk_5
  - preview: Automation in order fulfillment rose from 60% to between 80% and 90%, with 10 of 12 tests successfully running warehouse automations at 120% of peak order volume. These outcomes have not...
- score: 0.3542
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\the-adecco-group-annual-report-2025.pdf
  - section_heading: section59
  - chunk_id: the-adecco-group-annual-report-2025.pdf::section59::chunk_3
  - preview: In France, LHH supported the transformation of a traditional refinery into a battery production facility, prioritizing re-skilling, local employment and social continuity rather than redu...

### Query: Show aerospace projects

- score: 0.5211
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section8
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section8::chunk_19
  - preview: Description of Project:
- score: 0.5211
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section16
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section16::chunk_3
  - preview: Description of Project:
- score: 0.5211
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\challengefund3-technicalproposal-kartoza.pdf
  - section_heading: section12
  - chunk_id: challengefund3-technicalproposal-kartoza.pdf::section12::chunk_12
  - preview: Description of Project:
- score: 0.4220
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\Resume-Sample-1-Software-Engineer.pdf
  - section_heading: section1
  - chunk_id: Resume-Sample-1-Software-Engineer.pdf::section1::chunk_8
  - preview: SOFTWARE ENGINEERING PROJECTS
- score: 0.3885
  - source_file: C:\DTI 5902\dffrnt-airgapped-ai-assistant\database\raw\Client_Related\dmava_mckinseyco.pdf
  - section_heading: section29
  - chunk_id: dmava_mckinseyco.pdf::section29::chunk_4
  - preview:  NASA – ARMD Sustainable Leadership Effort. Led year-long workshop- based efforts for the ARMD senior leadership team focused on aligning on a common vision, building trust, making decis...

## C. Overall readiness recommendation

Database is structurally ready, but baseline search needs tuning.
