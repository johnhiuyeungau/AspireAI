from pypdf import PdfReader

def extract_pdf(file_path: str) -> str:
    """
    Extract text from PDF using pypdf (BSD license – fully free for commercial use).
    """
    reader = PdfReader(file_path)
    text_parts = []

    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            text_parts.append(text.strip())

    return "\n\n".join(text_parts).strip()