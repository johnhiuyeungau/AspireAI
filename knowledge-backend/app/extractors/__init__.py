from .pdf import extract_pdf
from .docx import extract_docx
from .text import extract_txt_or_md

def extract_text(file_path: str, file_type: str) -> str:
    file_type = file_type.lower().lstrip(".")
    if file_type == "pdf":
        return extract_pdf(file_path)
    elif file_type in ("docx", "doc"):
        return extract_docx(file_path)
    elif file_type in ("txt", "md", "markdown"):
        return extract_txt_or_md(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")