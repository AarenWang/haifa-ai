from __future__ import annotations

import asyncio
import os
from typing import Iterable, Optional

from google import genai
from llama_index.core.base.embeddings.base import BaseEmbedding, Embedding


def _resolve_api_key(explicit_key: Optional[str] = None) -> Optional[str]:
    return explicit_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def _create_client(api_key: Optional[str] = None) -> genai.Client:
    resolved_key = _resolve_api_key(api_key)
    if resolved_key:
        return genai.Client(api_key=resolved_key)
    return genai.Client()


class GenAIEmbedding(BaseEmbedding):
    """Gemini embedding adapter for LlamaIndex using google-genai SDK."""

    model_name: str
    api_key: Optional[str] = None

    def _embed_batch(self, texts: Iterable[str]) -> list[Embedding]:
        text_list = list(texts)
        if not text_list:
            return []
        client = _create_client(self.api_key)
        response = client.models.embed_content(model=self.model_name, contents=text_list)
        embeddings = response.embeddings or []
        return [embedding.values or [] for embedding in embeddings]

    def _get_query_embedding(self, query: str) -> Embedding:
        return self._embed_batch([query])[0]

    async def _aget_query_embedding(self, query: str) -> Embedding:
        return await asyncio.to_thread(self._get_query_embedding, query)

    def _get_text_embedding(self, text: str) -> Embedding:
        return self._embed_batch([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[Embedding]:
        return self._embed_batch(texts)
