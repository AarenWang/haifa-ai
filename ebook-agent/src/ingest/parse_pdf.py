from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pdfplumber


@dataclass
class PdfSection:
    title: str
    text: str
    page_label: str


def parse_pdf(path: Path) -> List[PdfSection]:
    sections: List[PdfSection] = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            if not normalized:
                continue
            sections.append(
                PdfSection(
                    title=f"Page {index}",
                    text=normalized,
                    page_label=str(index),
                )
            )
    return sections
