from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class AppSettings:
    books_dir: Path
    qdrant_url: str
    qdrant_api_key: Optional[str]
    collection_name: str
    embedding_model: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    similarity_cutoff: float

    @classmethod
    def from_yaml(cls, path: Path) -> "AppSettings":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            books_dir=Path(data["books_dir"]),
            qdrant_url=data["qdrant_url"],
            qdrant_api_key=data.get("qdrant_api_key"),
            collection_name=data["collection_name"],
            embedding_model=data["embedding_model"],
            llm_model=data["llm_model"],
            chunk_size=int(data["chunk_size"]),
            chunk_overlap=int(data["chunk_overlap"]),
            top_k=int(data["top_k"]),
            similarity_cutoff=float(data["similarity_cutoff"]),
        )
