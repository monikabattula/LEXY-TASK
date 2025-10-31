from pathlib import Path
from typing import Tuple

from .config import settings


def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", "."))


def document_upload_path(document_id: str, filename: str) -> Path:
    fname = safe_filename(filename)
    return settings.uploads_dir / document_id / fname


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_bytes(path: Path, data: bytes) -> Tuple[Path, int]:
    ensure_parent(path)
    path.write_bytes(data)
    return path, len(data)


