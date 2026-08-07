from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
USER_DATA = BASE_DIR / "user_data"
DOCUMENTS_DIR = USER_DATA / "documents"
PROCESSED_DIR = USER_DATA / "processed"
DB_PATH = USER_DATA / "metadata.db"

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)