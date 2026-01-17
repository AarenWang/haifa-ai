from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from llama_index.core import Settings
from llama_index.llms.openai import OpenAI

from config.settings import AppSettings
from query.prompt import build_prompt
from query.retriever import RetrievedChunk


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    citations: str


def _format_citations(chunks: Iterable[RetrievedChunk]) -> str:
    lines = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.metadata
        book = metadata.get("book_title", "未知书名")
        chapter = metadata.get("chapter", "未知章节")
        page = metadata.get("page", "")
        header = f"[{index}] {book} / {chapter}"
        if page:
            header = f"{header} / {page}"
        lines.append(f"{header}\n{chunk.text}")
    return "\n\n".join(lines)


def synthesize_answer(question: str, chunks: list[RetrievedChunk], settings: AppSettings) -> AnswerResult:
    if not chunks:
        return AnswerResult(
            answer="未在当前书库中找到支持内容。",
            citations="",
        )

    Settings.llm = OpenAI(model=settings.llm_model)
    prompt = build_prompt(question, chunks)
    response = Settings.llm.complete(prompt)
    return AnswerResult(answer=str(response), citations=_format_citations(chunks))
