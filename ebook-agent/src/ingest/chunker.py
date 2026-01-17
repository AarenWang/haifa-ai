from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class Chunk:
    text: str
    index: int


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: List[Chunk] = []
    start = 0
    index = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunk_text = normalized[start:end]
        chunks.append(Chunk(text=chunk_text, index=index))
        index += 1
        if end == len(normalized):
            break
        start = max(end - overlap, 0)
    return chunks


def chunk_sections(sections: Iterable[tuple[str, str]], chunk_size: int, overlap: int) -> List[tuple[str, Chunk]]:
    results: List[tuple[str, Chunk]] = []
    for section_title, section_text in sections:
        for chunk in chunk_text(section_text, chunk_size=chunk_size, overlap=overlap):
            results.append((section_title, chunk))
    return results
