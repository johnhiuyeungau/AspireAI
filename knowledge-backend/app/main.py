import uuid
import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import aiofiles

from .config import DOCUMENTS_DIR, CHUNKS_DIR
from .database import init_db, get_connection
from .extractors import extract_text
from .chunker import chunk_text, build_chunk_id
from .embeddings import (
    index_document_chunks,
    index_all_active_documents,
    remove_document_from_index,
    query_similar,
)

# ---------- App must be created FIRST ----------
app = FastAPI(title="Knowledge Intelligence Engine - MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# near top
_mdns_service = None

@app.on_event("startup")
def startup():
    global _mdns_service
    init_db()
    print("Database initialized")
    print(f"Documents folder: {DOCUMENTS_DIR}")
    print(f"Chunks folder: {CHUNKS_DIR}")
    
    try:
        from .mdns import start_mdns
        _mdns_service = start_mdns(8000)
    except Exception as e:
        print(f"mDNS skipped: {e}")


@app.on_event("shutdown")
def shutdown():
    global _mdns_service
    if _mdns_service is not None:
        try:
            _mdns_service.unregister_all_services()
            _mdns_service.close()
        except Exception:
            pass
        _mdns_service = None


def process_document_chunks(document_id: str) -> dict:
    """
    Read extracted text, chunk it, store in SQLite + JSON, then embed.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT id, original_name, subject, status FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")

    text_path = DOCUMENTS_DIR / f"{document_id}.txt"
    if not text_path.exists():
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Extracted text not found. Re-upload the document.",
        )

    text = text_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        conn.close()
        raise HTTPException(status_code=400, detail="Document text is empty")

    # Remove old chunks (re-chunk safe)
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    pieces = chunk_text(text)
    now = datetime.utcnow().isoformat()
    saved = []

    for piece in pieces:
        chunk_id = build_chunk_id(document_id, piece["chunk_index"])
        conn.execute(
            """
            INSERT INTO chunks (id, document_id, chunk_index, text, token_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                document_id,
                piece["chunk_index"],
                piece["text"],
                piece["token_count"],
                now,
            ),
        )
        saved.append({
            "id": chunk_id,
            "chunk_index": piece["chunk_index"],
            "token_count": piece["token_count"],
        })

    conn.execute(
        "UPDATE documents SET status = ? WHERE id = ?",
        ("chunked", document_id),
    )
    conn.commit()
    conn.close()

    # Debug JSON copy
    out = {
        "document_id": document_id,
        "original_name": row["original_name"],
        "subject": row["subject"],
        "chunk_count": len(saved),
        "chunks": [
            {
                "id": build_chunk_id(document_id, p["chunk_index"]),
                "chunk_index": p["chunk_index"],
                "token_count": p["token_count"],
                "text": p["text"],
            }
            for p in pieces
        ],
    }
    json_path = CHUNKS_DIR / f"{document_id}.json"
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Embeddings (skips if silenced)
    try:
        index_result = index_document_chunks(document_id)
    except Exception as e:
        print(f"Embedding index failed for {document_id}: {e}")
        index_result = {"indexed": 0, "error": str(e)}

    return {
        "document_id": document_id,
        "original_name": row["original_name"],
        "chunk_count": len(saved),
        "indexed_chunks": index_result.get("indexed", 0),
        "status": "chunked",
        "chunks": saved,
    }


@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Knowledge Intelligence Engine ready",
        "version": "MVP-1.0",
        "pdf_engine": "pypdf (free commercial license)",
    }


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    subject: str = Form("General"),
    level: str = Form("Unknown"),
    purpose: str = Form("Learning"),
):
    allowed = {".pdf", ".docx", ".txt", ".md", ".markdown"}
    original_name = file.filename or "unknown"
    suffix = Path(original_name).suffix.lower()

    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")

    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}{suffix}"
    save_path = DOCUMENTS_DIR / safe_name

    try:
        async with aiofiles.open(save_path, "wb") as f:
            content = await file.read()
            await f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    try:
        text = extract_text(str(save_path), suffix)
        text_length = len(text)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {str(e)}")

    text_path = DOCUMENTS_DIR / f"{doc_id}.txt"
    text_path.write_text(text, encoding="utf-8")

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO documents (
            id, filename, original_name, subject, level, purpose,
            file_type, file_path, text_length, uploaded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            safe_name,
            original_name,
            subject,
            level,
            purpose,
            suffix.lstrip("."),
            str(save_path),
            text_length,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    chunk_count = 0
    indexed_chunks = 0
    try:
        chunk_result = process_document_chunks(doc_id)
        chunk_count = chunk_result.get("chunk_count", 0)
        indexed_chunks = chunk_result.get("indexed_chunks", 0)
    except Exception as e:
        print(f"Chunking failed for {doc_id}: {e}")

    return {
        "document_id": doc_id,
        "original_name": original_name,
        "subject": subject,
        "level": level,
        "purpose": purpose,
        "text_length": text_length,
        "chunk_count": chunk_count,
        "indexed_chunks": indexed_chunks,
        "status": "chunked" if chunk_count > 0 else "extracted",
        "message": (
            "Document uploaded, text extracted, chunked, and indexed successfully"
            if chunk_count > 0
            else "Document uploaded and text extracted (chunking failed)"
        ),
    }


@app.get("/api/documents")
def list_documents():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, original_name, subject, level, purpose, file_type,
               text_length, uploaded_at, status, silenced
        FROM documents
        ORDER BY uploaded_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


@app.patch("/api/documents/{doc_id}/silence")
def toggle_silence(doc_id: str, silenced: bool = True):
    conn = get_connection()
    cur = conn.execute(
        "UPDATE documents SET silenced = ? WHERE id = ?",
        (1 if silenced else 0, doc_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")
    conn.commit()
    conn.close()

    if silenced:
        remove_document_from_index(doc_id)
    else:
        try:
            index_document_chunks(doc_id)
        except Exception as e:
            print(f"Re-index after unsilence failed: {e}")

    return {
        "document_id": doc_id,
        "silenced": silenced,
        "message": "Document silenced" if silenced else "Document activated",
    }


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT file_path FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(row["file_path"])

    try:
        if file_path.exists():
            file_path.unlink()
        txt_version = DOCUMENTS_DIR / f"{doc_id}.txt"
        if txt_version.exists():
            txt_version.unlink()
        json_version = CHUNKS_DIR / f"{doc_id}.json"
        if json_version.exists():
            json_version.unlink()
    except Exception as e:
        print(f"Warning: could not delete files for {doc_id}: {e}")

    # Vector index first, then DB
    remove_document_from_index(doc_id)
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

    return {"document_id": doc_id, "message": "Document deleted successfully"}


@app.post("/api/documents/chunk-all")
def chunk_all_pending():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id FROM documents
        WHERE status != 'chunked' OR status IS NULL
        ORDER BY uploaded_at ASC
        """
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        try:
            result = process_document_chunks(row["id"])
            results.append({
                "document_id": row["id"],
                "ok": True,
                "chunk_count": result["chunk_count"],
                "indexed_chunks": result.get("indexed_chunks", 0),
            })
        except Exception as e:
            results.append({"document_id": row["id"], "ok": False, "error": str(e)})

    return {"processed": len(results), "results": results}


@app.post("/api/documents/{doc_id}/chunk")
def chunk_document(doc_id: str):
    return process_document_chunks(doc_id)


@app.get("/api/documents/{doc_id}/chunks")
def get_document_chunks(
    doc_id: str,
    include_text: bool = Query(False, description="Include full chunk text"),
):
    conn = get_connection()
    doc = conn.execute(
        "SELECT id, original_name, silenced FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if not doc:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")

    if include_text:
        rows = conn.execute(
            """
            SELECT id, chunk_index, token_count, created_at, text
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
            """,
            (doc_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, chunk_index, token_count, created_at
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
            """,
            (doc_id,),
        ).fetchall()
    conn.close()

    return {
        "document_id": doc_id,
        "original_name": doc["original_name"],
        "silenced": bool(doc["silenced"]),
        "chunk_count": len(rows),
        "chunks": [dict(r) for r in rows],
    }


@app.get("/api/chunks")
def list_all_chunks(
    active_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=1000),
):
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.token_count, c.created_at,
                   d.original_name, d.subject, d.silenced
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.silenced = 0
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.token_count, c.created_at,
                   d.original_name, d.subject, d.silenced
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/index/document/{doc_id}")
def index_one(doc_id: str):
    try:
        return index_document_chunks(doc_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/index/all")
def index_all():
    return index_all_active_documents()


@app.get("/api/search")
def semantic_search(
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
    subject: str = Query(None),
):
    hits = query_similar(q, top_k=top_k, subject=subject)
    return {"query": q, "top_k": top_k, "results": hits}