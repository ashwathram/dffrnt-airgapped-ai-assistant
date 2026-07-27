"""End-to-end smoke tests.

These require a live API server plus Qdrant and Ollama, so they are marked
``integration`` and skipped by default. Run them explicitly with::

    pytest -m integration

Configure the target with DFFRNT_BASE_URL and AUDIT_LOG_PATH.
"""

import json
import os

import httpx
import pytest

pytestmark = pytest.mark.integration

BASE = os.getenv("DFFRNT_BASE_URL", "http://localhost:8000")
AUDIT_LOG = os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl")


def test_health():
    response = httpx.get(f"{BASE}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_query_returns_answer():
    response = httpx.post(
        f"{BASE}/api/query",
        json={"question": "What does DFFRNT specialize in?"},
        timeout=1200,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["answer"]) > 20, "Answer too short"
    assert len(data["sources"]) > 0, "No sources returned"


def test_empty_question_rejected():
    response = httpx.post(f"{BASE}/api/query", json={"question": ""}, timeout=30)
    assert response.status_code == 400


def test_audit_log_exists():
    assert os.path.exists(AUDIT_LOG), "Audit log not found"
    lines = open(AUDIT_LOG).readlines()
    assert lines, "Audit log is empty"
    events = {json.loads(line)["event_type"] for line in lines}
    assert events
