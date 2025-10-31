from pathlib import Path
from typing import List, Tuple

from docx import Document


def extract_text_from_docx(file_path: Path) -> Tuple[str, List[Tuple[int, str]]]:
    """
    Extract text from .docx file.
    Returns (full_text, list of (paragraph_index, paragraph_text))
    """
    doc = Document(file_path)
    paragraphs = []
    full_text_parts = []
    
    for idx, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if text:
            paragraphs.append((idx, text))
            full_text_parts.append(text)
    
    full_text = "\n\n".join(full_text_parts)
    return full_text, paragraphs


def get_document_preview(file_path: Path, max_paragraphs: int = 10) -> str:
    """Get first N paragraphs for preview/context."""
    _, paragraphs = extract_text_from_docx(file_path)
    preview = "\n\n".join([text for _, text in paragraphs[:max_paragraphs]])
    return preview

