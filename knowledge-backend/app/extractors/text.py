from pathlib import Path

def extract_txt_or_md(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8", errors="ignore").strip()