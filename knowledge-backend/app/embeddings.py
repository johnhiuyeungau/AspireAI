"""
Local Embedding + Chroma vector store
- Model: BAAI/bge-small-en-v1.5 (MIT, commercial OK)
- Only indexes chunks from non-silenced documents
"""

from __future__ import annotations
from typing import List, Dict, Optional
import threading

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

from .config import (
    EMBEDDING_MODEL_NAME,
    CHROMA_DIR,
    CHROMA_COLLECTION_NAME,
)
from .database import get_connection

_model = None
_model_lock = threading.Lock()
_chroma_client = None
_collection = None

# Encode in batches to limit RAM on large documents
EMBED_BATCH_SIZE = 32


def get_embedding_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
                _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                print("Embedding model ready")
    return _model


def get_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_embedding_model()
    vectors = model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def index_document_chunks(document_id: str) -> Dict:
    """
    Embed all chunks for one document and upsert into Chroma.
    Skips if document is silenced.
    """
    conn = get_connection()
    doc = conn.execute(
        """
        SELECT id, original_name, subject, level, purpose, silenced
        FROM documents WHERE id = ?
        """,
        (document_id,),
    ).fetchone()

    if not doc:
        conn.close()
        raise ValueError(f"Document not found: {document_id}")

    # Snapshot fields before close
    original_name = doc["original_name"] or ""
    subject = doc["subject"] or ""
    level = doc["level"] or ""
    purpose = doc["purpose"] or ""
    is_silenced = bool(doc["silenced"])

    # Always remove existing vectors for this doc first
    _delete_document_vectors(document_id)

    if is_silenced:
        conn.close()
        return {
            "document_id": document_id,
            "indexed": 0,
            "skipped": True,
            "reason": "document is silenced",
        }

    rows = conn.execute(
        """
        SELECT id, chunk_index, text, token_count
        FROM chunks
        WHERE document_id = ?
        ORDER BY chunk_index ASC
        """,
        (document_id,),
    ).fetchall()
    conn.close()

    if not rows:
        return {
            "document_id": document_id,
            "indexed": 0,
            "skipped": True,
            "reason": "no chunks",
        }

    ids = [r["id"] for r in rows]
    documents = [r["text"] for r in rows]
    metadatas = [
        {
            "document_id": document_id,
            "chunk_index": int(r["chunk_index"]),
            "original_name": original_name,
            "subject": subject,
            "level": level,
            "purpose": purpose,
            "token_count": int(r["token_count"] or 0),
        }
        for r in rows
    ]

    embeddings = embed_texts(documents)
    collection = get_collection()
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    return {
        "document_id": document_id,
        "indexed": len(ids),
        "skipped": False,
    }


def _delete_document_vectors(document_id: str) -> int:
    collection = get_collection()
    try:
        existing = collection.get(
            where={"document_id": {"$eq": document_id}}
        )
    except Exception:
        # Fallback for older Chroma versions
        existing = collection.get(where={"document_id": document_id})

    ids = existing.get("ids") or []
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def remove_document_from_index(document_id: str) -> Dict:
    deleted = _delete_document_vectors(document_id)
    return {"document_id": document_id, "removed": deleted}


def index_all_active_documents() -> Dict:
    """Index every non-silenced document that has chunks."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.id
        FROM documents d
        WHERE d.silenced = 0
          AND EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
        ORDER BY d.uploaded_at ASC
        """
    ).fetchall()
    conn.close()

    results = []
    total = 0
    for row in rows:
        try:
            r = index_document_chunks(row["id"])
            total += r.get("indexed", 0)
            results.append({"document_id": row["id"], "ok": True, **r})
        except Exception as e:
            results.append({"document_id": row["id"], "ok": False, "error": str(e)})

    return {
        "documents_processed": len(results),
        "chunks_indexed": total,
        "results": results,
    }


def query_similar(
    query: str,
    top_k: int = 5,
    subject: Optional[str] = None,
) -> List[Dict]:
    """
    Semantic search over active (non-silenced) chunks.
    Silenced docs are excluded because their vectors are removed on silence.
    """
    if not query or not query.strip():
        return []

    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    n_results = min(top_k, count)
    q_emb = embed_texts([query.strip()])[0]

    where = None
    if subject:
        where = {"subject": {"$eq": subject}}

    try:
        result = collection.query(
            query_embeddings=[q_emb],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        # e.g. filter matches nothing
        print(f"Chroma query failed: {e}")
        return []

    hits = []
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    for i, chunk_id in enumerate(ids):
        distance = float(dists[i]) if i < len(dists) else None
        score = (1.0 - distance) if distance is not None else None
        meta = metas[i] if i < len(metas) else {}
        hits.append({
            "chunk_id": chunk_id,
            "text": docs[i] if i < len(docs) else "",
            "score": score,
            "distance": distance,
            "document_id": meta.get("document_id"),
            "original_name": meta.get("original_name"),
            "subject": meta.get("subject"),
            "chunk_index": meta.get("chunk_index"),
            "token_count": meta.get("token_count"),
        })

    return hits