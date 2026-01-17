from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid


SUPPORTED_EXTENSIONS = {".pdf", ".epub"}


@dataclass(frozen=True)
class BookFile:
    book_id: str
    title: str
    path: Path
    extension: str


def _build_book_id(path: Path) -> str:
    stat = path.stat()
    fingerprint = f"{path.resolve()}::{stat.st_size}::{stat.st_mtime}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))


def scan_books(books_dir: Path) -> list[BookFile]:
    if not books_dir.exists():
        return []

    results: list[BookFile] = []
    for item in sorted(books_dir.iterdir()):
        if not item.is_file():
            continue
        if item.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        results.append(
            BookFile(
                book_id=_build_book_id(item),
                title=item.stem,
                path=item,
                extension=item.suffix.lower(),
            )
        )
    return results
