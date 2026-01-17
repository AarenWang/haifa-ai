from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from config.settings import AppSettings
from ingest.embed_store import ingest_books
from ingest.scan_books import scan_books
from query.answer import synthesize_answer
from query.retriever import retrieve_chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ebook Knowledge QA Agent")
    parser.add_argument(
        "--config",
        default=Path("./config/settings.yaml"),
        type=Path,
        help="配置文件路径",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ingest", help="导入电子书并建立索引")

    query_parser = subparsers.add_parser("query", help="提问")
    query_parser.add_argument("question", help="问题内容")

    return parser


def handle_ingest(settings: AppSettings) -> None:
    books = scan_books(settings.books_dir)
    results = ingest_books(books, settings)

    table = Table(title="导入结果")
    table.add_column("书名")
    table.add_column("Book ID")
    table.add_column("Chunk 数")
    table.add_column("状态")

    for result in results:
        status = "已跳过" if result.skipped else "已导入"
        table.add_row(result.title, result.book_id, str(result.chunks), status)

    console = Console()
    console.print(table)


def handle_query(question: str, settings: AppSettings) -> None:
    chunks = retrieve_chunks(question, settings)
    result = synthesize_answer(question, chunks, settings)

    console = Console()
    console.print("\n[bold]回答[/bold]")
    console.print(result.answer)
    console.print("\n[bold]引用[/bold]")
    console.print(result.citations if result.citations else "无引用内容")


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    settings = AppSettings.from_yaml(args.config)

    if args.command == "ingest":
        handle_ingest(settings)
    elif args.command == "query":
        handle_query(args.question, settings)


if __name__ == "__main__":
    main()
