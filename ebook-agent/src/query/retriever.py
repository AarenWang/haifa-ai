from __future__ import annotations

from dataclasses import dataclass

from llama_index.core import Settings, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from config.settings import AppSettings


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    metadata: dict


def retrieve_chunks(question: str, settings: AppSettings) -> list[RetrievedChunk]:
    Settings.embed_model = OpenAIEmbedding(model=settings.embedding_model)
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    vector_store = QdrantVectorStore(client=client, collection_name=settings.collection_name)
    index = VectorStoreIndex.from_vector_store(vector_store)

    retriever = index.as_retriever(similarity_top_k=settings.top_k)
    nodes = retriever.retrieve(question)

    results: list[RetrievedChunk] = []
    for node in nodes:
        score = node.score or 0.0
        if score < settings.similarity_cutoff:
            continue
        results.append(
            RetrievedChunk(
                text=node.node.get_content(),
                score=score,
                metadata=node.node.metadata or {},
            )
        )
    return results
