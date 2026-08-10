from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
USER_DATA = BASE_DIR / "user_data"
DOCUMENTS_DIR = USER_DATA / "documents"
PROCESSED_DIR = USER_DATA / "processed"
CHUNKS_DIR = PROCESSED_DIR / "chunks"
CHROMA_DIR = USER_DATA / "chroma"
MODELS_DIR = USER_DATA / "models"          # for GGUF LLM files
DB_PATH = USER_DATA / "metadata.db"

# Embeddings
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
CHROMA_COLLECTION_NAME = "knowledge_chunks"

# Chunking (keep in sync with chunker.py if you centralize settings)
CHUNK_SIZE_TOKENS = 1000
CHUNK_OVERLAP_TOKENS = 150

# Retrieval / RAG (Phase 7)
RAG_TOP_K = 5

# Local LLM (Phase 7) — fill in when you add llama.cpp
LLM_MODEL_PATH = MODELS_DIR / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
LLM_N_CTX = 4096
LLM_N_THREADS = 4

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)