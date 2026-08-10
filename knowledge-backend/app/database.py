import sqlite3
from .config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            original_name TEXT,
            subject TEXT,
            level TEXT,
            purpose TEXT,
            file_type TEXT,
            file_path TEXT,
            text_length INTEGER,
            uploaded_at TEXT,
            status TEXT DEFAULT 'extracted',
            silenced INTEGER DEFAULT 0
        )
    """)

    try:
        conn.execute("ALTER TABLE documents ADD COLUMN silenced INTEGER DEFAULT 0")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            token_count INTEGER,
            created_at TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_document_id
        ON chunks(document_id)
    """)

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_doc_index
        ON chunks(document_id, chunk_index)
    """)

    conn.commit()
    conn.close()