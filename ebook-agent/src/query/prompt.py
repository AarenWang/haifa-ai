from __future__ import annotations

from typing import Iterable

from query.retriever import RetrievedChunk


def build_prompt(question: str, chunks: Iterable[RetrievedChunk]) -> str:
    context_blocks = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.metadata
        book = metadata.get("book_title", "未知书名")
        chapter = metadata.get("chapter", "未知章节")
        page = metadata.get("page", "")
        label = f"[{index}] {book} / {chapter}"
        if page:
            label = f"{label} / {page}"
        context_blocks.append(f"{label}\n{chunk.text}")

    context_text = "\n\n".join(context_blocks) if context_blocks else "(无引用)"
    return (
        "你是一个基于书籍的知识助理。只能基于以下引用内容作答。"
        "如果引用内容中没有答案，请明确说明未找到。\n\n"
        "回答要求：\n"
        "1. 先给出简明结论\n"
        "2. 列出引用来源（书名 / 章节 / 页码）\n"
        "3. 附上原文片段\n\n"
        f"引用内容：\n{context_text}\n\n"
        f"问题：{question}\n"
        "回答："
    )
