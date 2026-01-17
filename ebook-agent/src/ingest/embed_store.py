from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from config.settings import AppSettings
from ingest.chunker import Chunk, chunk_sections
from ingest.parse_epub import parse_epub
from ingest.parse_pdf import parse_pdf
from ingest.scan_books import BookFile


@dataclass(frozen=True)
class IngestResult:
    book_id: str
    title: str
    chunks: int
    skipped: bool


def _book_exists(client: QdrantClient, collection_name: str, book_id: str) -> bool:
    if not client.collection_exists(collection_name=collection_name):
        return False
    points, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="book_id",
                    match=qdrant_models.MatchValue(value=book_id),
                )
            ]
        ),
        limit=1,
        with_payload=False,
        with_vectors=False,
    )
    return len(points) > 0


def _build_documents(
    book: BookFile,
    sections: Iterable[tuple[str, str]],
    chunk_size: int,
    overlap: int,
) -> list[Document]:
    documents: list[Document] = []
    chunked_sections = chunk_sections(sections, chunk_size=chunk_size, overlap=overlap)
    for section_title, chunk in chunked_sections:
        documents.append(
            Document(
                text=chunk.text,
                metadata={
                    "book_id": book.book_id,
                    "book_title": book.title,
                    "author": "",
                    "chapter": section_title,
                    "page": section_title if book.extension == ".pdf" else "",
                    "chunk_index": chunk.index,
                },
            )
        )
    return documents


def _load_sections(book: BookFile) -> list[tuple[str, str]]:
    if book.extension == ".pdf":
        return [(section.title, section.text) for section in parse_pdf(book.path)]
    if book.extension == ".epub":
        return [(section.title, section.text) for section in parse_epub(book.path)]
    return []


def ingest_books(
    books: Iterable[BookFile],
    settings: AppSettings,
    qdrant_client: Optional[QdrantClient] = None,
) -> list[IngestResult]:
    client = qdrant_client or QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    Settings.embed_model = OpenAIEmbedding(model=settings.embedding_model)

    vector_store = QdrantVectorStore(client=client, collection_name=settings.collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    results: list[IngestResult] = []
    for book in books:
        if _book_exists(client, settings.collection_name, book.book_id):
            results.append(IngestResult(book_id=book.book_id, title=book.title, chunks=0, skipped=True))
            continue

        sections = _load_sections(book)
        documents = _build_documents(book, sections, settings.chunk_size, settings.chunk_overlap)
        if not documents:
            results.append(IngestResult(book_id=book.book_id, title=book.title, chunks=0, skipped=True))
            continue

        VectorStoreIndex.from_documents(documents, storage_context=storage_context)
        results.append(
            IngestResult(
                book_id=book.book_id,
                title=book.title,
                chunks=len(documents),
                skipped=False,
            )
        )
    return results
