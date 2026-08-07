import uuid
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import aiofiles

from .config import DOCUMENTS_DIR
from .database import init_db, get_connection
from .extractors import extract_text

app = FastAPI(title="Knowledge Intelligence Engine - MVP Step 1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()
    print("Database initialized")
    print(f"Documents folder: {DOCUMENTS_DIR}")

@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Knowledge Intelligence Engine - Document Ingestion ready",
        "version": "MVP-1.0",
        "pdf_engine": "pypdf (free commercial license)"
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

    # Save original file
    try:
        async with aiofiles.open(save_path, "wb") as f:
            content = await file.read()
            await f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Extract text
    try:
        text = extract_text(str(save_path), suffix)
        text_length = len(text)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {str(e)}")

    # Save extracted plain text
    text_path = DOCUMENTS_DIR / f"{doc_id}.txt"
    text_path.write_text(text, encoding="utf-8")

    # Save metadata
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

    return {
        "document_id": doc_id,
        "original_name": original_name,
        "subject": subject,
        "level": level,
        "purpose": purpose,
        "text_length": text_length,
        "status": "extracted",
        "message": "Document uploaded and text extracted successfully"
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

@app.patch("/api/documents/{doc_id}/silence")
def toggle_silence(doc_id: str, silenced: bool = True):
    """
    Silence or re-activate a document.
    Silenced documents will be ignored by the retrieval engine later.
    """
    conn = get_connection()
    cur = conn.execute(
        "UPDATE documents SET silenced = ? WHERE id = ?",
        (1 if silenced else 0, doc_id)
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")
    conn.commit()
    conn.close()
    return {
        "document_id": doc_id,
        "silenced": silenced,
        "message": "Document silenced" if silenced else "Document activated"
    }


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    """
    Permanently delete a document (file + extracted text + metadata).
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT file_path FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(row["file_path"])
    text_path = file_path.with_suffix(".txt") if file_path.suffix != ".txt" else None

    # Delete physical files
    try:
        if file_path.exists():
            file_path.unlink()
        # Also delete the extracted .txt version
        txt_version = DOCUMENTS_DIR / f"{doc_id}.txt"
        if txt_version.exists():
            txt_version.unlink()
    except Exception as e:
        print(f"Warning: could not delete files for {doc_id}: {e}")

    # Delete metadata
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

    return {"document_id": doc_id, "message": "Document deleted successfully"}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)