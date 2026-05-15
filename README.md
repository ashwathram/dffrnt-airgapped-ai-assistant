# Air-Gapped Private AI Knowledge and Content Assistant for DFFRNT

**A secure, fully offline AI system for DFFRNT** — built with open-source models and Retrieval-Augmented Generation (RAG).

![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![License](https://img.shields.io/badge/License-MIT-blue)

## Overview

This project delivers a **private, air-gapped AI assistant** that serves as DFFRNT’s internal “central brain”. It ingests and organizes confidential company knowledge (projects, proposals, timesheets, resumes, etc.) and supports high-value tasks such as:

- Generating tailored resumes for RFP responses
- Drafting case studies and proposals
- Answering internal queries with grounded responses
- Extracting insights from historical project data

The system runs **completely offline** on dedicated hardware to ensure maximum data privacy and security.

---

## Key Features

- Fully air-gapped deployment (no internet required after setup)
- Retrieval-Augmented Generation (RAG) for accurate, source-grounded answers
- Single conversational interface
- Specialized agents/tools for resume generation and content creation
- Document ingestion pipeline (PDF, Word, PowerPoint, CSV)
- Source attribution and hallucination mitigation
- Designed for easy maintenance by DFFRNT’s technical team

---

## Architecture

```mermaid
graph TD
    A[Client Documents] --> B[Ingestion Pipeline]
    B --> C[Vector Database + Metadata]
    D[Local LLM] <--> C
    E[Conversational UI] <--> D
    F[RFP Resume Generator] <--> D
    G[Content Drafter] <--> D
