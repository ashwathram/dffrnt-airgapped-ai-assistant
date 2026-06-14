import httpx, os, json, sys
sys.path.append("..")

BASE = "http://localhost:8000"

def test_health():
    r = httpx.get(f"{BASE}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    print("PASS: Health check")

def test_query_returns_answer():
    r = httpx.post(
        f"{BASE}/api/query",
        json={"question": "What does DFFRNT specialize in?"},
        timeout=1200,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["answer"]) > 20,  "Answer too short"
    assert len(data["sources"]) > 0,  "No sources returned"
    print(f"PASS: Query answered ({len(data['answer'])} chars, "
          f"{len(data['sources'])} sources)")
    print(f"      Answer preview: {data['answer'][:80]}...")

def test_source_citation():
    r = httpx.post(
        f"{BASE}/api/query",
        json={"question": "Who has healthcare experience?"},
        timeout=1200,
    )
    data = r.json()
    sources = [s["filename"] for s in data["sources"]]
    assert "test_doc.txt" in sources, "Expected test_doc.txt in sources"
    print(f"PASS: Source citation working — sources: {sources}")

def test_empty_question_rejected():
    r = httpx.post(
        f"{BASE}/api/query",
        json={"question": ""},
        timeout=30
    )
    assert r.status_code == 400
    print("PASS: Empty question correctly rejected")

def test_audit_log_exists():
    assert os.path.exists("logs/audit.jsonl"), "Audit log not found"
    lines = open("logs/audit.jsonl").readlines()
    assert len(lines) > 0, "Audit log is empty"
    events = [json.loads(l)["event_type"] for l in lines]
    print(f"PASS: Audit log has {len(lines)} events: {set(events)}")

if __name__ == "__main__":
    print("=" * 50)
    print("DFFRNT AI System Tests")
    print("=" * 50 + "\n")
    test_health()
    test_query_returns_answer()
    test_source_citation()
    test_empty_question_rejected()
    test_audit_log_exists()
    print("\n" + "=" * 50)
    print("All tests PASSED ✓")
    print("=" * 50)
