import urllib.error

from dffrnt_assistant.ollama import OllamaClient


def test_embed_texts_batches_requests():
    calls = []
    client = OllamaClient("http://x", "m", "embed")

    def fake_post(path, payload):
        calls.append((path, len(payload["input"])))
        return {"embeddings": [[0.0] for _ in payload["input"]]}

    client._post = fake_post
    out = client.embed_texts([f"t{i}" for i in range(150)], batch_size=64)

    assert len(out) == 150
    assert [n for _, n in calls] == [64, 64, 22]
    assert all(path == "/api/embed" for path, _ in calls)


def test_embed_texts_falls_back_to_classic_endpoint():
    client = OllamaClient("http://x", "m", "embed")

    def fake_post(path, payload):
        if path == "/api/embed":
            raise urllib.error.HTTPError("u", 404, "not found", {}, None)
        return {"embedding": [0.1]}

    client._post = fake_post
    out = client.embed_texts(["a", "b"], batch_size=64)

    assert out == [[0.1], [0.1]]
    assert client._use_batch_embed is False


def test_embed_on_cpu_pins_embeddings_to_cpu():
    seen = []
    client = OllamaClient("http://x", "m", "embed", embed_on_cpu=True)

    def fake_post(path, payload):
        seen.append(payload)
        return {"embeddings": [[0.0]]}

    client._post = fake_post
    client.embed_query("hi")
    assert seen[0]["options"] == {"num_gpu": 0}   # embedder forced off the GPU


def test_embeddings_carry_no_options_by_default():
    seen = []
    client = OllamaClient("http://x", "m", "embed")   # embed_on_cpu defaults False

    def fake_post(path, payload):
        seen.append(payload)
        return {"embeddings": [[0.0]]}

    client._post = fake_post
    client.embed_query("hi")
    assert "options" not in seen[0]                # Ollama places the embedder itself


def test_generate_forwards_think_flag():
    seen = []
    client = OllamaClient("http://x", "m", "embed")

    def fake_post(path, payload):
        seen.append(payload)
        return {"response": "ok"}

    client._post = fake_post
    assert client.generate("p", think=False) == "ok"
    assert seen[0]["think"] is False
    assert client.generate("p") == "ok"
    assert "think" not in seen[1]                  # None sends nothing


def test_generate_retries_without_think_on_400():
    # A model without thinking support rejects the field; the call must still
    # succeed by retrying without it (summaries would otherwise fall back to a
    # raw excerpt).
    seen = []
    client = OllamaClient("http://x", "m", "embed")

    def fake_post(path, payload):
        seen.append(payload)
        if "think" in payload:
            raise urllib.error.HTTPError("u", 400, "no thinking support", {}, None)
        return {"response": "ok"}

    client._post = fake_post
    assert client.generate("p", think=False) == "ok"
    assert "think" in seen[0] and "think" not in seen[1]


def test_warmup_loads_llm_and_embedder():
    calls = []
    client = OllamaClient("http://x", "llm-model", "embed-model")

    def fake_post(path, payload):
        calls.append((path, payload))
        return {"embeddings": [[0.0]]}

    client._post = fake_post
    client.warmup()

    assert [p for p, _ in calls] == ["/api/generate", "/api/embed"]
    generate_payload = calls[0][1]
    assert generate_payload["model"] == "llm-model"
    assert "prompt" not in generate_payload        # load-only: nothing generated
    assert generate_payload["keep_alive"] == -1    # stays resident once loaded
    assert generate_payload["options"] == client.gen_options  # same runner config
