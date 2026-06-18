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
