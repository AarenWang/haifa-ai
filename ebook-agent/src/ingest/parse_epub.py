from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub


@dataclass
class EpubSection:
    title: str
    text: str


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def parse_epub(path: Path) -> List[EpubSection]:
    book = epub.read_epub(str(path))
    sections: List[EpubSection] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        title = item.get_name()
        text = _extract_text(item.get_content().decode("utf-8", errors="ignore"))
        if not text:
            continue
        sections.append(EpubSection(title=title, text=text))
    return sections
