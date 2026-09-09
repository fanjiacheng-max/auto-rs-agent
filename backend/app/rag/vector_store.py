"""Persistent local vector store for normalized biomedical evidence.

The first implementation deliberately uses a deterministic local hashing
embedding. It makes the index usable without an LLM/embedding API key and
keeps indexing reproducible. A stronger local embedding model can replace
``HashEmbeddingFunction`` without changing the store or document schema.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RagDocument:
    id: str
    text: str
    metadata: Mapping[str, Any]


class HashEmbeddingFunction:
    """Small deterministic feature hashing embedding; no network or API key."""

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 32:
            raise ValueError("dimensions must be >= 32")
        self.dimensions = dimensions

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in input]

    def embed_documents(self, input: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in input]

    def embed_query(self, input: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in input]

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[A-Za-z0-9_.:+/-]+|[\u4e00-\u9fff]", text.lower())
        features = list(tokens)
        # Character trigrams help identifiers and short biomedical terms.
        for token in tokens:
            padded = f"^{token}$"
            features.extend(padded[i : i + 3] for i in range(max(0, len(padded) - 2)))
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    # Chroma probes this when displaying the configured embedding function.
    def name(self) -> str:
        return f"local-hash-{self.dimensions}"


def _metadata_value(value: Any) -> str | int | float | bool:
    """Chroma metadata cannot contain None, lists, or nested dictionaries."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return ";".join(str(item) for item in value)
    return str(value)


class BiomedicalVectorStore:
    """Chroma-backed store scoped to one project workspace."""

    def __init__(
        self,
        persist_directory: str | Path,
        collection_name: str = "biomedical_evidence",
        embedding_dimensions: int = 384,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError("Install chromadb before using BiomedicalVectorStore") from exc

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.embedding_function = HashEmbeddingFunction(embedding_dimensions)
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=self.embedding_function,
            metadata={"embedding": self.embedding_function.name(), "schema_version": "1"},
        )

    def upsert(self, documents: Iterable[RagDocument]) -> int:
        docs = list(documents)
        if not docs:
            return 0
        self.collection.upsert(
            ids=[doc.id for doc in docs],
            documents=[doc.text for doc in docs],
            metadatas=[{key: _metadata_value(value) for key, value in doc.metadata.items()} for doc in docs],
        )
        return len(docs)

    def count(self) -> int:
        return int(self.collection.count())

    def query(
        self,
        text: str,
        n_results: int = 5,
        where: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not text.strip():
            return []
        result = self.collection.query(
            query_texts=[text],
            n_results=max(1, n_results),
            where=dict(where) if where else None,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        texts = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {
                "id": doc_id,
                "text": doc_text,
                "metadata": metadata or {},
                "distance": distance,
            }
            for doc_id, doc_text, metadata, distance in zip(ids, texts, metadatas, distances)
        ]

    def query_candidate(self, candidate: Mapping[str, Any], n_results: int = 8) -> list[dict[str, Any]]:
        """Retrieve evidence with species filtering and exact-identity reranking."""
        entity = candidate.get("entity") or {}
        species = candidate.get("species_taxid")
        identifiers = {
            str(value).casefold()
            for value in [entity.get("canonical_id"), entity.get("symbol"), *(entity.get("aliases") or [])]
            if value
        }
        query_text = " ".join(str(value) for value in (
            entity.get("canonical_id"), entity.get("symbol"), candidate.get("disease"),
            candidate.get("tissue"), candidate.get("cell_type"), candidate.get("omics"),
        ) if value)
        if not query_text.strip():
            return []
        where = {"species_taxid": species} if species is not None else None
        hits = self.query(query_text, n_results=max(n_results * 5, 20), where=where)
        for hit in hits:
            metadata = hit.get("metadata") or {}
            metadata_id = str(metadata.get("entity_id", "")).casefold()
            text = str(hit.get("text", "")).casefold()
            exact = metadata_id in identifiers if metadata_id else False
            token_match = any(identifier and identifier in text for identifier in identifiers)
            hit["identity_match"] = "exact" if exact else ("text" if token_match else "context")
            hit["_rank"] = (0 if exact else 1 if token_match else 2, float(hit.get("distance") or 1.0))
        hits.sort(key=lambda item: item["_rank"])
        for hit in hits:
            hit.pop("_rank", None)
        return hits[: max(1, n_results)]
