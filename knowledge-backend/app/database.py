import sqlite3
from datetime import datetime
from .config import DB_PATH

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    # Migration for existing databases
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN silenced INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists
    conn.commit()
    conn.close()