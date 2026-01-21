#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ebook_vocab.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebook-vocab",
        description="Ebook vocabulary analyzer (spaCy): lemma frequency + NER entities.",
    )
    p.add_argument("book_path", help="Path to ebook file: .txt/.md/.epub/.pdf")
    p.add_argument("--out", default="./out", help="Output directory (default: ./out)")
    p.add_argument("--top-lemmas", type=int, default=5000, help="Top N lemmas to export")
    p.add_argument("--top-entities", type=int, default=2000, help="Top N entities per label to export")
    p.add_argument(
        "--keep-stopwords",
        action="store_true",
        help="Keep stopwords in lemma counts (default: filtered out).",
    )
    p.add_argument(
        "--include-entity-labels",
        default="PERSON,GPE,LOC,ORG,PRODUCT,EVENT,WORK_OF_ART,NORP,FAC",
        help="Comma-separated entity labels to export (default: common ones).",
    )
    p.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="For quick tests: limit analysis to first N characters (0 = no limit).",
    )
    p.add_argument(
        "--disable-epub-structured-filter",
        action="store_true",
        help="Disable EPUB TOC/spine structured filtering and only use keyword filtering.",
    )
    p.add_argument(
        "--disable-pdf-outline-filter",
        action="store_true",
        help="Disable PDF outline/bookmark filtering.",
    )
    p.add_argument(
        "--min-body-ratio",
        type=float,
        default=0.0,
        help="Minimum body-word ratio for chapter filtering (0 to disable).",
    )
    p.add_argument(
        "--min-chapter-words",
        type=int,
        default=0,
        help="Minimum body-word count for chapter filtering (0 to disable).",
    )
    p.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info).",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    labels = {s.strip() for s in args.include_entity_labels.split(",") if s.strip()}

    run_pipeline(
        book_path=Path(args.book_path),
        out_dir=Path(args.out),
        top_lemmas=args.top_lemmas,
        top_entities=args.top_entities,
        keep_stopwords=args.keep_stopwords,
        include_entity_labels=labels,
        max_chars=args.max_chars if args.max_chars > 0 else None,
        epub_structured_filter=not args.disable_epub_structured_filter,
        pdf_outline_filter=not args.disable_pdf_outline_filter,
        min_body_ratio=args.min_body_ratio,
        min_chapter_words=args.min_chapter_words,
    )


if __name__ == "__main__":
    main()
