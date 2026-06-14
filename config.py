import os

# Change this to switch environments
# "aws"        = AWS g4dn.xlarge (you are here)
# "macbook"    = Intel MacBook (tiny model)
# "production" = Client Mac Studio M3 Ultra
ENVIRONMENT = os.getenv("ENVIRONMENT", "aws")

MODELS = {
    "macbook":    "qwen2.5:0.5b",
    "aws":        "qwen2.5:7b",
    "production": "llama3.3:70b-instruct-q8_0",
}

LLM_MODEL       = MODELS[ENVIRONMENT]
EMBED_MODEL     = "nomic-embed-text"
OLLAMA_URL      = "http://localhost:11434"
QDRANT_URL      = "http://localhost:6333"
API_HOST        = "0.0.0.0"
API_PORT        = 8000
COLLECTION_NAME = "dffrnt_documents"
VECTOR_SIZE     = 768
TOP_K_RESULTS   = 5
CHUNK_SIZE      = 512
CHUNK_OVERLAP   = 64
AUDIT_LOG_PATH  = "logs/audit.jsonl"

print(f"[Config] Environment : {ENVIRONMENT}")
print(f"[Config] LLM Model   : {LLM_MODEL}")
