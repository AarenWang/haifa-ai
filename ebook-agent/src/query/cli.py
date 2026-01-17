from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from config.settings import AppSettings
from query.answer import synthesize_answer
from query.retriever import retrieve_chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ebook Knowledge QA")
    parser.add_argument("question", help="要提问的问题")
    parser.add_argument(
        "--config",
        default=Path("./config/settings.yaml"),
        type=Path,
        help="配置文件路径",
    )
    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    settings = AppSettings.from_yaml(args.config)
    chunks = retrieve_chunks(args.question, settings)
    result = synthesize_answer(args.question, chunks, settings)

    console = Console()
    console.print(Panel(result.answer, title="回答"))
    if result.citations:
        console.print(Panel(result.citations, title="引用"))
    else:
        console.print(Panel("无引用内容", title="引用"))


if __name__ == "__main__":
    main()
